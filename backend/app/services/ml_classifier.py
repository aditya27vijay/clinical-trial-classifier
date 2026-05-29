"""
ML Classifier — Ollama (Qwen3:1.7b) Primary + BiomedBERT Fallback
Full trial context passed to LLM for accurate classification.
Confidence-weighted salvageability scoring with modality interaction.
"""

import json
import logging
import os
import re
import requests as http_requests
from functools import lru_cache
from typing import Tuple, List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────

OLLAMA_URL        = os.getenv("OLLAMA_URL", "http://ollama:11434/api/generate")
OLLAMA_MODEL      = "qwen3:1.7b"
CONFIDENCE_THRESHOLD     = 0.35
CONFIDENCE_FULL_TRUST    = 0.75   # above this, score is not blended
UNKNOWN_BASELINE         = 40     # score we blend toward on low confidence

VALID_CATEGORIES = [
    "Recruitment failure",
    "Business termination",
    "Lack of efficacy",
    "Toxicity",
    "Endpoint failure",
    "Operational issue",
    "Unknown",
]

# ─── Base Scores ──────────────────────────────────────────────────────────────

BASE_SCORES = {
    "Business termination":  85,
    "Recruitment failure":   80,
    "Operational issue":     70,
    "Endpoint failure":      60,
    "Unknown":               40,
    "Lack of efficacy":      25,
    "Toxicity":              20,
}

# ─── Modality Keywords ────────────────────────────────────────────────────────

MODALITY_KEYWORDS = {
    "small_molecule": [
        "tablet", "capsule", "oral", "pill", "compound", "inhibitor",
        "antagonist", "agonist", "kinase", "small molecule", "chemical",
        "mg/kg", "hydrochloride", "sodium", "acetate",
    ],
    "biologic_antibody": [
        "antibody", "monoclonal", "mab", "biologic", "protein",
        "fusion protein", "immunoglobulin", "bevacizumab", "pembrolizumab",
        "nivolumab", "rituximab", "trastuzumab", "checkpoint",
    ],
    "gene_therapy": [
        "gene therapy", "viral vector", "aav", "lentiviral", "adenoviral",
        "gene transfer", "gene editing", "crispr", "zinc finger",
        "gene correction", "oncolytic",
    ],
    "cell_therapy": [
        "cell therapy", "car-t", "car t", "stem cell", "t cell",
        "adoptive cell", "dendritic cell", "natural killer", "nk cell",
        "islet cell", "bone marrow", "cellular therapy",
    ],
    "rna_therapy": [
        "rna", "mrna", "sirna", "antisense", "oligonucleotide",
        "rnai", "interference", "splice", "asos", "aptamer",
    ],
    "vaccine": [
        "vaccine", "vaccination", "immunization", "adjuvant",
        "antigen", "prophylactic", "immunogenic",
    ],
    "device_procedure": [
        "device", "implant", "catheter", "stent", "surgical",
        "procedure", "radiation", "ablation", "stimulation",
    ],
}

# ─── Modality × Category Score Matrix ────────────────────────────────────────

MODALITY_SCORE_MATRIX = {
    ("small_molecule",    "Toxicity"):              +10,
    ("small_molecule",    "Lack of efficacy"):      +5,
    ("small_molecule",    "Recruitment failure"):   +5,
    ("biologic_antibody", "Toxicity"):              -5,
    ("biologic_antibody", "Recruitment failure"):   +8,
    ("biologic_antibody", "Business termination"):  +10,
    ("gene_therapy",      "Toxicity"):              -20,
    ("gene_therapy",      "Lack of efficacy"):      -10,
    ("gene_therapy",      "Business termination"):  +5,
    ("cell_therapy",      "Toxicity"):              -15,
    ("cell_therapy",      "Recruitment failure"):   +5,
    ("cell_therapy",      "Business termination"):  +8,
    ("rna_therapy",       "Toxicity"):              +5,
    ("rna_therapy",       "Lack of efficacy"):      +8,
    ("rna_therapy",       "Business termination"):  +10,
    ("vaccine",           "Recruitment failure"):   +10,
    ("vaccine",           "Lack of efficacy"):      -5,
    ("vaccine",           "Business termination"):  +5,
    ("device_procedure",  "Toxicity"):              -10,
    ("device_procedure",  "Operational issue"):     +5,
}

# ─── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior clinical development expert and drug asset analyst with 20+ years of experience evaluating terminated clinical trials for pharmaceutical companies. You have deep expertise in clinical operations, drug development strategy, regulatory affairs, and biomedical science.

Your task is to analyze ALL available information about a terminated clinical trial and classify why it stopped, then assess its salvageability as a drug asset.

═══ FAILURE CATEGORIES ═══

1. "Recruitment failure"
   WHY: Trial stopped because not enough patients were enrolled
   SIGNALS: slow accrual, low enrollment, missed recruitment targets, insufficient subjects, sample size not met, unable to enroll
   CONTEXT CLUES: Low actual vs anticipated enrollment. Many sites but few patients. Long recruitment window with no completion.

2. "Business termination"
   WHY: Trial stopped for commercial, strategic, financial, or organizational reasons — NOT because of scientific failure
   SIGNALS: sponsor decision, funding not obtained, portfolio reprioritization, company restructuring, drug became commercially available, program discontinuation, out-licensing, no longer pursuing
   CONTEXT CLUES: Industry-sponsored. Short duration before stopping. No safety or efficacy data driving decision. Funding gaps in academic trials.
   CRITICAL: "Did not obtain funding" = Business termination. "Sponsor decision" alone = Business termination.

3. "Lack of efficacy"
   WHY: Trial stopped because the drug showed insufficient therapeutic benefit
   SIGNALS: futility, no clinical benefit, drug did not work, no response, no improvement, interim analysis showed no effect
   CONTEXT CLUES: Later phase trial (Phase 2/3). Placebo-controlled. Clear primary endpoint defined. Interim analysis triggered stopping.
   CRITICAL: "No toxicity concerns were identified" is NOT toxicity — the drug was safe but likely ineffective.

4. "Toxicity"
   WHY: Trial stopped because the drug CAUSED harm to patients
   SIGNALS: adverse events, side effects, drug-related harm, dose-limiting toxicity, hepatotoxicity, cardiotoxicity, patient death from drug, safety signal, DSMB recommendation
   CONTEXT CLUES: Phase 1 dose escalation. Multiple patients affected. Specific organ toxicity named.
   CRITICAL: Only classify as Toxicity if the drug CAUSED harm. Absence of toxicity ≠ Toxicity.

5. "Endpoint failure"
   WHY: Trial stopped because it failed to meet its predefined clinical measurement goals
   SIGNALS: primary endpoint not met, secondary endpoint missed, composite endpoint failure, did not achieve pre-specified threshold
   CONTEXT CLUES: Phase 3 trial. Well-defined primary outcome. Interim analysis at pre-specified timepoint.
   NOTE: Distinct from lack of efficacy — endpoint failure is about the measurement goal, not just drug performance.

6. "Operational issue"
   WHY: Trial stopped due to logistical, regulatory, manufacturing, or administrative problems unrelated to the drug's science
   SIGNALS: never initiated, site closure, drug supply failure, regulatory hold, IND withdrawal, protocol amendment, investigator withdrawal, manufacturing problem, administrative issue
   CONTEXT CLUES: Trial never started enrolling. Very short duration. Regulatory action mentioned.
   CRITICAL: "Never initiated" = Operational issue always.

7. "Unknown"
   USE ONLY when: text is genuinely blank, completely uninformative ("N/A", "see protocol"), or a single meaningless word
   Do NOT use Unknown if ANY signal exists in any field.

═══ CLASSIFICATION RULES ═══

1. Read ALL provided fields, not just the termination reason — title, phase, sponsor type, enrollment, and study design all provide critical context
2. Negation is critical: "no toxicity" ≠ Toxicity; "no efficacy" = Lack of efficacy
3. Industry sponsor + vague "sponsor decision" = Business termination
4. Academic/NIH sponsor + "funding" language = Business termination
5. Phase 1 + safety language = Toxicity
6. Phase 2/3 + futility/no effect = Lack of efficacy
7. Low enrollment relative to target = Recruitment failure (even if not explicitly stated)
8. Trial ran < 1 year from start to termination with no scientific reason = likely Operational issue or Business termination
9. Has posted results data = drug showed SOMETHING, boosts salvageability regardless of failure reason
10. Multiple reasons given = classify by the PRIMARY scientific reason

═══ SALVAGEABILITY SIGNALS ═══

Look for these in ALL fields and set the corresponding JSON flags:

partial_efficacy_signal: true if ANY of these appear anywhere:
  - Subgroup showed benefit, responders identified, biomarker-selected patients responded
  - "Some patients responded", "trend toward", "partial response"
  - Results were posted (means data exists)
  - Phase 1 completed successfully before Phase 2 stopped

severity: assess overall safety profile from all context:
  - "none": no safety issues mentioned anywhere
  - "mild": minor AEs, well-tolerated language, manageable side effects  
  - "moderate": AEs requiring dose modification, some discontinuations
  - "severe": SAEs, deaths, irreversible harm, DSMB-mandated stop, black box warning

early_phase: true if Phase 1, Phase 1/2, Early Phase 1, or first-in-human

has_results_data: true if results section exists or results were posted — this significantly boosts salvageability

large_unmet_need: true if condition is oncology, rare disease, CNS, or other high-unmet-need area

═══ OUTPUT FORMAT ═══

Respond with ONLY this JSON object. No thinking tags, no explanation, no markdown, no preamble:
{
  "category": "<exactly one of the 7 categories>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<one precise sentence citing the specific signals that drove this classification>",
  "partial_efficacy_signal": <true|false>,
  "severity": "<none|mild|moderate|severe>",
  "early_phase": <true|false>,
  "has_results_data": <true|false>,
  "large_unmet_need": <true|false>,
  "salvageability_modifier": <integer -20 to +20, your expert assessment of additional score adjustment beyond rules, 0 if neutral>
}"""


# ─── Context Builder ──────────────────────────────────────────────────────────

def _build_trial_context(
    why_stopped: str,
    trial_context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build a rich context string for the LLM from all available trial fields.
    This is what gets sent as the prompt — the more context, the better the classification.
    """
    ctx = trial_context or {}

    lines = ["CLINICAL TRIAL TERMINATION ANALYSIS", "=" * 40]

    # Core identification
    if ctx.get("title"):
        lines.append(f"Trial Title: {ctx['title']}")
    if ctx.get("nct_id"):
        lines.append(f"NCT ID: {ctx['nct_id']}")

    # The primary signal
    lines.append(f"\nTermination Reason (why_stopped): {why_stopped or '[NOT PROVIDED]'}")

    # Drug / intervention
    lines.append("\n--- INTERVENTION ---")
    if ctx.get("drug_name"):
        lines.append(f"Drug/Intervention: {ctx['drug_name']}")
    if ctx.get("_intervention_type"):
        lines.append(f"Intervention Type: {ctx['_intervention_type']}")
    if ctx.get("_intervention_description"):
        desc = ctx["_intervention_description"][:200]
        lines.append(f"Intervention Description: {desc}")
    if ctx.get("_all_interventions"):
        lines.append(f"All Interventions: {ctx['_all_interventions']}")

    # Disease / condition
    lines.append("\n--- DISEASE AREA ---")
    if ctx.get("condition"):
        lines.append(f"Condition(s): {ctx['condition']}")
    if ctx.get("_primary_purpose"):
        lines.append(f"Primary Purpose: {ctx['_primary_purpose']}")

    # Trial design
    lines.append("\n--- TRIAL DESIGN ---")
    if ctx.get("phase"):
        lines.append(f"Phase: {ctx['phase']}")
    if ctx.get("_study_type"):
        lines.append(f"Study Type: {ctx['_study_type']}")
    if ctx.get("_allocation"):
        lines.append(f"Allocation: {ctx['_allocation']}")
    if ctx.get("_masking"):
        lines.append(f"Masking: {ctx['_masking']}")
    if ctx.get("_num_arms"):
        lines.append(f"Number of Arms: {ctx['_num_arms']}")
    if ctx.get("_primary_outcomes"):
        lines.append(f"Primary Outcome(s): {ctx['_primary_outcomes']}")

    # Enrollment
    lines.append("\n--- ENROLLMENT ---")
    if ctx.get("enrollment"):
        enrollment_type = ctx.get("_enrollment_type", "")
        lines.append(f"Enrollment Count: {ctx['enrollment']} ({enrollment_type})")
    if ctx.get("_num_sites"):
        lines.append(f"Number of Sites: {ctx['_num_sites']}")

    # Timeline
    lines.append("\n--- TIMELINE ---")
    if ctx.get("start_date"):
        lines.append(f"Start Date: {ctx['start_date']}")
    if ctx.get("completion_date"):
        lines.append(f"Completion/Stop Date: {ctx['completion_date']}")

    # Sponsor
    lines.append("\n--- SPONSOR ---")
    if ctx.get("sponsor"):
        lines.append(f"Lead Sponsor: {ctx['sponsor']}")
    if ctx.get("_sponsor_class"):
        lines.append(f"Sponsor Type: {ctx['_sponsor_class']}")
    if ctx.get("_collaborators"):
        lines.append(f"Collaborators: {ctx['_collaborators']}")

    # Results
    lines.append("\n--- RESULTS ---")
    has_results = ctx.get("_has_results", False)
    lines.append(f"Results Data Posted: {'YES — trial generated analyzable data' if has_results else 'No'}")

    # Brief summary
    if ctx.get("_brief_summary"):
        lines.append(f"\n--- STUDY SUMMARY ---")
        lines.append(ctx["_brief_summary"])

    lines.append("\n" + "=" * 40)
    lines.append("Based on ALL of the above information, classify this trial's failure reason.")

    return "\n".join(lines)


# ─── Ollama Classifier ────────────────────────────────────────────────────────

def _classify_with_ollama(
    why_stopped: str,
    trial_context: Optional[Dict[str, Any]] = None,
) -> Tuple[str, float, dict]:
    """
    Primary classifier — sends full trial context to Qwen3:1.7b.
    think=False disables chain-of-thought to keep output clean JSON.
    """
    prompt = _build_trial_context(why_stopped, trial_context)

    payload = {
        "model":  OLLAMA_MODEL,
        "prompt": prompt,
        "system": SYSTEM_PROMPT,
        "stream": False,
        "think":  False,
        "format": "json",
        "options": {
            "temperature": 0.1,
            "top_p":       0.9,
            "num_predict": 300,
        },
    }

    try:
        resp = http_requests.post(OLLAMA_URL, json=payload, timeout=45)
        resp.raise_for_status()
        raw_text = resp.json().get("response", "")

        # Strip any residual think tags
        raw_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()

        result   = json.loads(raw_text)
        category = result.get("category", "Unknown")

        if category not in VALID_CATEGORIES:
            logger.warning(f"Ollama invalid category '{category}', defaulting Unknown")
            category = "Unknown"

        confidence = float(result.get("confidence", 0.5))
        logger.info(f"[Ollama] '{(why_stopped or '')[:60]}' → {category} ({confidence:.2f})")
        return category, confidence, result

    except (http_requests.RequestException, json.JSONDecodeError, KeyError) as e:
        logger.error(f"[Ollama] Failed: {e}")
        return "Unknown", 0.0, {}


# ─── BiomedBERT Fallback ──────────────────────────────────────────────────────

REFERENCE_LIBRARY = {
    "Recruitment failure": [
        "Trial stopped due to slow enrollment and inability to reach sample size",
        "Insufficient patient accrual despite extended recruitment period",
        "Study terminated because the required number of subjects could not be enrolled",
        "Unable to recruit enough eligible patients to continue",
    ],
    "Toxicity": [
        "Study halted following serious adverse events including hepatotoxicity",
        "Dose-limiting toxicity observed requiring trial discontinuation",
        "Safety signal identified in interim analysis, DSMB recommended stopping",
        "Drug caused severe and irreversible harm in multiple patients",
    ],
    "Lack of efficacy": [
        "Interim analysis demonstrated futility and lack of clinical benefit",
        "Drug failed to show statistically significant improvement in primary endpoint",
        "No efficacy signal observed in dose escalation cohorts",
        "Study stopped at interim due to no response in patient population",
    ],
    "Business termination": [
        "Sponsor made strategic decision to discontinue the program",
        "Trial stopped following portfolio reprioritization and funding reallocation",
        "Did not obtain funding to proceed with the study",
        "Drug became commercially available making the trial unnecessary",
        "Company decided to end the program for business reasons",
        "Never initiated due to lack of funding",
    ],
    "Endpoint failure": [
        "Primary endpoint of reduction in hospitalisation was not met",
        "Failed to achieve pre-specified endpoint at interim analysis",
        "Composite endpoint not achieved in the treatment arm",
    ],
    "Operational issue": [
        "Manufacturing supply issues prevented continuation of the trial",
        "Site closure and investigator withdrawal led to study termination",
        "Clinical hold placed by FDA due to regulatory concerns",
        "Trial was never initiated or started due to operational issues",
        "Never initiated, study never began",
    ],
    "Unknown": [
        "Study terminated for unspecified reasons",
        "No reason provided for termination",
    ],
}


@lru_cache(maxsize=1)
def _get_embedder():
    from sentence_transformers import SentenceTransformer
    logger.info("[Fallback] Loading S-PubMedBert embedder...")
    return SentenceTransformer("pritamdeka/S-PubMedBert-MS-MARCO")


def _classify_with_embeddings(text: str) -> Tuple[str, float]:
    """Fallback: cosine similarity against reference library."""
    try:
        from sklearn.metrics.pairwise import cosine_similarity

        embedder  = _get_embedder()
        query_emb = embedder.encode([text])
        best_cat, best_sim = "Unknown", 0.0

        for category, examples in REFERENCE_LIBRARY.items():
            ref_embs = embedder.encode(examples)
            sim = float(cosine_similarity(query_emb, ref_embs).max())
            if sim > best_sim:
                best_sim, best_cat = sim, category

        logger.info(f"[Fallback] '{text[:60]}' → {best_cat} (sim={best_sim:.2f})")
        return best_cat, best_sim
    except Exception as e:
        logger.error(f"[Fallback] Embedding failed: {e}")
        return "Unknown", 0.0


# ─── Modality Detection ───────────────────────────────────────────────────────

def detect_modality(
    drug_name: Optional[str],
    intervention_type: Optional[str] = None,
    intervention_description: Optional[str] = None,
) -> Optional[str]:
    """Detect drug modality from name, type, and description."""

    # ClinicalTrials.gov intervention type gives a strong prior
    if intervention_type:
        t = intervention_type.upper()
        if t == "GENETIC":
            return "gene_therapy"
        if t == "BIOLOGICAL":
            return "biologic_antibody"

    text = " ".join(filter(None, [drug_name, intervention_description])).lower()
    if not text.strip():
        return None

    scores = {m: 0 for m in MODALITY_KEYWORDS}
    for modality, keywords in MODALITY_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                scores[modality] += 1

    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


# ─── Confidence-Weighted Scoring ──────────────────────────────────────────────

def _apply_confidence_weighting(score: int, confidence: float) -> int:
    """
    Blend score toward Unknown baseline (40) when confidence is low.
    At confidence >= 0.75: full score (no blending)
    At confidence == 0.35: ~50% blend toward 40
    At confidence < 0.35:  heavy blend toward 40
    """
    if confidence >= CONFIDENCE_FULL_TRUST:
        return score

    # Linear blend factor: 0.0 at threshold, 1.0 at full trust
    blend = max(0.0, (confidence - CONFIDENCE_THRESHOLD) /
                     (CONFIDENCE_FULL_TRUST - CONFIDENCE_THRESHOLD))

    blended = int(score * blend + UNKNOWN_BASELINE * (1 - blend))
    logger.debug(f"[Score] Confidence blend: {score} × {blend:.2f} + 40 × {1-blend:.2f} = {blended}")
    return blended


# ─── Salvageability Scoring ───────────────────────────────────────────────────

def compute_salvageability(
    category:   str,
    confidence: float,
    llm_result: dict,
    modality:   Optional[str] = None,
    phase:      Optional[str] = None,
) -> int:
    score = BASE_SCORES.get(category, 40)

    # ── LLM-extracted signals ─────────────────────────────────────────────────
    partial_efficacy  = llm_result.get("partial_efficacy_signal", False)
    severity          = llm_result.get("severity", "none")
    early_phase       = llm_result.get("early_phase", False)
    has_results       = llm_result.get("has_results_data", False)
    large_unmet_need  = llm_result.get("large_unmet_need", False)
    llm_modifier      = int(llm_result.get("salvageability_modifier", 0))

    if partial_efficacy:
        score += 12
        logger.debug("[Score] +12 partial efficacy signal")

    if has_results:
        score += 8    # Results posted = data exists = asset has value
        logger.debug("[Score] +8 results data posted")

    if large_unmet_need:
        score += 5    # High unmet need = motivation to rescue
        logger.debug("[Score] +5 large unmet need")

    if severity == "severe":
        score -= 20
    elif severity == "moderate":
        score -= 10
    elif severity == "mild":
        score -= 3

    if early_phase:
        score += 7
        logger.debug("[Score] +7 early phase")

    # LLM's own expert modifier (capped to prevent abuse)
    capped_modifier = max(-20, min(20, llm_modifier))
    if capped_modifier != 0:
        score += capped_modifier
        logger.debug(f"[Score] {capped_modifier:+d} LLM expert modifier")

    # ── Phase metadata modifier ───────────────────────────────────────────────
    if phase:
        p = phase.lower()
        if ("phase 1" in p or "phase1" in p or "early" in p) and not early_phase:
            score += 5
        elif "phase 3" in p or "phase3" in p:
            score -= 5

    # ── Modality × category matrix ────────────────────────────────────────────
    if modality:
        delta = MODALITY_SCORE_MATRIX.get((modality, category), 0)
        if delta:
            score += delta
            logger.debug(f"[Score] {delta:+d} modality={modality}")

    # ── Confidence weighting — applied last ───────────────────────────────────
    score = _apply_confidence_weighting(max(0, min(100, score)), confidence)

    final = max(0, min(100, score))
    logger.info(
        f"[Score] final={final} | cat={category} | conf={confidence:.2f} "
        f"| modality={modality} | severity={severity}"
    )
    return final


# ─── Recommendations ─────────────────────────────────────────────────────────

RECOMMENDATIONS = {
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

MODALITY_RECOMMENDATIONS = {
    "small_molecule": {
        "Toxicity":         ["Investigate structural analogues with improved safety profile", "Explore prodrug formulation to reduce peak plasma concentration"],
        "Lack of efficacy": ["Screen for more potent analogues in the same chemical series", "Evaluate PK/PD optimization for better target engagement"],
    },
    "biologic_antibody": {
        "Toxicity":         ["Engineer antibody with reduced Fc effector function", "Explore antibody fragment (Fab/scFv) to reduce immunogenicity"],
        "Business termination": ["High licensing value — engage BD teams at larger pharma", "Evaluate biosimilar pathway if molecule is well-characterised"],
    },
    "gene_therapy": {
        "Toxicity":         ["Investigate alternative viral vectors (AAV serotype switch)", "Explore non-viral delivery (LNP) to reduce immunogenicity"],
        "Lack of efficacy": ["Optimise promoter and transgene expression levels", "Investigate cell-type specific delivery targeting"],
    },
    "cell_therapy": {
        "Toxicity":         ["Engineer safety switch (suicide gene) into cell product", "Reduce conditioning regimen intensity before infusion"],
        "Recruitment failure": ["Leverage rare disease patient registries for enrollment", "Consider platform trial design across multiple indications"],
    },
    "rna_therapy": {
        "Lack of efficacy": ["Optimise lipid nanoparticle (LNP) delivery formulation", "Investigate chemical modifications to improve RNA stability"],
        "Toxicity":         ["Reduce immunostimulatory motifs in RNA sequence", "Optimise dosing schedule to reduce inflammatory response"],
    },
    "vaccine": {
        "Lack of efficacy": ["Test alternative adjuvant systems to boost immunogenicity", "Explore prime-boost regimen optimisation"],
        "Recruitment failure": ["Partner with public health bodies for population recruitment", "Leverage disease outbreak response networks"],
    },
}


def get_recommendations(category: str, modality: Optional[str] = None) -> List[str]:
    base = RECOMMENDATIONS.get(category, RECOMMENDATIONS["Unknown"])
    if modality and modality in MODALITY_RECOMMENDATIONS:
        extra = MODALITY_RECOMMENDATIONS[modality].get(category, [])
        if extra:
            return extra + base
    return base


# ─── Main Entry Point ─────────────────────────────────────────────────────────

def full_analysis(
    why_stopped: str,
    drug_name:                Optional[str] = None,
    phase:                    Optional[str] = None,
    intervention_description: Optional[str] = None,
    trial_context:            Optional[Dict[str, Any]] = None,
) -> Tuple[str, int, List[str], str, Dict[str, Any]]:
    """
    Full pipeline: classify → three-tier score → recommend.
    Returns (category, score, recommendations, data_confidence, score_breakdown).
    trial_context: full dict from fetcher containing all Tier 1/2/3 fields.
    """
    from app.services.scorer import compute_three_tier_score

    # Merge convenience args into context dict
    ctx = dict(trial_context or {})
    if drug_name and not ctx.get("drug_name"):
        ctx["drug_name"] = drug_name
    if phase and not ctx.get("phase"):
        ctx["phase"] = phase

    # ── Step 1: Classification ────────────────────────────────────────────────
    if not why_stopped or not why_stopped.strip():
        category, confidence, llm_result = _classify_with_ollama("", ctx)
        if confidence < CONFIDENCE_THRESHOLD:
            category = "Unknown"
            llm_result = {}
    else:
        category, confidence, llm_result = _classify_with_ollama(why_stopped, ctx)

        # Fallback only if Ollama crashed (confidence == 0.0)
        if confidence == 0.0:
            combined = " ".join(filter(None, [
                why_stopped,
                ctx.get("title", ""),
                ctx.get("condition", ""),
            ]))
            emb_cat, emb_sim = _classify_with_embeddings(combined)
            if emb_sim > 0.40:
                category   = emb_cat
                llm_result = {}

    # ── Step 2: Three-tier score calculation ───────────────────────────────────
    score, data_confidence, score_breakdown = compute_three_tier_score(
        category, confidence, llm_result, ctx
    )

    # ── Step 3: Recommendations ───────────────────────────────────────────────
    modality = detect_modality(
        ctx.get("drug_name", drug_name),
        ctx.get("_t1_intervention_type"),
        ctx.get("_t1_intervention_description"),
    )
    recs = get_recommendations(category, modality)

    return category, score, recs, data_confidence, score_breakdown