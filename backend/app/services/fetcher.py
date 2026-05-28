"""
ClinicalTrials.gov API Integration
Fetches terminated, withdrawn, and suspended clinical trials with full context.
"""

import requests
import logging
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
FAILED_STATUSES = ["TERMINATED", "WITHDRAWN", "SUSPENDED"]


def _normalize_trial(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize a raw ClinicalTrials.gov API v2 response into our schema."""
    try:
        protocol       = raw.get("protocolSection", {})
        id_module      = protocol.get("identificationModule", {})
        status_module  = protocol.get("statusModule", {})
        conditions_mod = protocol.get("conditionsModule", {})
        arms_module    = protocol.get("armsInterventionsModule", {})
        design_module  = protocol.get("designModule", {})
        sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
        outcomes_mod   = protocol.get("outcomesModule", {})
        desc_module    = protocol.get("descriptionModule", {})
        eligibility    = protocol.get("eligibilityModule", {})
        contacts_mod   = protocol.get("contactsLocationsModule", {})
        results        = raw.get("resultsSection", {})

        nct_id = id_module.get("nctId", "")
        if not nct_id:
            return None

        # ── Interventions ─────────────────────────────────────────────────────
        interventions = arms_module.get("interventions", [])
        drug_name = None
        intervention_type = None
        intervention_description = None
        all_interventions = []

        for iv in interventions:
            iv_type = iv.get("type", "").upper()
            iv_name = iv.get("name", "")
            all_interventions.append(f"{iv_name} ({iv_type})")
            if iv_type in ("DRUG", "BIOLOGICAL", "COMBINATION_PRODUCT", "GENETIC"):
                if not drug_name:
                    drug_name = iv_name
                    intervention_type = iv_type
                    intervention_description = iv.get("description")

        if not drug_name and interventions:
            drug_name = interventions[0].get("name")
            intervention_type = interventions[0].get("type")
            intervention_description = interventions[0].get("description")

        # ── Phase ─────────────────────────────────────────────────────────────
        phases = design_module.get("phases", [])
        phase = ", ".join(phases) if phases else None

        # ── Conditions ────────────────────────────────────────────────────────
        conditions = conditions_mod.get("conditions", [])
        condition = "; ".join(conditions[:3]) if conditions else None

        # ── Enrollment ────────────────────────────────────────────────────────
        enrollment_info = design_module.get("enrollmentInfo", {})
        enrollment = enrollment_info.get("count")
        enrollment_type = enrollment_info.get("type")  # ACTUAL or ANTICIPATED

        # ── Study design details ──────────────────────────────────────────────
        design_info    = design_module.get("designInfo", {})
        study_type     = design_module.get("studyType")
        allocation     = design_info.get("allocation")        # RANDOMIZED / NON_RANDOMIZED
        masking        = design_info.get("maskingInfo", {}).get("masking")  # NONE / SINGLE / DOUBLE etc
        primary_purpose = design_info.get("primaryPurpose")  # TREATMENT / PREVENTION etc
        num_arms       = len(arms_module.get("armGroups", []))

        # ── Outcomes ──────────────────────────────────────────────────────────
        primary_outcomes = outcomes_mod.get("primaryOutcomes", [])
        primary_outcome_measures = [o.get("measure", "") for o in primary_outcomes[:2]]

        # ── Dates ─────────────────────────────────────────────────────────────
        start_date      = status_module.get("startDateStruct", {}).get("date")
        completion_date = status_module.get("completionDateStruct", {}).get("date")
        results_date    = status_module.get("resultsFirstPostDateStruct", {}).get("date")

        # ── Has results posted ────────────────────────────────────────────────
        has_results = bool(results) or bool(results_date)

        # ── Sponsor & collaborators ───────────────────────────────────────────
        sponsor = sponsor_module.get("leadSponsor", {}).get("name")
        sponsor_class = sponsor_module.get("leadSponsor", {}).get("class")  # INDUSTRY / NIH / OTHER
        collaborators = [c.get("name") for c in sponsor_module.get("collaborators", [])[:2]]

        # ── Sites ─────────────────────────────────────────────────────────────
        locations = contacts_mod.get("locations", [])
        num_sites = len(locations)

        # ── Brief summary ─────────────────────────────────────────────────────
        brief_summary = desc_module.get("briefSummary", "")
        # Trim to 300 chars for LLM context without blowing token budget
        if brief_summary:
            brief_summary = brief_summary[:300].strip()

        return {
            # ── Core fields (stored in DB) ────────────────────────────────────
            "nct_id":           nct_id,
            "title":            id_module.get("briefTitle"),
            "condition":        condition,
            "drug_name":        drug_name,
            "phase":            phase,
            "overall_status":   status_module.get("overallStatus"),
            "why_stopped":      status_module.get("whyStopped"),
            "sponsor":          sponsor,
            "start_date":       start_date,
            "completion_date":  completion_date,
            "enrollment":       enrollment,

            # ── Extended context fields (used by LLM, not all stored) ─────────
            "_intervention_type":         intervention_type,
            "_intervention_description":  intervention_description,
            "_all_interventions":         "; ".join(all_interventions),
            "_enrollment_type":           enrollment_type,
            "_study_type":                study_type,
            "_allocation":                allocation,
            "_masking":                   masking,
            "_primary_purpose":           primary_purpose,
            "_num_arms":                  num_arms,
            "_primary_outcomes":          "; ".join(primary_outcome_measures),
            "_has_results":               has_results,
            "_sponsor_class":             sponsor_class,
            "_collaborators":             "; ".join(collaborators),
            "_num_sites":                 num_sites,
            "_brief_summary":             brief_summary,
        }

    except Exception as e:
        logger.error(f"Error normalizing trial: {e}")
        return None


def fetch_failed_trials(
    max_results: int = 200,
    page_size: int = 100,
    condition: Optional[str] = None,
    intervention: Optional[str] = None,
) -> List[Dict[str, Any]]:
    all_trials = []
    next_page_token = None

    while len(all_trials) < max_results:
        params: Dict[str, Any] = {
            "filter.overallStatus": "|".join(FAILED_STATUSES),
            "pageSize": min(page_size, max_results - len(all_trials)),
            "format": "json",
        }
        if condition:
            params["query.cond"] = condition
        if intervention:
            params["query.intr"] = intervention
        if next_page_token:
            params["pageToken"] = next_page_token

        try:
            resp = requests.get(BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            logger.error(f"ClinicalTrials.gov API error: {e}")
            break

        studies = data.get("studies", [])
        if not studies:
            break

        for raw in studies:
            normalized = _normalize_trial(raw)
            if normalized:
                all_trials.append(normalized)

        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break

    logger.info(f"Fetched {len(all_trials)} trials from ClinicalTrials.gov")
    return all_trials


def fetch_trial_by_nct(nct_id: str) -> Optional[Dict[str, Any]]:
    url = f"{BASE_URL}/{nct_id}"
    try:
        resp = requests.get(url, params={"format": "json"}, timeout=15)
        resp.raise_for_status()
        return _normalize_trial(resp.json())
    except requests.RequestException as e:
        logger.error(f"Error fetching {nct_id}: {e}")
        return None