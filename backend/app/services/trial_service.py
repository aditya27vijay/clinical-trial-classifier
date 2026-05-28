"""CRUD operations for failed_trials table."""

from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from app.models.trial import FailedTrial
from app.models.schemas import TrialCreate, TrialUpdate


def get_trial_by_id(db: Session, trial_id: int) -> Optional[FailedTrial]:
    return db.query(FailedTrial).filter(FailedTrial.id == trial_id).first()


def get_trial_by_nct(db: Session, nct_id: str) -> Optional[FailedTrial]:
    return db.query(FailedTrial).filter(FailedTrial.nct_id == nct_id).first()


def get_trials(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    phase: Optional[str] = None,
    failure_category: Optional[str] = None,
    overall_status: Optional[str] = None,
    min_score: Optional[int] = None,
    max_score: Optional[int] = None,
) -> tuple:
    query = db.query(FailedTrial)

    if search:
        term = f"%{search}%"
        query = query.filter(
            or_(
                FailedTrial.title.ilike(term),
                FailedTrial.drug_name.ilike(term),
                FailedTrial.condition.ilike(term),
                FailedTrial.nct_id.ilike(term),
                FailedTrial.sponsor.ilike(term),
            )
        )

    if phase:
        query = query.filter(FailedTrial.phase.ilike(f"%{phase}%"))

    if failure_category:
        query = query.filter(FailedTrial.failure_category == failure_category)

    if overall_status:
        query = query.filter(FailedTrial.overall_status == overall_status)

    if min_score is not None:
        query = query.filter(FailedTrial.salvageability_score >= min_score)

    if max_score is not None:
        query = query.filter(FailedTrial.salvageability_score <= max_score)

    total = query.count()
    results = (
        query.order_by(FailedTrial.salvageability_score.desc().nullslast())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return total, results


def create_trial(db: Session, trial: TrialCreate) -> FailedTrial:
    db_trial = FailedTrial(**trial.model_dump())
    db.add(db_trial)
    db.commit()
    db.refresh(db_trial)
    return db_trial


def upsert_trial(db: Session, trial_data: dict) -> tuple:
    """Insert or update a trial. Returns (trial, created)."""
    existing = get_trial_by_nct(db, trial_data["nct_id"])
    if existing:
        for k, v in trial_data.items():
            if v is not None:
                setattr(existing, k, v)
        db.commit()
        db.refresh(existing)
        return existing, False
    else:
        db_trial = FailedTrial(**trial_data)
        db.add(db_trial)
        db.commit()
        db.refresh(db_trial)
        return db_trial, True


def update_trial(db: Session, trial_id: int, update: TrialUpdate) -> Optional[FailedTrial]:
    trial = get_trial_by_id(db, trial_id)
    if not trial:
        return None
    for k, v in update.model_dump(exclude_unset=True).items():
        setattr(trial, k, v)
    db.commit()
    db.refresh(trial)
    return trial


def delete_trial(db: Session, trial_id: int) -> bool:
    trial = get_trial_by_id(db, trial_id)
    if not trial:
        return False
    db.delete(trial)
    db.commit()
    return True


def get_dashboard_stats(db: Session) -> dict:
    total = db.query(FailedTrial).count()

    by_status = dict(
        db.query(FailedTrial.overall_status, func.count())
        .group_by(FailedTrial.overall_status)
        .all()
    )

    by_phase = dict(
        db.query(FailedTrial.phase, func.count())
        .group_by(FailedTrial.phase)
        .all()
    )

    by_failure = dict(
        db.query(FailedTrial.failure_category, func.count())
        .group_by(FailedTrial.failure_category)
        .all()
    )

    avg_score_row = db.query(func.avg(FailedTrial.salvageability_score)).scalar()
    avg_score = round(float(avg_score_row), 1) if avg_score_row else 0.0

    top_salvageable = (
        db.query(FailedTrial)
        .filter(FailedTrial.salvageability_score.isnot(None))
        .order_by(FailedTrial.salvageability_score.desc())
        .limit(5)
        .all()
    )

    return {
        "total_trials": total,
        "by_status": by_status,
        "by_phase": by_phase,
        "by_failure_category": by_failure,
        "avg_salvageability": avg_score,
        "top_salvageable": top_salvageable,
    }
