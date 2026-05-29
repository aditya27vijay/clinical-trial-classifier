"""
Three-Tier Salvageability Scorer — v2
Tier 1 (60%) — Protocol fields with category multiplier
Tier 2 (25%) — Contextual enrichment
Tier 3 (15%) — Results data (override when present)
+ LLM signal adjustments applied post-combination
+ Confidence-weighted category multiplier blending
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Category Multipliers ──────────────────────────────────────────────────────
# Applied to raw Tier 1 score. Reflects how salvageable the science is
# given the reason it failed.

CATEGORY_MULTIPLIERS = {
    "Business termination":  1.00,  # Science untested, full protocol score preserved
    "Recruitment failure":   0.90,  # Fixable operational problem, minor penalty
    "Operational issue":     0.85,  # Fixable, minor penalty
    "Endpoint failure":      0.65,  # Science partially tested, moderate penalty
    "Unknown":               0.60,  # Uncertainty penalty
    "Lack of efficacy":      0.35,  # Drug failed, heavy penalty
    "Toxicity":              0.25,  # Drug caused harm, severe penalty
}

UNKNOWN_MULTIPLIER = 0.60
CONFIDENCE_FULL_TRUST = 0.75
CONFIDENCE_BLEND_FLOOR = 0.15


# ─── Tier 1 Component Scoring ─────────────────────────────────────────────────

def _score_phase(ctx: Dict[str, Any]) -> float:
    phases = ctx.get("_t1_phases", [])
    if not phases:
        return 0.0
    phase_str = " ".join([p.lower() for p in phases])
    if "early" in phase_str:
        return 15.0
    if "phase 1" in phase_str or "phase1" in phase_str:
        return 12.0
    if "phase 2" in phase_str or "phase2" in phase_str:
        return 8.0
    if "phase 3" in phase_str or "phase3" in phase_str:
        return 4.0
    return 5.0  # phase listed but unrecognised string


def _score_enrollment(ctx: Dict[str, Any]) -> float:
    enrollment = ctx.get("_t1_enrollment_actual")
    enrollment_type = ctx.get("_t1_enrollment_type")
    if not enrollment:
        return 0.0
    if enrollment > 200:
        score = 12.0
    elif enrollment > 100:
        score = 10.0
    elif enrollment > 50:
        score = 7.0
    elif enrollment > 20:
        score = 4.0
    elif enrollment > 5:
        score = 2.0
    else:
        score = 0.0
    # Halve if ANTICIPATED — it's a target, not reality
    if enrollment_type == "ANTICIPATED":
        score *= 0.5
    return score


def _score_duration(ctx: Dict[str, Any]) -> float:
    days = ctx.get("_t1_trial_duration_days")
    if days is None:
        return 0.0
    if days > 730:
        return 12.0
    if days > 365:
        return 10.0
    if days > 180:
        return 6.0
    if days > 30:
        return 3.0
    return 0.0


def _score_sponsor(ctx: Dict[str, Any]) -> float:
    sponsor_class = ctx.get("_t1_sponsor_class")
    if sponsor_class == "INDUSTRY":
        return 10.0
    if sponsor_class == "NIH":
        return 7.0
    if sponsor_class == "OTHER":
        return 4.0
    return 0.0


def _score_sites(ctx: Dict[str, Any]) -> float:
    num_sites = ctx.get("_t1_num_sites", 0)
    if num_sites > 50:
        return 8.0
    if num_sites > 20:
        return 6.0
    if num_sites > 5:
        return 4.0
    if num_sites > 2:
        return 2.0
    if num_sites == 1:
        return 1.0
    return 0.0


def _score_intervention_model(ctx: Dict[str, Any]) -> float:
    model = ctx.get("_t1_intervention_model")
    if model == "PARALLEL":
        return 8.0
    if model == "CROSSOVER":
        return 7.0
    if model == "FACTORIAL":
        return 6.0
    if model == "SINGLE_GROUP":
        return 3.0
    if model:
        return 4.0  # Known but unrecognised
    return 0.0


def _score_fda(ctx: Dict[str, Any]) -> float:
    if ctx.get("_t1_is_fda_regulated_drug", False):
        return 6.0
    if ctx.get("_t1_is_fda_regulated_device", False):
        return 4.0
    return 0.0


def _score_disease_area(ctx: Dict[str, Any]) -> float:
    if ctx.get("_t1_is_oncology", False) or ctx.get("_t1_is_rare_disease", False):
        return 10.0
    if ctx.get("_t1_is_cns", False):
        return 8.0
    # Check if any condition is set at all
    if ctx.get("condition") or ctx.get("_t1_condition_meshes"):
        return 4.0
    return 2.0


def _score_randomization(ctx: Dict[str, Any]) -> float:
    allocation = ctx.get("_t1_allocation")
    if allocation == "RANDOMIZED":
        return 6.0
    if allocation == "NON_RANDOMIZED":
        return 2.0
    return 0.0


def _score_secondary_outcomes(ctx: Dict[str, Any]) -> float:
    count = ctx.get("_t1_secondary_outcome_count", 0)
    if count >= 6:
        return 3.0
    if count >= 3:
        return 2.0
    if count >= 1:
        return 1.0
    return 0.0


# ─── Category Multiplier with Confidence Blending ─────────────────────────────

def _get_blended_multiplier(category: str, confidence: float) -> float:
    """
    When Ollama confidence is low, the category may be wrong.
    Blend the category multiplier toward the Unknown multiplier (0.60)
    proportionally as confidence drops below 0.40.
    At confidence >= 0.75: use category multiplier fully.
    At confidence == 0.15: almost fully blended to Unknown.
    """
    base_multiplier = CATEGORY_MULTIPLIERS.get(category, UNKNOWN_MULTIPLIER)

    if confidence >= CONFIDENCE_FULL_TRUST:
        return base_multiplier

    # Linear blend factor: 0.0 at floor, 1.0 at full trust
    blend = max(0.0, (confidence - CONFIDENCE_BLEND_FLOOR) /
                     (CONFIDENCE_FULL_TRUST - CONFIDENCE_BLEND_FLOOR))

    blended = base_multiplier * blend + UNKNOWN_MULTIPLIER * (1.0 - blend)
    logger.debug(
        f"[Multiplier] cat={category} conf={confidence:.2f} "
        f"base={base_multiplier} blended={blended:.3f}"
    )
    return blended


# ─── Tier 1: Protocol Scoring ─────────────────────────────────────────────────

# Raw component max total ≈ 77 (15+12+12+10+8+8+6+10+6+3 = 90 theoretical max,
# but realistically ~77 for a well-run trial). Scale to 60 via multiplier.
TIER1_RAW_SCALE = 77.0
TIER1_MAX = 60.0


def score_tier1_protocol(
    ctx: Dict[str, Any],
    category: str,
    confidence: float,
) -> Tuple[float, Dict[str, float]]:
    """
    Score protocol fields and apply category multiplier.
    Returns (score capped at 60, components dict).
    """
    components = {
        "phase":               _score_phase(ctx),
        "enrollment":          _score_enrollment(ctx),
        "duration":            _score_duration(ctx),
        "sponsor_class":       _score_sponsor(ctx),
        "sites":               _score_sites(ctx),
        "intervention_model":  _score_intervention_model(ctx),
        "fda_regulation":      _score_fda(ctx),
        "disease_area":        _score_disease_area(ctx),
        "randomization":       _score_randomization(ctx),
        "secondary_outcomes":  _score_secondary_outcomes(ctx),
    }

    raw_sum = sum(components.values())

    # Scale raw sum to 60-point tier maximum
    scaled = (raw_sum / TIER1_RAW_SCALE) * TIER1_MAX

    # Apply category multiplier (confidence-blended)
    multiplier = _get_blended_multiplier(category, confidence)
    final = scaled * multiplier

    logger.debug(
        f"[Tier1] raw={raw_sum:.1f} scaled={scaled:.1f} "
        f"multiplier={multiplier:.3f} final={final:.1f}"
    )
    return min(TIER1_MAX, final), components


# ─── Tier 2: Contextual Enrichment ───────────────────────────────────────────

TIER2_MAX = 25.0


def score_tier2_context(
    ctx: Dict[str, Any],
) -> Tuple[float, Dict[str, float], List[str]]:
    """
    Score contextual enrichment signals.
    Returns (score capped at 25, components, signals_present).
    """
    score = 0.0
    components = {}
    signals = []

    per_signal = 5.0  # Each signal worth up to 5 points (5 signals × 5 = 25)

    # Expanded access — strong commercial/scientific interest signal
    if ctx.get("_t2_has_expanded_access", False):
        score += per_signal
        components["expanded_access"] = per_signal
        signals.append("expanded_access")
    else:
        components["expanded_access"] = 0.0

    # Collaborators — more institutions = more credibility and resources
    collab_count = ctx.get("_t2_collaborator_count", 0)
    if collab_count > 0:
        collab_score = min(per_signal, 2.0 + collab_count)
        score += collab_score
        components["collaborators"] = collab_score
        signals.append("collaborators")
    else:
        components["collaborators"] = 0.0

    # Publications (RESULT type) — drug generated publishable data
    pub_count = ctx.get("_t2_publication_count", 0)
    if pub_count > 0:
        pub_score = min(per_signal, 1.0 + pub_count)
        score += pub_score
        components["publications"] = pub_score
        signals.append("publications")
    else:
        components["publications"] = 0.0

    # Related studies — drug is being investigated elsewhere
    related = ctx.get("_t2_related_studies_count", 0)
    if related > 0:
        related_score = min(per_signal, 1.0 + related)
        score += related_score
        components["related_studies"] = related_score
        signals.append("related_studies")
    else:
        components["related_studies"] = 0.0

    # Results posted — trial generated enough data to report
    if ctx.get("_t2_has_results", False):
        score += per_signal
        components["results_posted"] = per_signal
        signals.append("results_posted")
    else:
        components["results_posted"] = 0.0

    final = min(TIER2_MAX, score)
    logger.debug(f"[Tier2] score={final:.1f} signals={signals}")
    return final, components, signals


# ─── Tier 3: Results Data ─────────────────────────────────────────────────────

TIER3_MAX = 15.0


def score_tier3_results(
    ctx: Dict[str, Any],
) -> Tuple[float, Dict[str, float], bool]:
    """
    Score from actual results data. Ground truth when available.
    Returns (score, components, is_override).
    """
    if not ctx.get("_t3_has_results_section", False):
        return 0.0, {}, False

    score = 0.0
    components = {}

    # Completion rate — higher is better (0.0–1.0 → 0–8 points)
    completion_rate = ctx.get("_t3_completion_rate")
    if completion_rate is not None:
        c_score = completion_rate * 8.0
        components["completion_rate"] = c_score
        score += c_score

    # SAE rate — lower is better (inverted)
    sae_rate = ctx.get("_t3_sae_rate")
    if sae_rate is not None:
        sae_score = max(0.0, 5.0 - (sae_rate * 10.0))
        components["sae_rate"] = sae_score
        score += sae_score

    # Deaths — each death heavily penalises (-2 per death)
    death_count = ctx.get("_t3_death_count", 0)
    if death_count > 0:
        death_penalty = max(-10.0, -2.0 * death_count)
        components["deaths"] = death_penalty
        score += death_penalty

    # Primary outcomes reported — data exists to analyse
    primary_reported = ctx.get("_t3_primary_outcomes_results", 0)
    if primary_reported > 0:
        o_score = min(2.0, float(primary_reported))
        components["outcomes_reported"] = o_score
        score += o_score

    final = max(0.0, min(TIER3_MAX, score))
    logger.debug(f"[Tier3] score={final:.1f} override=True")
    return final, components, True


# ─── LLM Signal Adjustments ───────────────────────────────────────────────────

def _apply_llm_signals(base_score: float, llm_result: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
    """
    Apply LLM-extracted signals as post-combination adjustments.
    These are applied AFTER tier combination, before final capping.
    """
    adjustments = {}
    delta = 0.0

    # Partial efficacy signal — drug showed something somewhere
    if llm_result.get("partial_efficacy_signal", False):
        adjustments["partial_efficacy"] = +10.0
        delta += 10.0

    # Severity of safety events
    severity = llm_result.get("severity", "none")
    if severity == "severe":
        adjustments["severity"] = -20.0
        delta -= 20.0
    elif severity == "moderate":
        adjustments["severity"] = -10.0
        delta -= 10.0
    elif severity == "mild":
        adjustments["severity"] = -3.0
        delta -= 3.0
    else:
        adjustments["severity"] = 0.0

    # Early phase — more room to optimize
    if llm_result.get("early_phase", False):
        adjustments["early_phase"] = +5.0
        delta += 5.0

    # Results data from LLM perspective
    if llm_result.get("has_results_data", False):
        adjustments["has_results_data"] = +8.0
        delta += 8.0

    # Large unmet need — commercial and scientific motivation to rescue
    if llm_result.get("large_unmet_need", False):
        adjustments["large_unmet_need"] = +5.0
        delta += 5.0

    # LLM expert modifier — capped ±20
    llm_modifier = llm_result.get("salvageability_modifier", 0)
    capped = max(-20, min(20, int(llm_modifier)))
    if capped != 0:
        adjustments["llm_expert_modifier"] = float(capped)
        delta += capped

    logger.debug(f"[LLM signals] delta={delta:+.1f} adjustments={adjustments}")
    return base_score + delta, adjustments


# ─── Data Confidence ──────────────────────────────────────────────────────────

def compute_data_confidence(signals: List[str], tier3_override: bool) -> str:
    if tier3_override:
        return "high"
    if len(signals) >= 3:
        return "high"
    if len(signals) >= 1:
        return "medium"
    return "low"


# ─── Main Entry Point ─────────────────────────────────────────────────────────

def compute_three_tier_score(
    category:   str,
    confidence: float,
    llm_result: Dict[str, Any],
    ctx:        Dict[str, Any],
) -> Tuple[int, str, Dict[str, Any]]:
    """
    Compute final salvageability score.
    Returns (final_score, data_confidence, full_breakdown).
    """

    # ── Tier 1: Protocol (60% max) ─────────────────────────────────────────────
    tier1_score, tier1_components = score_tier1_protocol(ctx, category, confidence)

    # ── Tier 2: Context (25% max) ──────────────────────────────────────────────
    tier2_score, tier2_components, tier2_signals = score_tier2_context(ctx)

    # ── Tier 3: Results (15% max, override) ────────────────────────────────────
    tier3_score, tier3_components, tier3_override = score_tier3_results(ctx)

    # ── Combine three tiers ────────────────────────────────────────────────────
    combined = tier1_score + tier2_score + tier3_score

    # ── Apply LLM signals post-combination ────────────────────────────────────
    adjusted, llm_adjustments = _apply_llm_signals(combined, llm_result)

    final_score = max(0, min(100, int(adjusted)))
    data_confidence = compute_data_confidence(tier2_signals, tier3_override)

    # ── Build breakdown for transparency ──────────────────────────────────────
    multiplier = _get_blended_multiplier(category, confidence)
    breakdown = {
        "tier1": {
            "score":       round(tier1_score, 1),
            "max":         60,
            "weight":      "60%",
            "multiplier":  round(multiplier, 3),
            "components":  {k: round(v, 1) for k, v in tier1_components.items()},
        },
        "tier2": {
            "score":       round(tier2_score, 1),
            "max":         25,
            "weight":      "25%",
            "components":  {k: round(v, 1) for k, v in tier2_components.items()},
            "signals":     tier2_signals,
        },
        "tier3": {
            "score":       round(tier3_score, 1),
            "max":         15,
            "weight":      "15%",
            "components":  {k: round(v, 1) for k, v in tier3_components.items()},
            "is_override": tier3_override,
        },
        "llm_adjustments": {k: round(v, 1) for k, v in llm_adjustments.items()},
        "combined_pre_llm": round(combined, 1),
        "final":           final_score,
        "data_confidence": data_confidence,
        "category_multiplier": round(multiplier, 3),
        "ollama_confidence":   round(confidence, 3),
    }

    logger.info(
        f"[Score] final={final_score} | tier1={tier1_score:.1f} "
        f"tier2={tier2_score:.1f} tier3={tier3_score:.1f} "
        f"llm_delta={adjusted - combined:+.1f} | "
        f"cat={category} mult={multiplier:.2f} conf={confidence:.2f} | "
        f"data_confidence={data_confidence}"
    )

    return final_score, data_confidence, breakdown