from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from app.services.ml_classifier import full_analysis

router = APIRouter()


# ─── Request Schema ───────────────────────────────────────────────────────────

class ClassifyRequest(BaseModel):
    # Core (required)
    why_stopped: str

    # Tier 1 — Protocol fields
    drug_name:                  Optional[str]       = None
    phase:                      Optional[str]       = None
    condition:                  Optional[str]       = None
    sponsor:                    Optional[str]       = None
    sponsor_class:              Optional[str]       = None
    enrollment:                 Optional[int]       = None
    enrollment_type:            Optional[str]       = None
    num_sites:                  Optional[int]       = None
    trial_duration_days:        Optional[int]       = None
    is_fda_regulated_drug:      Optional[bool]      = None
    allocation:                 Optional[str]       = None
    intervention_model:         Optional[str]       = None
    primary_purpose:            Optional[str]       = None
    study_type:                 Optional[str]       = None
    masking:                    Optional[str]       = None
    num_arms:                   Optional[int]       = None
    is_rare_disease:            Optional[bool]      = None
    is_oncology:                Optional[bool]      = None
    is_cns:                     Optional[bool]      = None
    intervention_type:          Optional[str]       = None
    intervention_description:   Optional[str]       = None
    secondary_outcome_count:    Optional[int]       = None
    primary_outcome_measures:   Optional[List[str]] = None
    eligibility_criteria_count: Optional[int]       = None
    responsible_party_type:     Optional[str]       = None

    # Tier 2 — Contextual enrichment
    has_expanded_access:        Optional[bool]      = None
    collaborator_count:         Optional[int]       = None
    collaborator_names:         Optional[List[str]] = None
    publication_count:          Optional[int]       = None
    has_results:                Optional[bool]      = None
    related_studies_count:      Optional[int]       = None
    detailed_description:       Optional[str]       = None

    # Tier 3 — Results data
    completion_rate:            Optional[float]     = None
    sae_count:                  Optional[int]       = None
    sae_rate:                   Optional[float]     = None
    death_count:                Optional[int]       = None
    has_results_section:        Optional[bool]      = None
    total_started:              Optional[int]       = None
    total_completed:            Optional[int]       = None


# ─── Response Schema ──────────────────────────────────────────────────────────

class ClassifyResponse(BaseModel):
    why_stopped:          str
    failure_category:     str
    salvageability_score: int
    recommended_actions:  List[str]
    data_confidence:      str
    score_breakdown:      Dict[str, Any]
    warning:              Optional[str] = None


# ─── Context Builder ──────────────────────────────────────────────────────────

def _build_context_from_request(req: ClassifyRequest) -> Dict[str, Any]:
    """
    Map all incoming payload fields to the _t1_/_t2_/_t3_ prefixed keys
    that the scorer and _build_trial_context expect.
    Only includes fields that were actually provided (not None).
    """
    ctx = {}

    # Core fields (no prefix — used by LLM context builder directly)
    if req.drug_name:             ctx["drug_name"]   = req.drug_name
    if req.phase:                 ctx["phase"]       = req.phase
    if req.condition:             ctx["condition"]   = req.condition
    if req.sponsor:               ctx["sponsor"]     = req.sponsor

    # ── Tier 1 ────────────────────────────────────────────────────────────────
    if req.phase:
        ctx["_t1_phases"] = [req.phase]
    if req.enrollment is not None:
        ctx["_t1_enrollment_actual"]    = req.enrollment
    if req.enrollment_type:
        ctx["_t1_enrollment_type"]      = req.enrollment_type
    if req.allocation:
        ctx["_t1_allocation"]           = req.allocation
    if req.intervention_model:
        ctx["_t1_intervention_model"]   = req.intervention_model
    if req.primary_purpose:
        ctx["_t1_primary_purpose"]      = req.primary_purpose
    if req.study_type:
        ctx["_t1_study_type"]           = req.study_type
    if req.trial_duration_days is not None:
        ctx["_t1_trial_duration_days"]  = req.trial_duration_days
    if req.sponsor_class:
        ctx["_t1_sponsor_class"]        = req.sponsor_class
    if req.responsible_party_type:
        ctx["_t1_responsible_party_type"] = req.responsible_party_type
    if req.eligibility_criteria_count is not None:
        ctx["_t1_eligibility_criteria_count"] = req.eligibility_criteria_count
    if req.num_sites is not None:
        ctx["_t1_num_sites"]            = req.num_sites
    if req.is_fda_regulated_drug is not None:
        ctx["_t1_is_fda_regulated_drug"] = req.is_fda_regulated_drug
    if req.is_rare_disease is not None:
        ctx["_t1_is_rare_disease"]      = req.is_rare_disease
    if req.is_oncology is not None:
        ctx["_t1_is_oncology"]          = req.is_oncology
    if req.is_cns is not None:
        ctx["_t1_is_cns"]               = req.is_cns
    if req.intervention_type:
        ctx["_t1_intervention_type"]    = req.intervention_type
    if req.intervention_description:
        ctx["_t1_intervention_description"] = req.intervention_description
    if req.num_arms is not None:
        ctx["_t1_num_arms"]             = req.num_arms
    if req.primary_outcome_measures:
        ctx["_t1_primary_outcome_measures"] = req.primary_outcome_measures
    if req.secondary_outcome_count is not None:
        ctx["_t1_secondary_outcome_count"] = req.secondary_outcome_count
    if req.masking:
        ctx["_t1_masking"]              = req.masking

    # ── Tier 2 ────────────────────────────────────────────────────────────────
    if req.has_expanded_access is not None:
        ctx["_t2_has_expanded_access"]  = req.has_expanded_access
    if req.collaborator_count is not None:
        ctx["_t2_collaborator_count"]   = req.collaborator_count
    if req.collaborator_names:
        ctx["_t2_collaborator_names"]   = req.collaborator_names
    if req.publication_count is not None:
        ctx["_t2_publication_count"]    = req.publication_count
    if req.has_results is not None:
        ctx["_t2_has_results"]          = req.has_results
    if req.related_studies_count is not None:
        ctx["_t2_related_studies_count"] = req.related_studies_count
    if req.detailed_description:
        ctx["_t2_detailed_description"] = req.detailed_description

    # ── Tier 3 ────────────────────────────────────────────────────────────────
    if req.has_results_section is not None:
        ctx["_t3_has_results_section"]  = req.has_results_section
    if req.total_started is not None:
        ctx["_t3_total_started"]        = req.total_started
    if req.total_completed is not None:
        ctx["_t3_total_completed"]      = req.total_completed
    if req.completion_rate is not None:
        ctx["_t3_completion_rate"]      = req.completion_rate
    if req.sae_count is not None:
        ctx["_t3_sae_count"]            = req.sae_count
    if req.sae_rate is not None:
        ctx["_t3_sae_rate"]             = req.sae_rate
    if req.death_count is not None:
        ctx["_t3_death_count"]          = req.death_count

    return ctx


# ─── Warning Generator ────────────────────────────────────────────────────────

def _build_warning(data_confidence: str, ctx: Dict[str, Any]) -> Optional[str]:
    """Return a warning string when confidence is low due to missing context."""
    if data_confidence == "high":
        return None

    provided_fields = len([v for v in ctx.values() if v is not None])

    if data_confidence == "low":
        return (
            f"Score based on minimal context ({provided_fields} fields provided). "
            "Provide sponsor_class, enrollment, num_sites, trial_duration_days, "
            "is_rare_disease, and allocation for a more accurate score."
        )
    elif data_confidence == "medium":
        return (
            "Score based on partial context. Adding Tier 2 fields "
            "(has_expanded_access, collaborator_count, publication_count, has_results) "
            "will improve accuracy."
        )
    return None


# ─── Endpoint ─────────────────────────────────────────────────────────────────

@router.post("/", response_model=ClassifyResponse)
def classify_termination_reason(request: ClassifyRequest):
    """
    Classify a clinical trial termination reason with three-tier salvageability scoring.

    Minimum required: why_stopped
    Better results: add Tier 1 fields (sponsor_class, enrollment, phase, num_sites, etc.)
    Best results: add Tier 2 + Tier 3 fields when available

    Returns category, score (0-100), recommendations, data_confidence (low/medium/high),
    full score breakdown, and a warning if context is insufficient.
    """
    ctx = _build_context_from_request(request)

    category, score, recommendations, data_confidence, score_breakdown = full_analysis(
        request.why_stopped,
        trial_context=ctx,
    )

    warning = _build_warning(data_confidence, ctx)

    return ClassifyResponse(
        why_stopped=request.why_stopped,
        failure_category=category,
        salvageability_score=score,
        recommended_actions=recommendations,
        data_confidence=data_confidence,
        score_breakdown=score_breakdown,
        warning=warning,
    )