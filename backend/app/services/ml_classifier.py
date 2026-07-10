"""
ML Classifier — Groq (Llama-3.3-70b-versatile) Primary
               → Ollama (Qwen3:1.7b) Fallback
               → BiomedBERT Embeddings Emergency Fallback
Full trial context passed to LLM for accurate classification.
Three-tier salvageability scoring with modality interaction.
"""

import json
import logging
import os
import re
import requests as http_requests
from functools import lru_cache
from typing import Tuple, List, Optional, Dict, Any
import time

logger = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────

NVIDIA_API_KEY    = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_MODEL      = os.getenv("NVIDIA_MODEL", "deepseek-ai/deepseek-v4-pro")
NVIDIA_API_URL    = "https://integrate.api.nvidia.com/v1/chat/completions"

OLLAMA_URL        = os.getenv("OLLAMA_URL", "http://ollama:11434/api/generate")
OLLAMA_MODEL      = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")

CONFIDENCE_THRESHOLD  = 0.15
CONFIDENCE_FULL_TRUST = 0.75

VALID_CATEGORIES = [
    "Recruitment failure",
    "Business termination",
    "Lack of efficacy",
    "Toxicity",
    "Endpoint failure",
    "Operational issue",
    "Unknown",
]

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
   SIGNALS: sponsor decision, funding not obtained, portfolio reprioritization, company restructuring, drug became commercially available, program discontinuation, out-licensing, no longer pursuing, pending data analysis
   CONTEXT CLUES: Industry-sponsored. Short duration before stopping. No safety or efficacy data driving decision. Funding gaps in academic trials.
   CRITICAL: "Did not obtain funding" = Business termination. "Sponsor decision" alone = Business termination. "Pending data analysis" from an industry sponsor = Business termination.

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

6. "Operational issue"
   WHY: Trial stopped due to logistical, regulatory, manufacturing, or administrative problems unrelated to the drug's science
   SIGNALS: never initiated, site closure, drug supply failure, regulatory hold, IND withdrawal, protocol amendment, investigator withdrawal, manufacturing problem
   CONTEXT CLUES: Trial never started enrolling. Very short duration. Regulatory action mentioned.
   CRITICAL: "Never initiated" = Operational issue always.

7. "Unknown"
   USE ONLY when: text is genuinely blank, completely uninformative ("N/A", "see protocol"), or a single meaningless word
   Do NOT use Unknown if ANY signal exists in any field.

═══ CLASSIFICATION RULES ═══

1. Read ALL provided fields — title, phase, sponsor type, enrollment, and design all provide critical context
2. Negation is critical: "no toxicity" ≠ Toxicity; "no efficacy" = Lack of efficacy
3. Industry sponsor + vague "sponsor decision" or "pending data analysis" = Business termination
4. Academic/NIH sponsor + "funding" language = Business termination
5. Phase 1 + explicit safety language = Toxicity
6. Phase 2/3 + futility/no effect = Lack of efficacy
7. Low enrollment relative to target = Recruitment failure (even if not explicitly stated)
8. Trial ran < 1 year with no scientific reason = likely Operational issue or Business termination
9. Has posted results data = drug showed SOMETHING, boosts salvageability
10. Multiple reasons given = classify by the PRIMARY scientific reason

═══ SALVAGEABILITY SIGNALS ═══

partial_efficacy_signal: true if subgroup showed benefit, responders identified, biomarker response, "trend toward", "partial response", results were posted, or Phase 1 completed before Phase 2 stopped

severity: overall safety profile — "none" (no safety issues), "mild" (minor AEs), "moderate" (dose modifications needed), "severe" (SAEs, deaths, DSMB stop)

early_phase: true if Phase 1, Phase 1/2, Early Phase 1, or first-in-human

has_results_data: true if results section exists or results were posted

large_unmet_need: true if condition is oncology, rare disease, CNS, or other high-unmet-need area

═══ OUTPUT FORMAT ═══

Respond with ONLY valid JSON. No explanation, no markdown, no preamble:
{
  "category": "<exactly one of the 7 categories>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<one precise sentence citing the specific signals that drove this classification>",
  "partial_efficacy_signal": <true|false>,
  "severity": "<none|mild|moderate|severe>",
  "early_phase": <true|false>,
  "has_results_data": <true|false>,
  "large_unmet_need": <true|false>,
  "salvageability_modifier": <integer -20 to +20, expert adjustment, 0 if neutral>
}"""


# ─── Context Builder ──────────────────────────────────────────────────────────

def _build_trial_context(
    why_stopped: str,
    trial_context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build a concise focused context string.
    Lean prompt — only highest-signal fields to avoid overwhelming smaller models.
    Groq/70b handles longer prompts, but concise is still better for accuracy.
    """
    ctx = trial_context or {}
    lines = []

    if ctx.get("title"):
        lines.append(f"Trial: {ctx['title'][:150]}")

    lines.append(f"Termination reason: {why_stopped or '[NOT PROVIDED]'}")

    if ctx.get("drug_name"):
        lines.append(f"Drug: {ctx['drug_name']}")
    if ctx.get("condition"):
        lines.append(f"Condition: {ctx['condition']}")
    if ctx.get("phase") or ctx.get("_t1_phases"):
        phase = ctx.get("phase") or ", ".join(ctx.get("_t1_phases", []))
        lines.append(f"Phase: {phase}")
    if ctx.get("_t1_sponsor_class"):
        lines.append(f"Sponsor type: {ctx['_t1_sponsor_class']}")
    if ctx.get("sponsor"):
        lines.append(f"Sponsor: {ctx['sponsor']}")
    if ctx.get("_t1_enrollment_actual"):
        lines.append(f"Enrollment: {ctx['_t1_enrollment_actual']} ({ctx.get('_t1_enrollment_type', '')})")
    if ctx.get("_t1_allocation"):
        lines.append(f"Design: {ctx['_t1_allocation']} {ctx.get('_t1_intervention_model', '')}")
    if ctx.get("_t1_trial_duration_days"):
        lines.append(f"Duration: {ctx['_t1_trial_duration_days']} days")

    # Safety summary — always include
    death_count = ctx.get("_t3_death_count", 0)
    sae_count   = ctx.get("_t3_sae_count", 0)
    if death_count or sae_count:
        lines.append(f"Safety: {sae_count} SAEs, {death_count} deaths")
    else:
        lines.append("Safety: No adverse events on record")

    if ctx.get("_t2_has_results") or ctx.get("_t3_has_results_section"):
        lines.append("Results: Posted")
    if ctx.get("_t1_is_oncology"):
        lines.append("Disease area: Oncology")
    elif ctx.get("_t1_is_rare_disease"):
        lines.append("Disease area: Rare disease")
    elif ctx.get("_t1_is_cns"):
        lines.append("Disease area: CNS")

    return "\n".join(lines)


# ─── Deepseek Classifier (Primary) ───────────────────────────────────────────────

def _classify_with_nvidia(
    why_stopped: str,
    trial_context: Optional[Dict[str, Any]] = None,
) -> Tuple[str, float, dict]:
    if not NVIDIA_API_KEY:
        logger.warning("[NVIDIA] No API key set, skipping to Ollama fallback")
        return "Unknown", 0.0, {}

    prompt = _build_trial_context(why_stopped, trial_context)

    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model": NVIDIA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens":  400,
    }

    try:
        logger.info(f"[NVIDIA] Sending payload: {json.dumps(payload)[:500]}")  # log first 500 chars
        resp = http_requests.post(NVIDIA_API_URL, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        raw_text = resp.json()["choices"][0]["message"]["content"]

        # Strip any markdown code fences
        raw_text = re.sub(r"```json|```", "", raw_text).strip()

        result   = json.loads(raw_text)
        category = result.get("category", "Unknown")

        if category not in VALID_CATEGORIES:
            logger.warning(f"[NVIDIA] Invalid category '{category}', defaulting Unknown")
            category = "Unknown"

        confidence = float(result.get("confidence", 0.8))
        logger.info(f"[NVIDIA] '{(why_stopped or '')[:60]}' → {category} ({confidence:.2f})")
        return category, confidence, result

    except http_requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 429:
            logger.warning("[NVIDIA] Rate limited — waiting 5s then retrying once")
            time.sleep(5)
            try:
                resp = http_requests.post(NVIDIA_API_URL, headers=headers, json=payload, timeout=30)
                resp.raise_for_status()
                raw_text = re.sub(r"```json|```", "", resp.json()["choices"][0]["message"]["content"]).strip()
                result   = json.loads(raw_text)
                category = result.get("category", "Unknown")
                if category not in VALID_CATEGORIES:
                    category = "Unknown"
                confidence = float(result.get("confidence", 0.8))
                logger.info(f"[NVIDIA] Retry succeeded → {category} ({confidence:.2f})")
                return category, confidence, result
            except Exception as retry_err:
                logger.error(f"[NVIDIA] Retry failed: {retry_err} — falling back to Ollama")
                return "Unknown", 0.0, {}
        else:
            logger.error(f"[NVIDIA] HTTP error: {e}")
            return "Unknown", 0.0, {}

    except (json.JSONDecodeError, KeyError, Exception) as e:
        logger.error(f"[NVIDIA] Failed: {e}")
        return "Unknown", 0.0, {}

# ─── Ollama Classifier (Fallback) ────────────────────────────────────────────

def _classify_with_ollama(
    why_stopped: str,
    trial_context: Optional[Dict[str, Any]] = None,
) -> Tuple[str, float, dict]:
    """
    Secondary classifier — Ollama Qwen3:1.7b.
    Used when Groq is unavailable or returns an error.
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
        raw_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()

        result   = json.loads(raw_text)
        category = result.get("category", "Unknown")

        if category not in VALID_CATEGORIES:
            category = "Unknown"

        confidence = float(result.get("confidence", 0.5))
        logger.info(f"[Ollama] '{(why_stopped or '')[:60]}' → {category} ({confidence:.2f})")
        return category, confidence, result

    except Exception as e:
        logger.error(f"[Ollama] Failed: {e}")
        return "Unknown", 0.0, {}


# ─── BiomedBERT Emergency Fallback ───────────────────────────────────────────

REFERENCE_LIBRARY = {
    "Recruitment failure": [
        "Trial stopped due to slow enrollment and inability to reach sample size",
        "Insufficient patient accrual despite extended recruitment period",
        "Study terminated because the required number of subjects could not be enrolled",
    ],
    "Toxicity": [
        "Study halted following serious adverse events including hepatotoxicity",
        "Dose-limiting toxicity observed requiring trial discontinuation",
        "Safety signal identified in interim analysis, DSMB recommended stopping",
    ],
    "Lack of efficacy": [
        "Interim analysis demonstrated futility and lack of clinical benefit",
        "Drug failed to show statistically significant improvement in primary endpoint",
        "No efficacy signal observed in dose escalation cohorts",
    ],
    "Business termination": [
        "Sponsor made strategic decision to discontinue the program",
        "Trial stopped following portfolio reprioritization and funding reallocation",
        "Did not obtain funding to proceed with the study",
        "Drug became commercially available making the trial unnecessary",
        "Pending data analysis led to program termination",
    ],
    "Endpoint failure": [
        "Primary endpoint of reduction in hospitalisation was not met",
        "Failed to achieve pre-specified endpoint at interim analysis",
    ],
    "Operational issue": [
        "Manufacturing supply issues prevented continuation of the trial",
        "Site closure and investigator withdrawal led to study termination",
        "Trial was never initiated or started due to operational issues",
    ],
    "Unknown": [
        "Study terminated for unspecified reasons",
    ],
}


@lru_cache(maxsize=1)
def _get_embedder():
    from sentence_transformers import SentenceTransformer
    logger.info("[Embedder] Loading S-PubMedBert...")
    return SentenceTransformer("pritamdeka/S-PubMedBert-MS-MARCO")


def _classify_with_embeddings(text: str) -> Tuple[str, float]:
    """Emergency fallback when both Groq and Ollama are unavailable."""
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

        logger.info(f"[Embedder] '{text[:60]}' → {best_cat} (sim={best_sim:.2f})")
        return best_cat, best_sim
    except Exception as e:
        logger.error(f"[Embedder] Failed: {e}")
        return "Unknown", 0.0


# ─── Unified Classifier ───────────────────────────────────────────────────────

def _classify(
    why_stopped: str,
    trial_context: Optional[Dict[str, Any]] = None,
) -> Tuple[str, float, dict, str]:
    """
    Three-level classifier with fallback chain.
    Returns (category, confidence, llm_result, source)
    source: 'groq' | 'ollama' | 'embeddings'
    """
    # ── Level 1: Groq (primary) ───────────────────────────────────────────────
    category, confidence, llm_result = _classify_with_nvidia(why_stopped, trial_context)
    if confidence > 0.0:
        return category, confidence, llm_result, "nvidia"

    # ── Level 2: Ollama (secondary) ───────────────────────────────────────────
    logger.warning("[Classifier] NVIDIA unavailable — trying Ollama")
    category, confidence, llm_result = _classify_with_ollama(why_stopped, trial_context)
    if confidence > 0.0:
        return category, confidence, llm_result, "ollama"

    # ── Level 3: BiomedBERT (emergency) ──────────────────────────────────────
    logger.warning("[Classifier] Ollama unavailable — using BiomedBERT embeddings")
    combined = " ".join(filter(None, [
        why_stopped,
        (trial_context or {}).get("title", ""),
        (trial_context or {}).get("condition", ""),
    ]))
    emb_cat, emb_sim = _classify_with_embeddings(combined)
    return emb_cat, emb_sim, {}, "embeddings"


# ─── Modality Detection ───────────────────────────────────────────────────────

def detect_modality(
    drug_name: Optional[str],
    intervention_type: Optional[str] = None,
    intervention_description: Optional[str] = None,
) -> Optional[str]:
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


# ─── Recommendations ──────────────────────────────────────────────────────────

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
    """
    from app.services.scorer import compute_three_tier_score

    ctx = dict(trial_context or {})
    if drug_name and not ctx.get("drug_name"):
        ctx["drug_name"] = drug_name
    if phase and not ctx.get("phase"):
        ctx["phase"] = phase

    # ── Step 1: Classify ──────────────────────────────────────────────────────
    text = why_stopped or ""
    category, confidence, llm_result, source = _classify(text, ctx)

    logger.info(f"[Pipeline] source={source} category={category} confidence={confidence:.2f}")

    # ── Step 2: Three-tier score ──────────────────────────────────────────────
    score, data_confidence, score_breakdown = compute_three_tier_score(
        category, confidence, llm_result, ctx
    )
    score_breakdown["classification_source"] = source

    # ── Step 3: Recommendations ───────────────────────────────────────────────
    modality = detect_modality(
        ctx.get("drug_name", drug_name),
        ctx.get("_t1_intervention_type"),
        ctx.get("_t1_intervention_description"),
    )
    recs = get_recommendations(category, modality)

    return category, score, recs, data_confidence, score_breakdown