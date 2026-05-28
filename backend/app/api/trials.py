from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database.db import get_db
from app.models.schemas import TrialResponse, TrialListResponse, TrialUpdate, DashboardStats
from app.services import trial_service

router = APIRouter()


@router.get("/", response_model=TrialListResponse)
def list_trials(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    phase: Optional[str] = Query(None),
    failure_category: Optional[str] = Query(None),
    overall_status: Optional[str] = Query(None),
    min_score: Optional[int] = Query(None, ge=0, le=100),
    max_score: Optional[int] = Query(None, ge=0, le=100),
    db: Session = Depends(get_db),
):
    skip = (page - 1) * page_size
    total, results = trial_service.get_trials(
        db,
        skip=skip,
        limit=page_size,
        search=search,
        phase=phase,
        failure_category=failure_category,
        overall_status=overall_status,
        min_score=min_score,
        max_score=max_score,
    )
    return TrialListResponse(
        total=total,
        page=page,
        page_size=page_size,
        results=results,
    )


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db)):
    return trial_service.get_dashboard_stats(db)


@router.get("/{trial_id}", response_model=TrialResponse)
def get_trial(trial_id: int, db: Session = Depends(get_db)):
    trial = trial_service.get_trial_by_id(db, trial_id)
    if not trial:
        raise HTTPException(status_code=404, detail="Trial not found")
    return trial


@router.get("/nct/{nct_id}", response_model=TrialResponse)
def get_trial_by_nct(nct_id: str, db: Session = Depends(get_db)):
    trial = trial_service.get_trial_by_nct(db, nct_id.upper())
    if not trial:
        raise HTTPException(status_code=404, detail="Trial not found")
    return trial


@router.patch("/{trial_id}", response_model=TrialResponse)
def update_trial(trial_id: int, update: TrialUpdate, db: Session = Depends(get_db)):
    trial = trial_service.update_trial(db, trial_id, update)
    if not trial:
        raise HTTPException(status_code=404, detail="Trial not found")
    return trial


@router.delete("/{trial_id}")
def delete_trial(trial_id: int, db: Session = Depends(get_db)):
    success = trial_service.delete_trial(db, trial_id)
    if not success:
        raise HTTPException(status_code=404, detail="Trial not found")
    return {"message": "Trial deleted"}
