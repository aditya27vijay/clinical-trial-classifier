from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from app.models.schemas import ClassifyResponse
from app.services.ml_classifier import full_analysis

router = APIRouter()


class ClassifyRequest(BaseModel):
    why_stopped: str
    drug_name: Optional[str] = None
    phase: Optional[str] = None


@router.post("/", response_model=ClassifyResponse)
def classify_termination_reason(request: ClassifyRequest):
    """
    Classify a raw termination reason.
    Optionally pass drug_name and phase for modality-aware scoring.
    """
    category, score, recommendations = full_analysis(
        request.why_stopped,
        drug_name=request.drug_name,
        phase=request.phase,
    )
    return ClassifyResponse(
        why_stopped=request.why_stopped,
        failure_category=category,
        salvageability_score=score,
        recommended_actions=recommendations,
    )
