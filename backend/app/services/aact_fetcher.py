# backend/app/services/aact_fetcher.py

import os
import logging
from typing import List, Dict, Optional
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


class AACTFetcher:
    """Fetches terminated trials from the AACT PostgreSQL database."""

    def __init__(self, database_url: str = None, schema: str = None):
        self.database_url = database_url or os.getenv("AACT_DATABASE_URL")
        self.schema = schema or os.getenv("AACT_SCHEMA", "ctgov")
        if not self.database_url:
            raise ValueError("AACT_DATABASE_URL not set in environment")

        self.engine = create_engine(
            self.database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=2,
        )

    # -------------------------------------------------------------------------
    # Public: fetch terminated trials (basic fields only)
    # -------------------------------------------------------------------------

    def fetch_terminated_trials(
        self,
        max_results: int = 100,
        condition: str = None,
        intervention: str = None,
    ) -> List[Dict]:
        """
        Fetch terminated/withdrawn/suspended trials from AACT.
        Only selects columns that actually exist in ctgov.studies.
        """
        where_clauses = ["s.overall_status IN ('TERMINATED', 'WITHDRAWN', 'SUSPENDED')"]
        params: dict = {"max_results": max_results}

        if condition:
            where_clauses.append(
                "EXISTS (SELECT 1 FROM ctgov.conditions c "
                "WHERE c.nct_id = s.nct_id AND c.name ILIKE :condition)"
            )
            params["condition"] = f"%{condition}%"

        if intervention:
            where_clauses.append(
                "EXISTS (SELECT 1 FROM ctgov.interventions i "
                "WHERE i.nct_id = s.nct_id AND i.name ILIKE :intervention)"
            )
            params["intervention"] = f"%{intervention}%"

        where_sql = " AND ".join(where_clauses)

        query = f"""
            SELECT
                s.nct_id,
                s.brief_title,
                s.official_title,
                s.why_stopped,
                s.phase,
                s.study_type,
                s.enrollment,
                s.enrollment_type,
                s.start_date,
                s.completion_date,
                s.primary_completion_date,
                s.overall_status,
                s.source              AS sponsor_name,
                s.number_of_arms,
                s.is_fda_regulated_drug,
                s.is_fda_regulated_device,

                -- has_expanded_access lives in ctgov.expanded_access_infos
                COALESCE(s.has_expanded_access, false) AS has_expanded_access,

                -- has_results_section: check if any result_groups exist
                EXISTS (
                    SELECT 1 FROM ctgov.result_groups rg
                    WHERE rg.nct_id = s.nct_id
                )                     AS has_results_section,

                -- Lead sponsor class
                (SELECT sp.agency_class
                 FROM ctgov.sponsors sp
                 WHERE sp.nct_id = s.nct_id
                   AND sp.lead_or_collaborator = 'lead'
                 LIMIT 1)             AS sponsor_class,

                -- Collaborator count
                (SELECT COUNT(*)
                 FROM ctgov.sponsors sp
                 WHERE sp.nct_id = s.nct_id
                   AND sp.lead_or_collaborator = 'collaborator') AS collaborator_count,

                -- Site count
                (SELECT COUNT(*)
                 FROM ctgov.facilities f
                 WHERE f.nct_id = s.nct_id) AS num_sites,

                -- Publication count (result references only)
                (SELECT COUNT(*)
                 FROM ctgov.study_references sr
                 WHERE sr.nct_id = s.nct_id
                   AND sr.reference_type = 'result') AS publication_count

            FROM ctgov.studies s
            WHERE {where_sql}
            ORDER BY s.start_date DESC NULLS LAST
            LIMIT :max_results
        """

        with self.engine.connect() as conn:
            result = conn.execute(text(query), params)
            trials = [dict(row._mapping) for row in result.fetchall()]

        logger.info(f"Fetched {len(trials)} trials from AACT")
        return trials

    # -------------------------------------------------------------------------
    # Public: enrich a single trial with all Tier 1/2/3 fields
    # -------------------------------------------------------------------------

    def enrich_trial_with_design_and_outcomes(self, nct_id: str) -> Dict:
        try:
            with self.engine.connect() as conn:
                trial = self._fetch_core(conn, nct_id)
                if not trial:
                    raise ValueError(f"Trial {nct_id} not found in AACT")
                self._enrich_interventions(conn, nct_id, trial)
                self._enrich_conditions(conn, nct_id, trial)
                self._enrich_outcomes(conn, nct_id, trial)
                self._enrich_sponsors(conn, nct_id, trial)
                self._enrich_sites(conn, nct_id, trial)
                self._enrich_safety(conn, nct_id, trial)
                self._enrich_participant_flow(conn, nct_id, trial)
                self._enrich_references(conn, nct_id, trial)
                self._compute_derived_fields(trial)
            return trial
        except Exception as e:
            import traceback
            logger.error(f"[AACT] Full error for {nct_id}: {traceback.format_exc()}")
            raise

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _fetch_core(self, conn, nct_id: str) -> Optional[Dict]:
        """Core study fields — only columns that exist in ctgov.studies."""
        query = text("""
            SELECT
                st.nct_id,
                st.brief_title,
                st.official_title,
                st.why_stopped,
                st.phase,
                st.study_type,
                st.enrollment,
                st.enrollment_type,
                st.start_date,
                st.completion_date,
                st.primary_completion_date,
                st.overall_status,
                st.source AS sponsor_name,
                st.number_of_arms,
                st.is_fda_regulated_drug,
                st.is_fda_regulated_device,
                st.has_expanded_access,
                d.allocation,
                d.intervention_model,
                d.primary_purpose,
                d.masking,
                e.criteria AS eligibility_criteria,
                e.minimum_age,
                e.maximum_age,
                e.gender,
                dd.description AS detailed_description,
                EXISTS (
                    SELECT 1 FROM ctgov.result_groups rg
                    WHERE rg.nct_id = st.nct_id
                ) AS has_results_section
            FROM ctgov.studies st
            LEFT JOIN ctgov.designs d ON st.nct_id = d.nct_id
            LEFT JOIN ctgov.eligibilities e ON st.nct_id = e.nct_id
            LEFT JOIN ctgov.detailed_descriptions dd ON st.nct_id = dd.nct_id
            WHERE st.nct_id = :nct_id
        """)
        result = conn.execute(query, {"nct_id": nct_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None

    def _enrich_interventions(self, conn, nct_id: str, trial: dict):
        result = conn.execute(text(f"""
            SELECT name, intervention_type, description
            FROM ctgov.interventions
            WHERE nct_id = :nct_id
        """), {"nct_id": nct_id})

        rows = [dict(r._mapping) for r in result.fetchall()]
        drug_rows = [r for r in rows if (r.get("intervention_type") or "").lower() == "drug"]

        trial["drug_names"]                       = [r["name"] for r in drug_rows]
        trial["drug_name"]                        = drug_rows[0]["name"] if drug_rows else None
        trial["_t1_intervention_type"]            = drug_rows[0]["intervention_type"] if drug_rows else (rows[0].get("intervention_type") if rows else None)
        trial["_t1_intervention_description"]     = drug_rows[0].get("description") if drug_rows else None
        trial["_t1_all_interventions"]            = [f"{r['name']} ({r['intervention_type']})" for r in rows]

    def _enrich_conditions(self, conn, nct_id: str, trial: dict):
        result = conn.execute(text(f"""
            SELECT name, downcase_name
            FROM ctgov.conditions
            WHERE nct_id = :nct_id
        """), {"nct_id": nct_id})

        rows       = [dict(r._mapping) for r in result.fetchall()]
        names      = [r["name"] for r in rows]
        names_lower = " ".join(r.get("downcase_name") or r["name"].lower() for r in rows)

        trial["condition"]             = "; ".join(names[:3]) if names else None
        trial["_t1_condition_meshes"]  = names

        oncology_terms = ["cancer", "neoplasm", "oncol", "tumor", "carcinoma",
                          "lymphoma", "leukemia", "myeloma", "sarcoma", "melanoma"]
        cns_terms      = ["neural", "brain", "cns", "neuro", "psych", "psychiatr",
                          "alzheimer", "parkinson", "epilep", "schizophr", "dementia"]
        rare_terms     = ["rare", "orphan", "genetic disorder", "inborn"]

        trial["_t1_is_oncology"]       = any(t in names_lower for t in oncology_terms)
        trial["_t1_is_cns"]            = any(t in names_lower for t in cns_terms)
        trial["_t1_is_rare_disease"]   = any(t in names_lower for t in rare_terms)

    def _enrich_outcomes(self, conn, nct_id: str, trial: dict):
        result = conn.execute(text(f"""
            SELECT measure, outcome_type, time_frame
            FROM ctgov.design_outcomes
            WHERE nct_id = :nct_id
        """), {"nct_id": nct_id})

        outcomes = [dict(r._mapping) for r in result.fetchall()]
        trial["_t1_primary_outcome_measures"] = [
            o["measure"] for o in outcomes if o["outcome_type"] == "primary"
        ]
        trial["_t1_secondary_outcome_count"]  = len([
            o for o in outcomes if o["outcome_type"] == "secondary"
        ])

    def _enrich_sponsors(self, conn, nct_id: str, trial: dict):
        result = conn.execute(text(f"""
            SELECT name, agency_class, lead_or_collaborator
            FROM ctgov.sponsors
            WHERE nct_id = :nct_id
        """), {"nct_id": nct_id})

        sponsors = [dict(r._mapping) for r in result.fetchall()]
        lead     = next((s for s in sponsors if s["lead_or_collaborator"] == "lead"), None)
        collabs  = [s for s in sponsors if s["lead_or_collaborator"] == "collaborator"]

        trial["sponsor"]                = lead["name"] if lead else trial.get("sponsor_name")
        trial["_t1_sponsor_class"]      = lead["agency_class"] if lead else None
        trial["_t2_collaborator_count"] = len(collabs)
        trial["_t2_collaborator_names"] = [s["name"] for s in collabs]

    def _enrich_sites(self, conn, nct_id: str, trial: dict):
        result = conn.execute(text(f"""
            SELECT COUNT(*) AS count
            FROM ctgov.facilities
            WHERE nct_id = :nct_id
        """), {"nct_id": nct_id})
        trial["_t1_num_sites"] = dict(result.fetchone()._mapping)["count"]

    def _enrich_safety(self, conn, nct_id: str, trial: dict):
        if not trial.get("has_results_section"):
            trial.update({
                "_t3_has_results_section": False,
                "_t3_sae_count":           0,
                "_t3_sae_affected_count":  0,
                "_t3_sae_rate":            None,
                "_t3_death_count":         0,
                "_t3_other_ae_count":      0,
            })
            return

        sae_result = conn.execute(text(f"""
            SELECT
                COALESCE(SUM(subjects_affected) FILTER (WHERE event_type = 'serious'), 0)  AS sae_affected,
                COALESCE(SUM(subjects_affected) FILTER (WHERE event_type = 'other'),   0)  AS other_affected,
                COALESCE(COUNT(*)               FILTER (WHERE event_type = 'serious'), 0)  AS sae_count
            FROM ctgov.reported_events
            WHERE nct_id = :nct_id
        """), {"nct_id": nct_id})

        sae_row      = dict(sae_result.fetchone()._mapping)

        death_result = conn.execute(text(f"""
            SELECT COALESCE(SUM(deaths), 0) AS death_count
            FROM ctgov.result_groups
            WHERE nct_id = :nct_id
        """), {"nct_id": nct_id})

        death_row    = dict(death_result.fetchone()._mapping)
        sae_affected = int(sae_row.get("sae_affected") or 0)
        enrollment   = trial.get("enrollment") or 0

        trial["_t3_has_results_section"] = True
        trial["_t3_sae_count"]           = int(sae_row.get("sae_count") or 0)
        trial["_t3_sae_affected_count"]  = sae_affected
        trial["_t3_sae_rate"]            = (sae_affected / enrollment) if enrollment > 0 else None
        trial["_t3_death_count"]         = int(death_row.get("death_count") or 0)
        trial["_t3_other_ae_count"]      = int(sae_row.get("other_affected") or 0)
        trial["_t2_has_results"]         = True

    def _enrich_participant_flow(self, conn, nct_id: str, trial: dict):
        if not trial.get("has_results_section"):
            trial.update({
                "_t3_total_started":   0,
                "_t3_total_completed": 0,
                "_t3_completion_rate": None,
            })
            return

        result = conn.execute(text(f"""
            SELECT
                COALESCE(SUM(CASE WHEN pf.type = 'started'   THEN pf.count ELSE 0 END), 0) AS started,
                COALESCE(SUM(CASE WHEN pf.type = 'completed' THEN pf.count ELSE 0 END), 0) AS completed
            FROM ctgov.participant_flows pf
            WHERE pf.nct_id = :nct_id
        """), {"nct_id": nct_id})

        row       = dict(result.fetchone()._mapping)
        started   = int(row.get("started") or 0)
        completed = int(row.get("completed") or 0)

        trial["_t3_total_started"]   = started
        trial["_t3_total_completed"] = completed
        trial["_t3_completion_rate"] = (completed / started) if started > 0 else None

    def _enrich_references(self, conn, nct_id: str, trial: dict):
        result = conn.execute(text(f"""
            SELECT reference_type, pmid
            FROM ctgov.study_references
            WHERE nct_id = :nct_id
        """), {"nct_id": nct_id})

        refs = [dict(r._mapping) for r in result.fetchall()]
        trial["_t2_publication_count"]    = len([r for r in refs if r["reference_type"] == "result"])
        trial["_t2_background_ref_count"] = len([r for r in refs if r["reference_type"] == "background"])
        trial["_t2_pmids"]                = [r["pmid"] for r in refs if r.get("pmid")]

    def _compute_derived_fields(self, trial: dict):
        """Map all fields to the _t1_/_t2_/_t3_ keys the scorer expects."""
        trial["_t1_phases"]              = [trial.get("phase")] if trial.get("phase") else []
        trial["_t1_enrollment_actual"]   = trial.get("enrollment")
        trial["_t1_enrollment_type"]     = trial.get("enrollment_type")
        trial["_t1_allocation"]          = trial.get("allocation")
        trial["_t1_intervention_model"]  = trial.get("intervention_model")
        trial["_t1_primary_purpose"]     = trial.get("primary_purpose")
        trial["_t1_study_type"]          = trial.get("study_type")
        trial["_t1_masking"]             = trial.get("masking")
        trial["_t1_num_arms"]            = trial.get("number_of_arms")
        trial["_t1_min_age"]             = trial.get("minimum_age")
        trial["_t1_max_age"]             = trial.get("maximum_age")
        trial["_t1_sex"]                 = trial.get("gender")
        trial["_t1_is_fda_regulated_drug"]   = trial.get("is_fda_regulated_drug")
        trial["_t1_is_fda_regulated_device"] = trial.get("is_fda_regulated_device")
        trial["_t2_has_expanded_access"]     = trial.get("has_expanded_access", False)
        trial["_t2_has_results"]             = trial.get("has_results_section", False)
        trial["_t2_detailed_description"]    = (trial.get("detailed_description") or "")[:500]
        trial["_t2_related_studies_count"]   = 0

        # Trial duration
        start      = trial.get("start_date")
        completion = trial.get("completion_date")
        if start and completion:
            try:
                trial["_t1_trial_duration_days"] = (completion - start).days
            except TypeError:
                trial["_t1_trial_duration_days"] = None
        else:
            trial["_t1_trial_duration_days"] = None

        # Eligibility criteria count
        criteria = trial.get("eligibility_criteria") or ""
        trial["_t1_eligibility_criteria_count"] = len([
            line for line in criteria.split("\n")
            if line.strip() and (line.strip()[0].isdigit() or line.strip().startswith("-"))
        ])

        # Sites per patient
        enrollment = trial.get("enrollment") or 0
        num_sites  = trial.get("_t1_num_sites") or 0
        trial["_sites_per_patient"] = (num_sites / enrollment) if enrollment > 0 else None
