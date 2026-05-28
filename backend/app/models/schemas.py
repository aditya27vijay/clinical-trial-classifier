from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


class TrialBase(BaseModel):
    nct_id: str
    title: Optional[str] = None
    condition: Optional[str] = None
    drug_name: Optional[str] = None
    phase: Optional[str] = None
    overall_status: Optional[str] = None
    why_stopped: Optional[str] = None
    failure_category: Optional[str] = None
    salvageability_score: Optional[int] = None
    recommended_actions: Optional[Any] = None
    sponsor: Optional[str] = None
    start_date: Optional[str] = None
    completion_date: Optional[str] = None
    enrollment: Optional[int] = None


class TrialCreate(TrialBase):
    pass


class TrialUpdate(BaseModel):
    failure_category: Optional[str] = None
    salvageability_score: Optional[int] = None
    recommended_actions: Optional[Any] = None


class TrialResponse(TrialBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ClassifyRequest(BaseModel):
    why_stopped: str


class ClassifyResponse(BaseModel):
    why_stopped: str
    failure_category: str
    salvageability_score: int
    recommended_actions: List[str]


class IngestResponse(BaseModel):
    fetched: int
    inserted: int
    skipped: int
    message: str


class TrialListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    results: List[TrialResponse]


class DashboardStats(BaseModel):
    total_trials: int
    by_status: dict
    by_phase: dict
    by_failure_category: dict
    avg_salvageability: float
    top_salvageable: List[TrialResponse]
