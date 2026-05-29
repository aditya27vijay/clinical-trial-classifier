"""
ClinicalTrials.gov API Integration — Full Data Extraction
Fetches all Tier 1, 2, and 3 fields for three-tier salvageability scoring.
"""

import requests
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
FAILED_STATUSES = ["TERMINATED", "WITHDRAWN", "SUSPENDED"]


def _safe_date_parse(date_str: Optional[str]) -> Optional[str]:
    """Parse date string, return as-is if valid ISO format."""
    if not date_str:
        return None
    return date_str


def _compute_trial_duration_days(start_date: Optional[str], completion_date: Optional[str]) -> Optional[int]:
    """Compute trial duration in days from start to completion/termination."""
    if not start_date or not completion_date:
        return None
    try:
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end = datetime.fromisoformat(completion_date.replace('Z', '+00:00'))
        return (end - start).days
    except Exception:
        return None


def _count_eligibility_criteria(criteria_text: Optional[str]) -> int:
    """Count approximate number of eligibility criteria from text."""
    if not criteria_text:
        return 0
    # Simple heuristic: count lines with "and", "or", dashes
    lines = criteria_text.split('\n')
    return len([l for l in lines if l.strip() and any(x in l.lower() for x in ['and', 'or', '-'])])


def _extract_mesh_terms(mesh_list: List[Dict[str, Any]]) -> tuple:
    """Extract MeSH terms and detect rare disease, oncology, CNS."""
    terms = []
    term_ids = []
    is_rare = False
    is_oncology = False
    is_cns = False

    rare_keywords = ['rare', 'orphan', 'genetic disorder', 'inborn error']
    oncology_keywords = ['neoplasm', 'cancer', 'carcinoma', 'tumor', 'lymphoma', 'leukemia', 'myeloma']
    cns_keywords = ['nervous system', 'brain', 'neurolog', 'psychiatric', 'alzheimer', 'parkinson', 'epileps']

    for mesh in mesh_list:
        term = mesh.get('term', '')
        mesh_id = mesh.get('id', '')
        terms.append(term)
        term_ids.append(mesh_id)

        term_lower = term.lower()
        if any(kw in term_lower for kw in rare_keywords):
            is_rare = True
        if any(kw in term_lower for kw in oncology_keywords):
            is_oncology = True
        if any(kw in term_lower for kw in cns_keywords):
            is_cns = True

    return terms, term_ids, is_rare, is_oncology, is_cns


def _compute_enrollment_ratio(actual: Optional[int], anticipated_type: Optional[str]) -> Optional[float]:
    """
    Compute enrollment ratio (actual / anticipated).
    ClinicalTrials.gov doesn't explicitly store anticipated, but we can infer from type.
    For now return None if we can't compute.
    """
    if not actual:
        return None
    # TODO: could enhance by fetching target enrollment from protocol if available
    return None


def _compute_sae_rate(sae_count: int, enrollment: Optional[int]) -> Optional[float]:
    """Compute serious adverse event rate."""
    if not enrollment or enrollment == 0:
        return None
    return sae_count / enrollment


def _compute_completion_rate(completed: int, started: int) -> Optional[float]:
    """Compute participant completion rate."""
    if started == 0:
        return None
    return completed / started


def _normalize_trial(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize raw ClinicalTrials.gov API response — extract ALL Tier 1, 2, 3 fields."""
    try:
        protocol       = raw.get("protocolSection", {})
        id_module      = protocol.get("identificationModule", {})
        status_module  = protocol.get("statusModule", {})
        design_module  = protocol.get("designModule", {})
        conditions_mod = protocol.get("conditionsModule", {})
        arms_module    = protocol.get("armsInterventionsModule", {})
        sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
        outcomes_mod   = protocol.get("outcomesModule", {})
        desc_module    = protocol.get("descriptionModule", {})
        eligibility    = protocol.get("eligibilityModule", {})
        contacts_mod   = protocol.get("contactsLocationsModule", {})
        oversight_mod  = protocol.get("oversightModule", {})
        references_mod = protocol.get("referencesModule", {})
        derived        = raw.get("derivedSection", {})
        results        = raw.get("resultsSection", {})

        nct_id = id_module.get("nctId", "")
        if not nct_id:
            return None

        # ══════════════════════════════════════════════════════════════════════
        # TIER 1 — PROTOCOL FIELDS (ALWAYS AVAILABLE)
        # ══════════════════════════════════════════════════════════════════════

        # ── Basic ─────────────────────────────────────────────────────────────
        title = id_module.get("briefTitle")
        phases = design_module.get("phases", [])
        phase_str = ", ".join(phases) if phases else None

        # ── Enrollment ────────────────────────────────────────────────────────
        enrollment_info = design_module.get("enrollmentInfo", {})
        enrollment_actual = enrollment_info.get("count")
        enrollment_type = enrollment_info.get("type")  # ACTUAL or ANTICIPATED

        # ── Dates ─────────────────────────────────────────────────────────────
        start_date = status_module.get("startDateStruct", {}).get("date")
        primary_completion_date = status_module.get("primaryCompletionDateStruct", {}).get("date")
        trial_duration_days = _compute_trial_duration_days(start_date, primary_completion_date)

        # ── Design ────────────────────────────────────────────────────────────
        design_info = design_module.get("designInfo", {})
        allocation = design_info.get("allocation")  # RANDOMIZED / NON_RANDOMIZED
        intervention_model = design_info.get("interventionModel")  # PARALLEL / SINGLE_GROUP etc
        primary_purpose = design_info.get("primaryPurpose")  # TREATMENT / PREVENTION
        masking = design_info.get("maskingInfo", {}).get("masking")
        study_type = design_module.get("studyType")
        num_arms = len(arms_module.get("armGroups", []))

        # ── Conditions & MeSH ─────────────────────────────────────────────────
        conditions = conditions_mod.get("conditions", [])
        condition_str = "; ".join(conditions[:3]) if conditions else None
        condition_meshes, condition_mesh_ids, is_rare_disease, is_oncology, is_cns = _extract_mesh_terms(
            derived.get("conditionBrowseModule", {}).get("meshes", [])
        )

        # ── Interventions & MeSH ──────────────────────────────────────────────
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

        intervention_meshes, intervention_mesh_ids = [], []
        intervention_mesh_raw = derived.get("interventionBrowseModule", {}).get("meshes", [])
        if intervention_mesh_raw:
            intervention_meshes = [m.get("term", "") for m in intervention_mesh_raw]
            intervention_mesh_ids = [m.get("id", "") for m in intervention_mesh_raw]

        # ── Eligibility ───────────────────────────────────────────────────────
        criteria_text = eligibility.get("eligibilityCriteria", "")
        criteria_complexity = _count_eligibility_criteria(criteria_text)
        min_age = eligibility.get("minimumAge")
        max_age = eligibility.get("maximumAge")
        sex = eligibility.get("sex")

        # ── Sites & FDA ───────────────────────────────────────────────────────
        locations = contacts_mod.get("locations", [])
        num_sites = len(locations)

        is_fda_regulated_drug = oversight_mod.get("isFdaRegulatedDrug", False)
        is_fda_regulated_device = oversight_mod.get("isFdaRegulatedDevice", False)

        # ── Sponsor & Responsible Party ───────────────────────────────────────
        sponsor = sponsor_module.get("leadSponsor", {}).get("name")
        sponsor_class = sponsor_module.get("leadSponsor", {}).get("class")  # INDUSTRY / NIH / OTHER
        responsible_party_type = sponsor_module.get("responsibleParty", {}).get("type")

        # ── Outcomes ──────────────────────────────────────────────────────────
        primary_outcomes = outcomes_mod.get("primaryOutcomes", [])
        primary_outcome_measures = [o.get("measure", "") for o in primary_outcomes[:2]]
        secondary_outcomes = outcomes_mod.get("secondaryOutcomes", [])
        secondary_outcome_count = len(secondary_outcomes)

        # ══════════════════════════════════════════════════════════════════════
        # TIER 2 — CONTEXTUAL ENRICHMENT (SOMETIMES AVAILABLE)
        # ══════════════════════════════════════════════════════════════════════

        # ── Expanded Access ───────────────────────────────────────────────────
        has_expanded_access = oversight_mod.get("hasExpandedAccess", False)

        # ── Collaborators ─────────────────────────────────────────────────────
        collaborators = sponsor_module.get("collaborators", [])
        collaborator_count = len(collaborators)
        collaborator_names = [c.get("name", "") for c in collaborators[:3]]

        # ── References & Publications ─────────────────────────────────────────
        references = references_mod.get("references", [])
        publication_count = len([r for r in references if r.get("type") == "RESULT"])
        background_count = len([r for r in references if r.get("type") == "BACKGROUND"])
        pmids = [r.get("pmid") for r in references if r.get("pmid")]

        # ── See Also Links ────────────────────────────────────────────────────
        see_also_links = references_mod.get("seeAlsoLinks", [])
        related_studies_count = len(see_also_links)

        # ── Detailed Description ──────────────────────────────────────────────
        detailed_description = desc_module.get("detailedDescription", "")
        if detailed_description:
            detailed_description = detailed_description[:500].strip()

        # ── Results Posted ────────────────────────────────────────────────────
        has_results = bool(results)

        # ══════════════════════════════════════════════════════════════════════
        # TIER 3 — RESULTS DATA (RARELY AVAILABLE FOR TERMINATED)
        # ══════════════════════════════════════════════════════════════════════

        # ── Participant Flow ──────────────────────────────────────────────────
        participant_flow = results.get("participantFlowModule", {})
        flow_groups = participant_flow.get("groups", [])
        flow_periods = participant_flow.get("periods", [])

        total_started = 0
        total_completed = 0
        for period in flow_periods:
            for milestone in period.get("milestones", []):
                if milestone.get("type") == "STARTED":
                    total_started += sum(m.get("count", 0) for m in milestone.get("achievements", []))
                elif milestone.get("type") == "COMPLETED":
                    total_completed += sum(m.get("count", 0) for m in milestone.get("achievements", []))

        completion_rate = _compute_completion_rate(total_completed, total_started) if total_started > 0 else None

        # ── Serious Adverse Events ────────────────────────────────────────────
        adverse_events = results.get("adverseEventsModule", {})
        serious_events = adverse_events.get("seriousEvents", [])
        sae_count = len(serious_events)
        sae_affected_count = 0
        sae_at_risk_count = 0

        for event in serious_events:
            for stat in event.get("stats", []):
                sae_affected_count += stat.get("numAffected", 0)
                sae_at_risk_count += stat.get("numAtRisk", 0)

        sae_rate = _compute_sae_rate(sae_affected_count, enrollment_actual)

        # ── Deaths ────────────────────────────────────────────────────────────
        event_groups = adverse_events.get("eventGroups", [])
        death_count = 0
        for group in event_groups:
            death_count += group.get("deathsNumAffected", 0)

        # ── Other Adverse Events ──────────────────────────────────────────────
        other_events = adverse_events.get("otherEvents", [])
        other_ae_count = len(other_events)

        # ── Outcome Measures Results ──────────────────────────────────────────
        outcome_measures = results.get("outcomeMeasuresModule", {}).get("outcomeMeasures", [])
        primary_outcomes_results_count = len([o for o in outcome_measures if o.get("type") == "PRIMARY"])
        secondary_outcomes_results_count = len([o for o in outcome_measures if o.get("type") == "SECONDARY"])

        return {
            # Core DB fields
            "nct_id":             nct_id,
            "title":              title,
            "condition":          condition_str,
            "drug_name":          drug_name,
            "phase":              phase_str,
            "overall_status":     status_module.get("overallStatus"),
            "why_stopped":        status_module.get("whyStopped"),
            "sponsor":            sponsor,
            "start_date":         start_date,
            "completion_date":    primary_completion_date,
            "enrollment":         enrollment_actual,

            # ── TIER 1 (Protocol) ─────────────────────────────────────────────
            "_t1_phases":                     phases,
            "_t1_enrollment_actual":          enrollment_actual,
            "_t1_enrollment_type":            enrollment_type,
            "_t1_allocation":                 allocation,
            "_t1_intervention_model":         intervention_model,
            "_t1_primary_purpose":            primary_purpose,
            "_t1_study_type":                 study_type,
            "_t1_trial_duration_days":        trial_duration_days,
            "_t1_sponsor_class":              sponsor_class,
            "_t1_responsible_party_type":     responsible_party_type,
            "_t1_eligibility_criteria_count": criteria_complexity,
            "_t1_min_age":                    min_age,
            "_t1_max_age":                    max_age,
            "_t1_sex":                        sex,
            "_t1_num_sites":                  num_sites,
            "_t1_is_fda_regulated_drug":      is_fda_regulated_drug,
            "_t1_is_fda_regulated_device":    is_fda_regulated_device,
            "_t1_condition_meshes":           condition_meshes,
            "_t1_is_rare_disease":            is_rare_disease,
            "_t1_is_oncology":                is_oncology,
            "_t1_is_cns":                     is_cns,
            "_t1_intervention_type":          intervention_type,
            "_t1_intervention_description":   intervention_description,
            "_t1_intervention_meshes":        intervention_meshes,
            "_t1_num_arms":                   num_arms,
            "_t1_primary_outcome_measures":   primary_outcome_measures,
            "_t1_secondary_outcome_count":    secondary_outcome_count,
            "_t1_masking":                    masking,

            # ── TIER 2 (Contextual) ───────────────────────────────────────────
            "_t2_has_expanded_access":        has_expanded_access,
            "_t2_collaborator_count":         collaborator_count,
            "_t2_collaborator_names":         collaborator_names,
            "_t2_publication_count":          publication_count,
            "_t2_background_ref_count":       background_count,
            "_t2_pmids":                      pmids,
            "_t2_related_studies_count":      related_studies_count,
            "_t2_has_results":                has_results,
            "_t2_detailed_description":       detailed_description,

            # ── TIER 3 (Results) ───────────────────────────────────────────────
            "_t3_has_results_section":        bool(results),
            "_t3_total_started":              total_started,
            "_t3_total_completed":            total_completed,
            "_t3_completion_rate":            completion_rate,
            "_t3_sae_count":                  sae_count,
            "_t3_sae_affected_count":         sae_affected_count,
            "_t3_sae_rate":                   sae_rate,
            "_t3_death_count":                death_count,
            "_t3_other_ae_count":             other_ae_count,
            "_t3_primary_outcomes_results":   primary_outcomes_results_count,
            "_t3_secondary_outcomes_results": secondary_outcomes_results_count,

            # Computed fields
            "_enrollment_ratio":              _compute_enrollment_ratio(enrollment_actual, enrollment_type),
            "_sites_per_patient":             num_sites / enrollment_actual if enrollment_actual and enrollment_actual > 0 else None,
        }

    except Exception as e:
        logger.error(f"Error normalizing trial {nct_id}: {e}")
        return None


def fetch_failed_trials(
    max_results: int = 200,
    page_size: int = 100,
    condition: Optional[str] = None,
    intervention: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch failed trials with full Tier 1/2/3 context."""
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
    """Fetch single trial by NCT ID."""
    url = f"{BASE_URL}/{nct_id}"
    try:
        resp = requests.get(url, params={"format": "json"}, timeout=15)
        resp.raise_for_status()
        return _normalize_trial(resp.json())
    except requests.RequestException as e:
        logger.error(f"Error fetching {nct_id}: {e}")
        return None