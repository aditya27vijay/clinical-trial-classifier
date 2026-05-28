"""
Rule-based NLP Classification Engine
Classifies clinical trial termination reasons into standardized categories.
"""

import re
from typing import Tuple, List, Dict

# ─── Keyword Maps ────────────────────────────────────────────────────────────

CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "Lack of efficacy": [
        "lack of efficacy",
        "insufficient efficacy",
        "no efficacy",
        "lack efficacy",
        "failed to demonstrate efficacy",
        "did not meet.*endpoint",
        "futility",
        "no clinical benefit",
        "no benefit",
        "poor efficacy",
        "interim analysis.*efficacy",
        "efficacy not demonstrated",
        "no significant.*improvement",
        "no improvement",
        "no response",
        "failed to show",
        "did not show",
        "not effective",
        "ineffective",
    ],
    "Toxicity": [
        "toxicity",
        "toxic",
        "adverse event",
        "adverse effect",
        "safety concern",
        "safety issue",
        "safety signal",
        "serious adverse",
        "side effect",
        "tolerability",
        "not tolerated",
        "dose limiting",
        "hepatotoxic",
        "cardiotoxic",
        "neurotoxic",
        "overdose",
        "death",
        "fatal",
        "harm",
    ],
    "Recruitment failure": [
        "enrollment",
        "enrolment",
        "recruitment",
        "recruit",
        "insufficient.*patient",
        "lack of.*patient",
        "unable to enroll",
        "unable to recruit",
        "low accrual",
        "poor accrual",
        "accrual",
        "insufficient.*participant",
        "not enough.*subject",
        "patient availability",
        "slow enrollment",
        "slow recruitment",
        "inadequate enrollment",
    ],
    "Business termination": [
        "business decision",
        "business reason",
        "sponsor decision",
        "company decision",
        "strategic decision",
        "commercial reason",
        "financial reason",
        "funding",
        "budget",
        "reprioritization",
        "re-prioritization",
        "portfolio",
        "discontinued.*program",
        "program discontinu",
        "sponsor.*terminat",
        "company.*terminat",
        "no longer.*interest",
        "withdrawn by sponsor",
        "company withdraw",
    ],
    "Operational issue": [
        "operational",
        "logistical",
        "protocol deviation",
        "protocol amendment",
        "site.*clos",
        "investigator.*clos",
        "investigator withdrew",
        "manufacturing",
        "drug supply",
        "supply issue",
        "regulatory",
        "fda.*hold",
        "clinical hold",
        "ifd.*hold",
        "administrative",
        "technical issue",
        "data integrity",
        "gdp",
        "gmp",
    ],
    "Endpoint failure": [
        "primary endpoint",
        "secondary endpoint",
        "endpoint not met",
        "failed.*endpoint",
        "endpoint.*fail",
        "missed.*endpoint",
        "did not achieve.*endpoint",
        "interim.*endpoint",
        "surrogate endpoint",
        "composite endpoint",
    ],
}

# ─── Salvageability Scores ────────────────────────────────────────────────────

BASE_SCORES: Dict[str, int] = {
    "Business termination": 85,
    "Recruitment failure": 80,
    "Operational issue": 70,
    "Endpoint failure": 60,
    "Lack of efficacy": 25,
    "Toxicity": 20,
    "Unknown": 40,
}

# ─── Rescue Recommendations ───────────────────────────────────────────────────

RECOMMENDATIONS: Dict[str, List[str]] = {
    "Recruitment failure": [
        "Broaden inclusion/exclusion criteria to increase eligible population",
        "Expand to additional recruitment sites or geographies",
        "Leverage patient advocacy networks for targeted outreach",
        "Implement decentralized or hybrid trial design",
        "Revisit rare disease designations to access specialized cohorts",
    ],
    "Business termination": [
        "Evaluate out-licensing or partnership opportunities",
        "Review subgroup efficacy signals that may support repositioning",
        "Assess asset for rare disease or orphan drug designation",
        "Explore academic or non-profit sponsored continuation",
        "Consider sell-off to specialized biotech acquirers",
    ],
    "Lack of efficacy": [
        "Investigate biomarker-stratified patient subgroups",
        "Explore combination therapy approaches",
        "Evaluate alternative disease indications (drug repurposing)",
        "Re-examine dose-response relationships",
        "Reassess primary endpoint selection with clinical experts",
    ],
    "Toxicity": [
        "Investigate reduced or optimized dosing regimens",
        "Explore targeted/localized drug delivery mechanisms",
        "Evaluate prodrug strategies to improve tolerability",
        "Conduct deeper toxicogenomics analysis for susceptibility markers",
        "Assess risk/benefit in high-unmet-need populations",
    ],
    "Endpoint failure": [
        "Redesign trial with validated surrogate endpoints",
        "Seek FDA alignment via Type B/C meeting on endpoint strategy",
        "Explore patient-reported outcomes as alternative endpoints",
        "Conduct exploratory analyses on secondary/tertiary endpoints",
        "Consider adaptive trial designs in future protocols",
    ],
    "Operational issue": [
        "Resolve regulatory or manufacturing barriers before re-initiation",
        "Restructure trial operations with experienced CRO partner",
        "Review site selection criteria and investigator capabilities",
        "Implement robust supply chain and RTSM systems",
        "Conduct thorough root-cause analysis before resubmission",
    ],
    "Unknown": [
        "Request detailed trial records from sponsor or ClinicalTrials.gov",
        "Contact principal investigator for unpublished data",
        "Review associated publications or conference presentations",
        "Assess drug class peers for analogous failure patterns",
    ],
}


# ─── Core Functions ───────────────────────────────────────────────────────────

def classify_failure(why_stopped: str) -> str:
    """Classify a termination reason string into a standardized category."""
    if not why_stopped or not why_stopped.strip():
        return "Unknown"

    text = why_stopped.lower().strip()

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if re.search(keyword, text):
                return category

    return "Unknown"


def compute_salvageability(failure_category: str, why_stopped: str = "") -> int:
    """Compute salvageability score (0–100) based on failure category and context."""
    base = BASE_SCORES.get(failure_category, 40)

    # Context modifiers
    text = (why_stopped or "").lower()

    # Boost: early phase failures are more salvageable
    if "phase 1" in text or "phase i" in text:
        base = min(100, base + 5)

    # Penalize: severe or multiple safety events
    severe_terms = ["fatal", "death", "serious adverse", "multiple.*adverse", "severe toxicity"]
    for term in severe_terms:
        if re.search(term, text):
            base = max(0, base - 15)
            break

    # Boost: partial efficacy signals mentioned
    partial_terms = ["some efficacy", "partial response", "subgroup", "biomarker", "trend toward"]
    for term in partial_terms:
        if re.search(term, text):
            base = min(100, base + 10)
            break

    return base


def get_recommendations(failure_category: str) -> List[str]:
    """Return rescue strategy recommendations for a given failure category."""
    return RECOMMENDATIONS.get(failure_category, RECOMMENDATIONS["Unknown"])


def full_analysis(why_stopped: str) -> Tuple[str, int, List[str]]:
    """Run the full classification + scoring + recommendation pipeline."""
    category = classify_failure(why_stopped)
    score = compute_salvageability(category, why_stopped)
    recommendations = get_recommendations(category)
    return category, score, recommendations
