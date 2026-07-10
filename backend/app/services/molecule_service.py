"""
Molecule Service — DB CRUD and aggregation for the molecule intelligence layer.
Called by the ingest pipeline and the /molecules API router.
"""

import logging
from typing import List, Optional, Tuple, Dict, Any
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.models.molecule_model import (
    Molecule, MoleculeTrial, MoleculePatent, MoleculeLiterature, MoleculeRealWorldUsage
)

logger = logging.getLogger(__name__)


# ─── Upsert core molecule ─────────────────────────────────────────────────────

def upsert_molecule(db: Session, resolved: dict) -> Tuple[Molecule, bool]:
    """
    Insert or update a molecule record.
    Deduplication key: inchi_key (if available), else canonical_name.
    Returns (molecule, created).
    """
    inchi_key = resolved.get("inchi_key")
    name      = resolved.get("canonical_name") or resolved.get("drug_name", "Unknown")

    # Try dedup by InChIKey first, then by name
    existing = None
    if inchi_key:
        existing = db.query(Molecule).filter(Molecule.inchi_key == inchi_key).first()
    if not existing:
        existing = db.query(Molecule).filter(
            func.lower(Molecule.canonical_name) == func.lower(name)
        ).first()

    updatable_fields = [
        "pubchem_cid", "inchi_key", "smiles", "inchi", "chembl_id",
        "chembl_pref_name", "mechanism_of_action", "primary_targets",
        "target_classes", "modality", "molecular_weight", "logp",
        "resolution_source", "resolution_confidence", "resolution_method",
        "drugbank_id", "approval_status",
    ]

    if existing:
        # Update fields that may have improved with new resolution.
        # Prefer a strictly better resolution_confidence rather than only
        # filling nulls, so a re-resolution with better match quality (e.g.
        # exact_name replacing an earlier fuzzy match) actually takes effect.
        new_confidence = resolved.get("resolution_confidence")
        old_confidence = existing.resolution_confidence
        should_upgrade = (
            new_confidence is not None and
            (old_confidence is None or float(new_confidence) > float(old_confidence))
        )

        for field in updatable_fields:
            new_val = resolved.get(field)
            if new_val is None:
                continue
            if getattr(existing, field) is None or (should_upgrade and field.startswith("resolution")):
                setattr(existing, field, new_val)

        # Structure conflicts should never be silently cleared once flagged —
        # only overwrite False -> True, never True -> False, without manual review.
        if resolved.get("resolution_conflict"):
            existing.resolution_conflict = True

        if resolved.get("is_combination"):
            existing.is_combination = True
            existing.combination_components = resolved.get("combination_components")

        db.commit()
        db.refresh(existing)

        if resolved.get("real_world_usage"):
            upsert_real_world_usage(db, existing.id, resolved["real_world_usage"])

        return existing, False

    # Create new
    mol = Molecule(
        canonical_name         = name,
        inn_name               = resolved.get("inn_name"),
        trade_names            = resolved.get("trade_names"),
        research_codes         = resolved.get("research_codes"),
        pubchem_cid            = resolved.get("pubchem_cid"),
        inchi_key              = inchi_key,
        smiles                 = resolved.get("smiles"),
        inchi                  = resolved.get("inchi"),
        chembl_id              = resolved.get("chembl_id"),
        chembl_pref_name       = resolved.get("chembl_pref_name"),
        mechanism_of_action    = resolved.get("mechanism_of_action"),
        primary_targets        = resolved.get("primary_targets"),
        target_classes         = resolved.get("target_classes"),
        modality               = resolved.get("modality"),
        molecular_weight       = resolved.get("molecular_weight"),
        logp                   = resolved.get("logp"),
        resolution_source      = resolved.get("resolution_source", "unresolved"),
        resolution_confidence  = resolved.get("resolution_confidence", 0.3),
        resolution_method      = resolved.get("resolution_method"),
        resolution_conflict    = resolved.get("resolution_conflict", False),
        is_combination         = resolved.get("is_combination", False),
        combination_components = resolved.get("combination_components"),
        drugbank_id            = resolved.get("drugbank_id"),
        approval_status        = resolved.get("approval_status"),
    )
    db.add(mol)
    db.commit()
    db.refresh(mol)
    logger.info(f"[MoleculeService] Created molecule: {name} (id={mol.id})")

    if resolved.get("real_world_usage"):
        upsert_real_world_usage(db, mol.id, resolved["real_world_usage"])

    return mol, True


def link_trial(
    db: Session,
    molecule_id: int,
    nct_id: str,
    indication: Optional[str],
    phase: Optional[str],
    failure_category: Optional[str],
    salvageability_score: Optional[int],
    sponsor: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[date] = None,
    completion_date: Optional[date] = None,
    why_stopped: Optional[str] = None,
) -> None:
    """
    Link a trial to a molecule. Skips if already linked.

    The sponsor/status/start_date/completion_date/why_stopped fields are what
    power the usage timeline (get_usage_timeline) — i.e. "when and where" this
    molecule was actually studied, not just the aggregate counts.
    """
    existing = db.query(MoleculeTrial).filter(
        MoleculeTrial.molecule_id == molecule_id,
        MoleculeTrial.nct_id == nct_id,
    ).first()

    if not existing:
        link = MoleculeTrial(
            molecule_id=molecule_id,
            nct_id=nct_id,
            indication=indication,
            phase=phase,
            failure_category=failure_category,
            salvageability_score=salvageability_score,
            sponsor=sponsor,
            status=status,
            start_date=start_date,
            completion_date=completion_date,
            why_stopped=why_stopped,
        )
        db.add(link)
        db.commit()
    else:
        # Backfill timeline fields if they were missing (e.g. molecule was
        # linked before this fields existed, or before enrichment ran).
        changed = False
        for field, value in [
            ("sponsor", sponsor), ("status", status),
            ("start_date", start_date), ("completion_date", completion_date),
            ("why_stopped", why_stopped),
        ]:
            if value is not None and getattr(existing, field) is None:
                setattr(existing, field, value)
                changed = True
        if changed:
            db.commit()


def update_molecule_aggregates(db: Session, molecule_id: int) -> None:
    """
    Recompute aggregate signals on the molecule from its linked trials,
    including the first_studied / last_active timeline bounds.
    Called after each new trial is linked.
    """
    mol = db.query(Molecule).filter(Molecule.id == molecule_id).first()
    if not mol:
        return

    links = db.query(MoleculeTrial).filter(MoleculeTrial.molecule_id == molecule_id).all()
    if not links:
        return

    # Aggregate
    scores      = [l.salvageability_score for l in links if l.salvageability_score]
    phases      = [l.phase for l in links if l.phase]
    indications = list(set(l.indication for l in links if l.indication))
    categories  = {}
    for l in links:
        if l.failure_category:
            categories[l.failure_category] = categories.get(l.failure_category, 0) + 1

    # Phase rank for latest_phase_reached
    phase_order = {
        "PHASE4": 5, "PHASE3": 4, "PHASE2": 3,
        "PHASE1/PHASE2": 2.5, "PHASE1": 2, "EARLY_PHASE1": 1
    }
    latest_phase = None
    if phases:
        latest_phase = max(phases, key=lambda p: phase_order.get(
            p.replace(" ", "").upper().replace("/", "").replace("PHASE", "PHASE"), 0
        ))

    # Timeline bounds — "when" this molecule was studied, earliest to most recent
    start_dates = [l.start_date for l in links if l.start_date]
    end_dates   = [l.completion_date for l in links if l.completion_date]

    mol.total_trials         = len(links)
    mol.total_indications    = len(indications)
    mol.failure_categories   = categories
    mol.best_salvageability  = max(scores) if scores else None
    mol.avg_salvageability   = round(sum(scores) / len(scores), 2) if scores else None
    mol.latest_phase_reached = latest_phase
    mol.first_studied        = min(start_dates) if start_dates else None
    mol.last_active          = max(end_dates) if end_dates else (max(start_dates) if start_dates else None)

    db.commit()


def get_usage_timeline(db: Session, molecule_id: int) -> List[Dict[str, Any]]:
    """
    Build the chronological "when and where this molecule was used" view:
    every trial it appeared in, ordered by start date, with sponsor, phase,
    indication, status, and how it ended.

    This is the core deliverable for BD teams asking "what has actually
    happened with this asset" — as opposed to the aggregate counts alone.
    """
    links = (
        db.query(MoleculeTrial)
        .filter(MoleculeTrial.molecule_id == molecule_id)
        .order_by(MoleculeTrial.start_date.asc().nullslast())
        .all()
    )

    timeline = []
    for l in links:
        timeline.append({
            "nct_id":               l.nct_id,
            "indication":           l.indication,
            "phase":                l.phase,
            "sponsor":              l.sponsor,
            "status":               l.status,
            "start_date":           l.start_date.isoformat() if l.start_date else None,
            "completion_date":      l.completion_date.isoformat() if l.completion_date else None,
            "failure_category":     l.failure_category,
            "why_stopped":          l.why_stopped,
            "salvageability_score": l.salvageability_score,
        })

    return timeline


# ─── Real-world usage (OpenTargets / DrugBank) ───────────────────────────────

def upsert_real_world_usage(db: Session, molecule_id: int, records: List[dict]) -> int:
    """
    Upsert approved/investigational/withdrawn indications for a molecule.
    Follows the same upsert pattern as patents/literature. Also rolls the
    strongest approval_status up onto the Molecule row for quick filtering.
    """
    inserted = 0
    for r in records:
        indication = r.get("indication")
        source     = r.get("source")
        if not indication or not source:
            continue

        existing = db.query(MoleculeRealWorldUsage).filter(
            MoleculeRealWorldUsage.molecule_id == molecule_id,
            MoleculeRealWorldUsage.indication == indication,
            MoleculeRealWorldUsage.source == source,
        ).first()

        if not existing:
            rwu = MoleculeRealWorldUsage(
                molecule_id        = molecule_id,
                indication         = indication,
                disease_id         = r.get("disease_id"),
                approval_status    = r.get("approval_status"),
                region             = r.get("region"),
                association_score  = r.get("association_score"),
                approved_date      = r.get("approved_date"),
                source             = source,
                external_id        = r.get("external_id"),
            )
            db.add(rwu)
            inserted += 1

    if inserted:
        db.commit()

        mol = db.query(Molecule).filter(Molecule.id == molecule_id).first()
        all_rwu = db.query(MoleculeRealWorldUsage).filter(
            MoleculeRealWorldUsage.molecule_id == molecule_id
        ).all()
        if mol and all_rwu:
            statuses = {r.approval_status for r in all_rwu if r.approval_status}
            mol.approval_status = (
                "approved" if "approved" in statuses else
                "investigational" if "investigational" in statuses else
                "withdrawn" if "withdrawn" in statuses else
                mol.approval_status
            )
            drugbank_ids = [r.external_id for r in all_rwu if r.source == "drugbank" and r.external_id]
            if drugbank_ids and not mol.drugbank_id:
                mol.drugbank_id = drugbank_ids[0]
            db.commit()

    return inserted


def get_real_world_usage(db: Session, molecule_id: int) -> List[MoleculeRealWorldUsage]:
    return (
        db.query(MoleculeRealWorldUsage)
        .filter(MoleculeRealWorldUsage.molecule_id == molecule_id)
        .all()
    )


# ─── Patents ──────────────────────────────────────────────────────────────────

def upsert_patents(db: Session, molecule_id: int, patents: List[dict]) -> int:
    """Upsert patent records for a molecule. Returns count inserted."""
    inserted = 0
    for p in patents:
        patent_num = p.get("patent_number")
        country    = p.get("country", "US")
        if not patent_num:
            continue

        existing = db.query(MoleculePatent).filter(
            MoleculePatent.molecule_id   == molecule_id,
            MoleculePatent.patent_number == patent_num,
            MoleculePatent.country       == country,
        ).first()

        if not existing:
            pat = MoleculePatent(
                molecule_id  = molecule_id,
                patent_number = patent_num,
                title        = p.get("title"),
                assignee     = p.get("assignee"),
                filing_date  = p.get("filing_date"),
                grant_date   = p.get("grant_date"),
                expiry_date  = p.get("expiry_date"),
                patent_type  = p.get("patent_type"),
                country      = country,
                source       = p.get("source", "uspto"),
            )
            db.add(pat)
            inserted += 1

    if inserted:
        db.commit()

        # Update molecule-level patent summary
        mol     = db.query(Molecule).filter(Molecule.id == molecule_id).first()
        all_pats = db.query(MoleculePatent).filter(MoleculePatent.molecule_id == molecule_id).all()
        if mol and all_pats:
            filing_dates = [p.filing_date for p in all_pats if p.filing_date]
            expiry_dates = [p.expiry_date for p in all_pats if p.expiry_date]
            today        = date.today()

            mol.earliest_patent_date = min(filing_dates) if filing_dates else None
            mol.patent_expiry_date   = max(expiry_dates) if expiry_dates else None

            if mol.earliest_patent_date:
                mol.patent_age_years = (today - mol.earliest_patent_date).days // 365

            if mol.patent_expiry_date:
                mol.ip_status = "active" if mol.patent_expiry_date > today else "expired"
            else:
                mol.ip_status = "unknown"

            mol.is_composition_patent = any(
                p.patent_type == "composition" for p in all_pats
            )
            db.commit()

    return inserted


# ─── Literature ───────────────────────────────────────────────────────────────

def upsert_literature(db: Session, molecule_id: int, publications: List[dict]) -> int:
    """Upsert PubMed records for a molecule. Returns count inserted."""
    inserted = 0
    for pub in publications:
        pmid = pub.get("pmid")
        if not pmid:
            continue

        existing = db.query(MoleculeLiterature).filter(
            MoleculeLiterature.molecule_id == molecule_id,
            MoleculeLiterature.pmid == pmid,
        ).first()

        if not existing:
            lit = MoleculeLiterature(
                molecule_id = molecule_id,
                pmid        = pmid,
                title       = pub.get("title"),
                abstract    = pub.get("abstract"),
                pub_date    = pub.get("pub_date"),
                journal     = pub.get("journal"),
                ref_type    = pub.get("ref_type", "background"),
            )
            db.add(lit)
            inserted += 1

    if inserted:
        db.commit()

        # Update molecule-level literature counts
        mol = db.query(Molecule).filter(Molecule.id == molecule_id).first()
        all_lit = db.query(MoleculeLiterature).filter(
            MoleculeLiterature.molecule_id == molecule_id
        ).all()
        if mol:
            mol.pubmed_result_count     = sum(1 for l in all_lit if l.ref_type == "result")
            mol.pubmed_background_count = sum(1 for l in all_lit if l.ref_type == "background")
            mol.pmids = [l.pmid for l in all_lit if l.pmid]
            db.commit()

    return inserted


# ─── Query helpers ────────────────────────────────────────────────────────────

def get_molecule_by_id(db: Session, molecule_id: int) -> Optional[Molecule]:
    return db.query(Molecule).filter(Molecule.id == molecule_id).first()


def get_molecules(
    db: Session,
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    modality: Optional[str] = None,
    min_score: Optional[int] = None,
    max_score: Optional[int] = None,
    ip_status: Optional[str] = None,
    has_results: Optional[bool] = None,
    has_publications: Optional[bool] = None,
    approval_status: Optional[str] = None,
    has_resolution_conflict: Optional[bool] = None,
) -> Tuple[int, List[Molecule]]:
    query = db.query(Molecule)

    if search:
        term = f"%{search}%"
        query = query.filter(
            or_(
                Molecule.canonical_name.ilike(term),
                Molecule.inn_name.ilike(term),
                Molecule.chembl_pref_name.ilike(term),
            )
        )
    if modality:
        query = query.filter(Molecule.modality == modality)
    if min_score is not None:
        query = query.filter(Molecule.best_salvageability >= min_score)
    if max_score is not None:
        query = query.filter(Molecule.best_salvageability <= max_score)
    if ip_status:
        query = query.filter(Molecule.ip_status == ip_status)
    if has_results is True:
        query = query.filter(Molecule.has_posted_results == True)
    if has_publications is True:
        query = query.filter(Molecule.pubmed_result_count > 0)
    if approval_status:
        query = query.filter(Molecule.approval_status == approval_status)
    if has_resolution_conflict is not None:
        query = query.filter(Molecule.resolution_conflict == has_resolution_conflict)

    total   = query.count()
    results = (
        query.order_by(Molecule.best_salvageability.desc().nullslast())
        .offset(skip).limit(limit).all()
    )
    return total, results


def get_molecule_stats(db: Session) -> dict:
    total = db.query(Molecule).count()

    by_modality = dict(
        db.query(Molecule.modality, func.count())
        .filter(Molecule.modality.isnot(None))
        .group_by(Molecule.modality).all()
    )
    by_ip_status = dict(
        db.query(Molecule.ip_status, func.count())
        .filter(Molecule.ip_status.isnot(None))
        .group_by(Molecule.ip_status).all()
    )
    by_approval_status = dict(
        db.query(Molecule.approval_status, func.count())
        .filter(Molecule.approval_status.isnot(None))
        .group_by(Molecule.approval_status).all()
    )

    avg_score = db.query(func.avg(Molecule.best_salvageability)).scalar()
    resolved  = db.query(Molecule).filter(
        Molecule.resolution_source != "unresolved"
    ).count()
    conflicts = db.query(Molecule).filter(Molecule.resolution_conflict == True).count()

    top = (
        db.query(Molecule)
        .filter(Molecule.best_salvageability.isnot(None))
        .order_by(Molecule.best_salvageability.desc())
        .limit(10).all()
    )

    return {
        "total_molecules":    total,
        "resolved_count":     resolved,
        "resolution_rate":    round(resolved / total, 2) if total else 0,
        "resolution_conflicts": conflicts,
        "by_modality":        by_modality,
        "by_ip_status":       by_ip_status,
        "by_approval_status": by_approval_status,
        "avg_salvageability": round(float(avg_score), 1) if avg_score else 0.0,
        "top_molecules":      top,
    }