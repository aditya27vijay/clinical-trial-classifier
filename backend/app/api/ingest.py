"""
Ingest API — fetches from AACT, classifies, scores, resolves molecules.

Flow per trial:
  1. Fetch from AACT (aact_fetcher)
  2. Classify + score (ml_classifier → scorer)
  3. Upsert into failed_trials
  4. Resolve drug name → PubChem + ChEMBL (molecule_resolver)
  5. Upsert into molecules + link molecule_trials
  6. Background: fetch patents + PubMed literature
"""

import time
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.orm import Session

from app.database.db import get_db, SessionLocal
from app.models.schemas import IngestResponse
from app.models.trial import FailedTrial
from app.services.ml_classifier import full_analysis
from app.services import molecule_service
from app.services.molecule_resolver import resolve as resolve_molecule
from app.services.patent_fetcher import (
    fetch_patents_for_molecule,
    determine_ip_status,
    get_earliest_filing_date,
    get_latest_expiry_date,
)
from app.services.pubmed_fetcher import fetch_literature_for_molecule

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Background enrichment ────────────────────────────────────────────────────

def _enrich_molecule_background(molecule_id: int, drug_name: str, inchi_key: Optional[str]):
    """
    Runs after trial ingest — fetches patents + PubMed and stores results.
    Non-blocking: called via BackgroundTasks.
    """
    db = SessionLocal()
    try:
        # Patents
        patents = fetch_patents_for_molecule(drug_name, inchi_key=inchi_key)
        if patents:
            inserted = molecule_service.upsert_patents(db, molecule_id, patents)
            logger.info(f"[Enrich] {drug_name} → {inserted} patents inserted")

        # Literature
        literature = fetch_literature_for_molecule(drug_name, max_results=15)
        if literature:
            inserted = molecule_service.upsert_literature(db, molecule_id, literature)
            logger.info(f"[Enrich] {drug_name} → {inserted} PubMed records inserted")

            # Update has_posted_results flag
            mol = molecule_service.get_molecule_by_id(db, molecule_id)
            if mol:
                mol.has_posted_results = mol.pubmed_result_count > 0
                db.commit()

    except Exception as e:
        logger.error(f"[Enrich] Background enrichment failed for {drug_name}: {e}")
    finally:
        db.close()


# ─── Core ingestion worker ────────────────────────────────────────────────────

def _run_ingest(
    db: Session,
    background_tasks,
    max_results: int,
    condition: Optional[str],
    intervention: Optional[str],
) -> dict:
    """
    Full ingest pipeline: AACT → classify → score → upsert trial → resolve molecule.
    """
    from app.services.aact_fetcher import AACTFetcher
    aact = AACTFetcher()

    trials = aact.fetch_terminated_trials(
        max_results=max_results,
        condition=condition,
        intervention=intervention,
    )
    logger.info(f"[Ingest] Fetched {len(trials)} trials from AACT")

    inserted = 0
    skipped  = 0
    errors   = 0
    results  = []

    for trial_data in trials:
        nct_id = trial_data.get("nct_id")
        if not nct_id:
            continue

        # Skip if already ingested
        existing = db.query(FailedTrial).filter(FailedTrial.nct_id == nct_id).first()
        if existing:
            skipped += 1
            results.append({"nct_id": nct_id, "status": "skipped"})
            continue

        try:
            # ── Step 1: Enrich trial from AACT ────────────────────────────────
            full_trial = aact.enrich_trial_with_design_and_outcomes(nct_id)

            # ── Step 2: Classify + score ──────────────────────────────────────
            why_stopped = full_trial.get("why_stopped") or ""
            category, score, recs, confidence, breakdown = full_analysis(
                why_stopped,
                trial_context=full_trial,
            )

            # Rate limit buffer for Groq
            time.sleep(4)

            # ── Step 3: Persist trial ─────────────────────────────────────────
            drug_names = full_trial.get("drug_names") or []
            primary_drug = drug_names[0] if drug_names else full_trial.get("drug_name") or None

            trial_row = FailedTrial(
                nct_id               = nct_id,
                title                = full_trial.get("brief_title"),
                condition            = full_trial.get("condition"),
                drug_name            = primary_drug,
                phase                = full_trial.get("phase"),
                overall_status       = full_trial.get("overall_status"),
                why_stopped          = why_stopped,
                sponsor              = full_trial.get("sponsor"),
                start_date           = str(full_trial.get("start_date") or ""),
                completion_date      = str(full_trial.get("completion_date") or ""),
                enrollment           = full_trial.get("enrollment"),
                failure_category     = category,
                salvageability_score = score,
                recommended_actions  = recs,
                data_confidence      = confidence,
                score_breakdown      = breakdown,
            )
            db.add(trial_row)
            db.commit()
            db.refresh(trial_row)

            # ── Step 4: Resolve molecule ──────────────────────────────────────
            if primary_drug:
                resolved = resolve_molecule(
                    primary_drug,
                    intervention_type=full_trial.get("_t1_intervention_type"),
                )

                mol, _ = molecule_service.upsert_molecule(db, {
                    **resolved,
                    "canonical_name": resolved.get("canonical_name") or primary_drug,
                    "has_expanded_access": full_trial.get("_t2_has_expanded_access", False),
                    "has_posted_results":  full_trial.get("_t2_has_results", False),
                })

                # Link trial → molecule
                molecule_service.link_trial(
                    db,
                    molecule_id          = mol.id,
                    nct_id               = nct_id,
                    indication           = full_trial.get("condition"),
                    phase                = full_trial.get("phase"),
                    failure_category     = category,
                    salvageability_score = score,
                )

                # Recompute aggregates (score, phase, indications)
                molecule_service.update_molecule_aggregates(db, mol.id)

                # ── Step 5: Background enrichment ─────────────────────────────
                if background_tasks:
                    background_tasks.add_task(
                        _enrich_molecule_background,
                        mol.id,
                        primary_drug,
                        resolved.get("inchi_key"),
                    )

            inserted += 1
            results.append({
                "nct_id":   nct_id,
                "status":   "success",
                "category": category,
                "score":    score,
                "drug":     primary_drug,
            })
            logger.info(f"[Ingest] ✓ {nct_id} — {category} score={score} drug={primary_drug}")

        except Exception as e:
            db.rollback()
            errors += 1
            results.append({"nct_id": nct_id, "status": "error", "error": str(e)})
            logger.error(f"[Ingest] ✗ {nct_id}: {e}", exc_info=True)

    logger.info(f"[Ingest] Complete — inserted={inserted} skipped={skipped} errors={errors}")
    return {
        "total_fetched": len(trials),
        "inserted":      inserted,
        "skipped":       skipped,
        "errors":        errors,
        "results":       results,
    }


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/", response_model=IngestResponse)
def trigger_ingest(
    background_tasks: BackgroundTasks,
    max_results:  int           = Query(100, ge=1, le=500),
    condition:    Optional[str] = Query(None),
    intervention: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Synchronous ingest — recommended for ≤100 trials."""
    summary = _run_ingest(db, background_tasks, max_results, condition, intervention)
    return IngestResponse(
        fetched  = summary["total_fetched"],
        inserted = summary["inserted"],
        skipped  = summary["skipped"],
        message  = (
            f"Ingestion complete. Fetched {summary['total_fetched']}, "
            f"inserted {summary['inserted']}, "
            f"skipped {summary['skipped']}, "
            f"errors {summary['errors']}. "
            f"Patent + PubMed enrichment running in background."
        ),
    )


@router.post("/background", status_code=202)
def trigger_ingest_background(
    background_tasks: BackgroundTasks,
    max_results:  int           = Query(500, ge=1, le=5000),
    condition:    Optional[str] = Query(None),
    intervention: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Background ingest — use for large batches (>100 trials)."""
    background_tasks.add_task(
        _run_ingest, db, None, max_results, condition, intervention
    )
    return {
        "status": "enqueued",
        "message": f"Ingestion queued for up to {max_results} trials.",
    }