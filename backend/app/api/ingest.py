from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional
from app.database.db import get_db
from app.models.schemas import IngestResponse
from app.services.fetcher import fetch_failed_trials
from app.services.ml_classifier import full_analysis
from app.services.trial_service import upsert_trial
import logging
import time

logger = logging.getLogger(__name__)
router = APIRouter()


def _run_ingest(
    db: Session,
    max_results: int,
    condition: Optional[str],
    intervention: Optional[str],
):
    trials = fetch_failed_trials(
        max_results=max_results,
        condition=condition,
        intervention=intervention,
    )

    inserted = 0
    skipped  = 0

    for trial_data in trials:
        why_stopped = trial_data.get("why_stopped") or ""

        # Pass full trial_context so the LLM + scorer get every available field
        category, score, recommendations, data_confidence, score_breakdown = full_analysis(
            why_stopped,
            trial_context=trial_data,
        )

        time.sleep(5)  

        trial_data["failure_category"]     = category
        trial_data["salvageability_score"] = score
        trial_data["recommended_actions"]  = recommendations
        trial_data["data_confidence"]      = data_confidence
        trial_data["score_breakdown"]      = score_breakdown

        # Strip internal underscore keys before writing to DB
        db_data = {k: v for k, v in trial_data.items() if not k.startswith("_")}

        _, created = upsert_trial(db, db_data)
        if created:
            inserted += 1
        else:
            skipped += 1

    return len(trials), inserted, skipped


@router.post("/", response_model=IngestResponse)
def trigger_ingest(
    max_results:  int           = Query(100, ge=1, le=1000),
    condition:    Optional[str] = Query(None),
    intervention: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    fetched, inserted, skipped = _run_ingest(db, max_results, condition, intervention)
    return IngestResponse(
        fetched=fetched,
        inserted=inserted,
        skipped=skipped,
        message=f"Ingestion complete. Fetched {fetched}, inserted {inserted}, updated {skipped}.",
    )


@router.post("/background", status_code=202)
def trigger_ingest_background(
    background_tasks: BackgroundTasks,
    max_results:      int           = Query(500, ge=1, le=2000),
    condition:        Optional[str] = Query(None),
    intervention:     Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    background_tasks.add_task(_run_ingest, db, max_results, condition, intervention)
    return {"message": "Background ingestion started", "max_results": max_results}