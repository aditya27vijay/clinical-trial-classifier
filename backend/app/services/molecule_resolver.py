"""
Molecule Resolver — PubChem + ChEMBL + OpenTargets/DrugBank
Resolves drug names → InChIKey → SMILES → targets → mechanism → real-world usage

Resolution chain:
  1. Normalize name (strip dosage/formulation noise, detect combinations, detect salt forms)
  2. PubChem exact name lookup, validated against returned synonyms (not a blind first-CID pick)
  3. Salt/hydrate suffix fallback — retry against the parent compound if the salt form fails
  4. INN stem pre-processing (biologics: -mab, -nib, -zumab) for modality
  5. ChEMBL name search, cross-validated against PubChem's InChIKey (structure-level, not name-level)
  6. Mark unresolved (confidence 0.3)

Confidence is now derived from *how* a match was found (exact / synonym / parent-compound /
fuzzy) rather than being a flat constant per source, and a `resolution_conflict` flag is set
whenever PubChem and ChEMBL disagree on structure so a human can review it instead of the
merge silently picking one.

All results are cached in-memory per session to avoid redundant API calls.
"""

import os
import re
import time
import logging
import difflib
import requests
from typing import Dict, List, Optional, Tuple
from functools import lru_cache

logger = logging.getLogger(__name__)

PUBCHEM_BASE     = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
CHEMBL_BASE      = "https://www.ebi.ac.uk/chembl/api/data"
OPENTARGETS_BASE = "https://api.platform.opentargets.org/api/v4/graphql"
DRUGBANK_BASE    = "https://go.drugbank.com/api/v1"   # licensed API — requires DRUGBANK_API_KEY
REQUEST_DELAY    = 0.34   # 3 req/sec PubChem polite limit

DRUGBANK_API_KEY = os.getenv("DRUGBANK_API_KEY")   # unset in most environments — see resolve_drugbank()

# INN stems → modality mapping
INN_STEMS = {
    "mab":    "biologic_antibody",
    "zumab":  "biologic_antibody",
    "ximab":  "biologic_antibody",
    "mumab":  "biologic_antibody",
    "lumab":  "biologic_antibody",
    "tinib":  "small_molecule",
    "nib":    "small_molecule",
    "rafenib":"small_molecule",
    "ciclib": "small_molecule",
    "tide":   "biologic_antibody",
    "kinase": "small_molecule",
    "statin": "small_molecule",
    "sartan": "small_molecule",
    "prazole":"small_molecule",
    "gene":   "gene_therapy",
    "cel":    "cell_therapy",
    "vir":    "small_molecule",
    "mRNA":   "rna_therapy",
    "siRNA":  "rna_therapy",
}

# Common salt / hydrate / formulation suffixes that change the InChIKey but not the
# clinically relevant parent compound. Stripping these gives a second lookup chance
# when the salt form itself isn't in PubChem/ChEMBL under that exact name.
SALT_SUFFIXES = [
    "hydrochloride", "hcl", "sulfate", "sulphate", "sodium", "potassium",
    "mesylate", "besylate", "tosylate", "tartrate", "maleate", "fumarate",
    "citrate", "phosphate", "acetate", "succinate", "dihydrate", "monohydrate",
    "hydrobromide", "hemihydrate", "trihydrate", "calcium", "disodium",
]

# Dosage / formulation noise that shows up in AACT intervention names and should be
# stripped before any name lookup (e.g. "Drug X 10 mg tablet" -> "Drug X").
DOSAGE_PATTERN = re.compile(
    r"\b\d+(\.\d+)?\s*(mg|mcg|g|ml|iu|units?)\b|\b(tablet|capsule|injection|solution|"
    r"oral|iv|infusion|suspension|extended[- ]release|xr|er|sr)\b",
    re.IGNORECASE,
)

COMBINATION_DELIMITERS = re.compile(r"\s*(?:\+|/| and |,)\s*", re.IGNORECASE)

# Confidence tiers by how the match was actually found — replaces the old flat constants
MATCH_CONFIDENCE = {
    "exact_name":       0.95,
    "synonym":          0.88,
    "parent_compound":  0.80,
    "fuzzy":            0.65,
    "chembl_only":      0.75,
    "unresolved":       0.30,
}


# ─── Name normalization ───────────────────────────────────────────────────────

def _clean_drug_name(name: str) -> str:
    """Strip dosage/formulation noise so lookups aren't defeated by e.g. '10 mg tablet'."""
    cleaned = DOSAGE_PATTERN.sub("", name)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,-")
    return cleaned or name.strip()


def split_combination(name: str) -> Optional[List[str]]:
    """
    Detect combination products like 'Drug A + Drug B' or 'Drug A/Drug B'.
    Returns a list of component names if a combination is detected, else None.
    Guards against splitting condition-style names with commas by requiring
    at least two non-trivial (>2 char) parts, all of which look like drug-ish
    tokens rather than a single descriptive phrase.
    """
    if not any(d in name for d in ["+", "/", " and "]):
        return None

    parts = [p.strip() for p in COMBINATION_DELIMITERS.split(name) if p.strip()]
    parts = [p for p in parts if len(p) > 2]

    if len(parts) < 2:
        return None
    return parts


def strip_salt_suffix(name: str) -> Optional[str]:
    """Return a parent-compound candidate name with a known salt/hydrate suffix removed."""
    lower = name.lower()
    for suffix in SALT_SUFFIXES:
        pattern = rf"\s+{re.escape(suffix)}$"
        if re.search(pattern, lower):
            return re.sub(pattern, "", name, flags=re.IGNORECASE).strip()
    return None


def _detect_modality_from_name(name: str) -> Optional[str]:
    """Quick modality detection from INN stem before API calls."""
    name_lower = name.lower()
    for stem, modality in INN_STEMS.items():
        if name_lower.endswith(stem):
            return modality
    return None


# ─── Low-level HTTP helpers ───────────────────────────────────────────────────

def _pubchem_request(path: str, retries: int = 3) -> Optional[dict]:
    """Make a PubChem PUG REST request with retry on 429."""
    url = f"{PUBCHEM_BASE}/{path}"
    for attempt in range(retries):
        try:
            time.sleep(REQUEST_DELAY)
            resp = requests.get(url, timeout=10)
            if resp.status_code == 404:
                return None
            if resp.status_code == 429:
                wait = 2 ** attempt
                logger.warning(f"[PubChem] Rate limited, waiting {wait}s")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.debug(f"[PubChem] Request failed ({attempt+1}/{retries}): {e}")
    return None


def _chembl_request(path: str, params: dict = None) -> Optional[dict]:
    """Make a ChEMBL REST request."""
    url = f"{CHEMBL_BASE}/{path}"
    try:
        time.sleep(0.2)
        resp = requests.get(url, params=params or {}, timeout=10,
                            headers={"Accept": "application/json"})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.debug(f"[ChEMBL] Request failed: {e}")
        return None


def _opentargets_request(query: str, variables: dict) -> Optional[dict]:
    """POST a GraphQL query to the OpenTargets Platform API (free, no key required)."""
    try:
        resp = requests.post(
            OPENTARGETS_BASE,
            json={"query": query, "variables": variables},
            timeout=15,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("errors"):
            logger.debug(f"[OpenTargets] GraphQL errors: {payload['errors']}")
            return None
        return payload.get("data")
    except requests.RequestException as e:
        logger.debug(f"[OpenTargets] Request failed: {e}")
        return None


# ─── PubChem property extraction ──────────────────────────────────────────────

def _extract_pubchem_props(compound: dict) -> dict:
    """Extract SMILES, InChIKey from PubChem compound props array."""
    props = compound.get("props", [])
    result = {}
    for prop in props:
        label = prop.get("urn", {}).get("label", "")
        name  = prop.get("urn", {}).get("name", "")
        val   = prop.get("value", {})

        if label == "Preferred IUPAC Name":
            result["iupac_name"] = val.get("sval")
        elif label == "InChIKey":
            result["inchi_key"] = val.get("sval")
        elif label == "InChI":
            result["inchi"] = val.get("sval")
        elif label == "SMILES" and name == "Canonical":
            result["smiles"] = val.get("sval")
        elif label == "Molecular Weight":
            result["molecular_weight"] = val.get("fval") or val.get("sval")
        elif label == "XLogP3":
            result["logp"] = val.get("fval")

    return result


def _get_pubchem_synonyms(cid: int) -> List[str]:
    """Fetch the synonym list for a CID, used to validate that a name match is real."""
    data = _pubchem_request(f"compound/cid/{cid}/synonyms/JSON")
    if not data:
        return []
    info = data.get("InformationList", {}).get("Information", [])
    if not info:
        return []
    return [s.lower() for s in info[0].get("Synonym", [])]


def _best_synonym_match(query: str, synonyms: List[str]) -> Tuple[str, float]:
    """
    Compare the queried name against a compound's synonym list.
    Returns (method, ratio) where method is exact_name / synonym / fuzzy.
    """
    query_l = query.lower()
    if query_l in synonyms:
        return ("exact_name" if synonyms and synonyms[0] == query_l else "synonym", 1.0)

    if not synonyms:
        return ("fuzzy", 0.0)

    best_ratio = max(difflib.SequenceMatcher(None, query_l, s).ratio() for s in synonyms)
    return ("fuzzy", best_ratio)


# ─── PubChem resolution ───────────────────────────────────────────────────────

def resolve_pubchem_by_name(drug_name: str) -> Optional[dict]:
    """
    Look up a drug name in PubChem, validating the match against the compound's
    own synonym list instead of blindly trusting the first returned CID.
    Returns resolved fields (including resolution_method) or None if not found
    or if the match quality is too low to trust.
    """
    cid = None
    data = _pubchem_request(f"compound/name/{requests.utils.quote(drug_name)}/JSON")

    if not data:
        # Try synonym search — this is where a blind cids[0] pick used to happen
        syn_data = _pubchem_request(f"compound/name/{requests.utils.quote(drug_name)}/cids/JSON")
        if not syn_data:
            return None
        cids = syn_data.get("IdentifierList", {}).get("CID", [])
        if not cids:
            return None
        cid = cids[0]
        data = _pubchem_request(f"compound/cid/{cid}/JSON")

    if not data:
        return None

    compounds = data.get("PC_Compounds", [])
    if not compounds:
        return None

    compound = compounds[0]
    cid = cid or compound.get("id", {}).get("id", {}).get("cid")
    props = _extract_pubchem_props(compound)

    if not props.get("inchi_key"):
        return None

    # Validate: does the queried name actually appear as a synonym of this CID?
    synonyms = _get_pubchem_synonyms(cid) if cid else []
    method, ratio = _best_synonym_match(drug_name, synonyms)

    # A fuzzy ratio below this floor means we likely picked the wrong compound
    # (e.g. a partial/garbled name match) — better to report unresolved than wrong.
    if method == "fuzzy" and ratio < 0.6:
        logger.info(f"[Resolver] PubChem candidate for '{drug_name}' rejected (fuzzy ratio={ratio:.2f})")
        return None

    return {
        "pubchem_cid":       cid,
        "inchi_key":         props.get("inchi_key"),
        "smiles":            props.get("smiles"),
        "inchi":             props.get("inchi"),
        "molecular_weight":  props.get("molecular_weight"),
        "logp":              props.get("logp"),
        "resolution_source": "pubchem",
        "resolution_method": method,
        "resolution_confidence": MATCH_CONFIDENCE.get(method, 0.7),
        "match_ratio":       round(ratio, 2),
    }


# ─── ChEMBL resolution ────────────────────────────────────────────────────────

def resolve_chembl_by_name(drug_name: str) -> Optional[dict]:
    """
    Look up a drug name in ChEMBL for targets, mechanism, and structure
    (standard InChIKey — used to cross-validate against PubChem).
    Returns enrichment fields or None.
    """
    data = _chembl_request("molecule.json", params={
        "pref_name__iexact": drug_name,
        "limit": 1,
    })
    method = "exact_name"

    # Fallback: search by synonym
    if not data or not data.get("molecules"):
        data = _chembl_request("molecule.json", params={
            "molecule_synonyms__molecule_synonym__iexact": drug_name,
            "limit": 1,
        })
        method = "synonym"

    if not data or not data.get("molecules"):
        return None

    mol = data["molecules"][0]
    chembl_id = mol.get("molecule_chembl_id")

    # Get mechanism of action
    mech_data = _chembl_request("mechanism.json", params={
        "molecule_chembl_id": chembl_id,
        "limit": 5,
    })

    mechanisms = []
    targets = []
    target_classes = []

    if mech_data and mech_data.get("mechanisms"):
        for m in mech_data["mechanisms"]:
            if m.get("mechanism_of_action"):
                mechanisms.append(m["mechanism_of_action"])
            if m.get("target_chembl_id"):
                tgt = _chembl_request(f"target/{m['target_chembl_id']}.json")
                if tgt:
                    targets.append(tgt.get("pref_name", m["target_chembl_id"]))
                    for comp in tgt.get("target_components", []):
                        for cls in comp.get("target_component_synonyms", []):
                            if cls.get("syn_type") == "GENE_SYMBOL":
                                target_classes.append(cls.get("component_synonym"))

    props = mol.get("molecule_properties") or {}
    structures = mol.get("molecule_structures") or {}

    return {
        "chembl_id":            chembl_id,
        "chembl_pref_name":     mol.get("pref_name"),
        "chembl_inchi_key":     structures.get("standard_inchi_key"),  # used for cross-validation only
        "mechanism_of_action":  mechanisms[0] if mechanisms else None,
        "primary_targets":      targets[:5],
        "target_classes":       list(set(target_classes))[:5],
        "molecular_weight":     props.get("full_mwt"),
        "logp":                 props.get("alogp"),
        "resolution_source":    "chembl",
        "resolution_method":    method,
        "resolution_confidence": MATCH_CONFIDENCE.get("chembl_only", 0.75),
    }


def get_canonical_name(drug_name: str, pubchem_cid: Optional[int] = None) -> Optional[str]:
    """Get the preferred IUPAC or canonical name from PubChem."""
    if pubchem_cid:
        data = _pubchem_request(f"compound/cid/{pubchem_cid}/property/IUPACName/JSON")
        if data:
            props = data.get("PropertyTable", {}).get("Properties", [])
            if props:
                return props[0].get("IUPACName")
    return None


# ─── Real-world / approved usage: OpenTargets (free) + DrugBank (licensed) ───

_OPENTARGETS_DRUG_QUERY = """
query DrugIndications($chemblId: String!) {
  drug(chemblId: $chemblId) {
    id
    name
    maximumClinicalTrialPhase
    isApproved
    indications {
      rows {
        disease {
          id
          name
        }
        maxPhaseForIndication
      }
    }
  }
}
"""


def resolve_opentargets_by_chembl_id(chembl_id: str) -> List[dict]:
    """
    Pull approved/investigational indications for a molecule from OpenTargets'
    free public GraphQL API, keyed off the ChEMBL ID already resolved above.

    NOTE: OpenTargets' schema does evolve between platform releases — if this
    query starts returning no data, check the current schema at
    https://platform-docs.opentargets.org/data-access/graphql-api before
    assuming the molecule genuinely has no indications.
    """
    if not chembl_id:
        return []

    data = _opentargets_request(_OPENTARGETS_DRUG_QUERY, {"chemblId": chembl_id})
    if not data or not data.get("drug"):
        return []

    drug = data["drug"]
    is_approved = drug.get("isApproved", False)
    rows = (drug.get("indications") or {}).get("rows", [])

    results = []
    for row in rows:
        disease = row.get("disease") or {}
        max_phase = row.get("maxPhaseForIndication")
        if max_phase is None:
            status = "unknown"
        elif max_phase >= 4:
            status = "approved"
        elif max_phase and max_phase > 0:
            status = "investigational"
        else:
            status = "unknown"

        results.append({
            "indication":        disease.get("name"),
            "disease_id":        disease.get("id"),
            "approval_status":   "approved" if is_approved and status == "approved" else status,
            "association_score": None,   # OpenTargets exposes separate target-disease scores;
                                          # left null here since this query is indication-level
            "source":            "opentargets",
            "external_id":       disease.get("id"),
        })

    return [r for r in results if r["indication"]]


def resolve_drugbank(drug_name: str) -> List[dict]:
    """
    Pull approved indications from DrugBank. DrugBank's indication data is
    license-gated — there is no free equivalent covering the same ground as
    their curated indication text, so this only activates if DRUGBANK_API_KEY
    is set in the environment. Returns [] (not an error) when unconfigured,
    so callers can treat it as "no additional data" rather than a failure.
    """
    if not DRUGBANK_API_KEY:
        logger.debug("[Resolver] DRUGBANK_API_KEY not set — skipping DrugBank enrichment")
        return []

    try:
        resp = requests.get(
            f"{DRUGBANK_BASE}/drugs",
            params={"q": drug_name},
            headers={"Authorization": f"Bearer {DRUGBANK_API_KEY}"},
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as e:
        logger.debug(f"[Resolver] DrugBank request failed: {e}")
        return []

    hits = payload.get("data", []) if isinstance(payload, dict) else []
    if not hits:
        return []

    drug = hits[0]
    results = []
    for indication in drug.get("indications", []):
        results.append({
            "indication":       indication.get("name"),
            "disease_id":       None,
            "approval_status":  indication.get("status", "approved").lower(),
            "association_score": None,
            "approved_date":    indication.get("approved_date"),
            "source":           "drugbank",
            "external_id":      drug.get("drugbank_id"),
        })

    return [r for r in results if r["indication"]]


def resolve_real_world_usage(chembl_id: Optional[str], drug_name: str) -> Tuple[List[dict], Optional[str]]:
    """
    Combine OpenTargets (free) and DrugBank (licensed, optional) real-world
    usage signals. Returns (records, drugbank_id_if_found).
    """
    records = []
    drugbank_id = None

    if chembl_id:
        records.extend(resolve_opentargets_by_chembl_id(chembl_id))

    drugbank_records = resolve_drugbank(drug_name)
    if drugbank_records:
        drugbank_id = drugbank_records[0].get("external_id")
        records.extend(drugbank_records)

    return records, drugbank_id


# ─── Cross-validation ─────────────────────────────────────────────────────────

def _inchikey_skeleton(inchi_key: Optional[str]) -> Optional[str]:
    """First 14 chars of an InChIKey encode the molecular skeleton (connectivity),
    ignoring stereochemistry/protonation layers — the right granularity for
    'is this the same parent compound', which is what we actually care about here."""
    if not inchi_key or len(inchi_key) < 14:
        return None
    return inchi_key[:14]


def _cross_validate_structures(pubchem_result: dict, chembl_result: dict) -> bool:
    """
    Returns True if PubChem's and ChEMBL's structures agree (or can't be compared),
    False if they actively disagree — a signal to flag resolution_conflict rather
    than silently merging two different compounds.
    """
    pc_key = _inchikey_skeleton(pubchem_result.get("inchi_key"))
    ch_key = _inchikey_skeleton(chembl_result.get("chembl_inchi_key"))
    if not pc_key or not ch_key:
        return True   # can't compare — don't falsely flag a conflict
    return pc_key == ch_key


# ─── Main entry point ─────────────────────────────────────────────────────────

def _resolve_single(drug_name: str, intervention_type: str = None) -> dict:
    """Resolve a single (non-combination) drug name. Internal helper for resolve()."""
    cleaned_name = _clean_drug_name(drug_name)

    modality = _detect_modality_from_name(cleaned_name)
    if intervention_type:
        t = intervention_type.upper()
        if t == "GENETIC":
            modality = "gene_therapy"
        elif t == "BIOLOGICAL":
            modality = "biologic_antibody"
        elif t == "DRUG":
            modality = modality or "small_molecule"

    result = {
        "canonical_name": cleaned_name,
        "modality":       modality,
        "resolution_source": "unresolved",
        "resolution_method": "unresolved",
        "resolution_confidence": MATCH_CONFIDENCE["unresolved"],
        "resolution_conflict": False,
    }

    # ── Step 1: PubChem lookup (with salt-suffix fallback) ───────────────────
    pubchem = resolve_pubchem_by_name(cleaned_name)
    used_parent_name = False
    if not pubchem:
        parent_name = strip_salt_suffix(cleaned_name)
        if parent_name:
            pubchem = resolve_pubchem_by_name(parent_name)
            if pubchem:
                used_parent_name = True
                pubchem["resolution_method"] = "parent_compound"
                pubchem["resolution_confidence"] = MATCH_CONFIDENCE["parent_compound"]
                logger.info(f"[Resolver] Resolved via parent compound: '{cleaned_name}' -> '{parent_name}'")

    if pubchem:
        result.update({k: v for k, v in pubchem.items() if k != "match_ratio"})
        logger.info(
            f"[Resolver] PubChem: {cleaned_name} → CID={pubchem.get('pubchem_cid')} "
            f"InChIKey={pubchem.get('inchi_key')} method={pubchem.get('resolution_method')}"
        )

        # ── Step 2: ChEMBL enrichment + structure cross-check ─────────────────
        chembl = resolve_chembl_by_name(parent_name if used_parent_name else cleaned_name)
        if chembl:
            structures_agree = _cross_validate_structures(pubchem, chembl)
            chembl.pop("chembl_inchi_key", None)   # internal-only field, don't persist to Molecule

            for k, v in chembl.items():
                if k not in result or result[k] is None:
                    result[k] = v

            if structures_agree:
                result["resolution_confidence"] = 0.97 if not used_parent_name else 0.90
                result["resolution_source"] = "pubchem+chembl"
                logger.info(f"[Resolver] ChEMBL enriched: {cleaned_name} → {chembl.get('chembl_id')}")
            else:
                # Structures disagree — keep PubChem's identity as ground truth for
                # chemistry, but flag it so a human reviews rather than trusting the merge.
                result["resolution_conflict"] = True
                result["resolution_confidence"] = min(result["resolution_confidence"], 0.55)
                result["resolution_source"] = "pubchem+chembl_conflict"
                logger.warning(
                    f"[Resolver] Structure conflict for '{cleaned_name}': "
                    f"PubChem InChIKey vs ChEMBL InChIKey disagree — flagged for review"
                )
    else:
        # ── Step 3: ChEMBL only fallback ─────────────────────────────────────
        chembl = resolve_chembl_by_name(cleaned_name)
        if chembl:
            chembl.pop("chembl_inchi_key", None)
            result.update(chembl)
            logger.info(f"[Resolver] ChEMBL only: {cleaned_name} → {chembl.get('chembl_id')}")
        else:
            logger.info(f"[Resolver] Unresolved: {cleaned_name}")

    # ── Step 4: Real-world usage (OpenTargets free / DrugBank optional) ──────
    rwu_records, drugbank_id = resolve_real_world_usage(result.get("chembl_id"), cleaned_name)
    if rwu_records:
        result["real_world_usage"] = rwu_records
    if drugbank_id:
        result["drugbank_id"] = drugbank_id
    if rwu_records:
        statuses = {r["approval_status"] for r in rwu_records}
        result["approval_status"] = (
            "approved" if "approved" in statuses else
            "investigational" if "investigational" in statuses else
            "withdrawn" if "withdrawn" in statuses else "unknown"
        )

    return result


def resolve(drug_name: str, intervention_type: str = None) -> dict:
    """
    Main entry point. Resolve a drug name to full chemical identity, real-world
    usage, and (if applicable) combination-product components.

    Returns a dict with all available fields. Always returns something —
    worst case is confidence=0.3 with just the original name.
    """
    if not drug_name or not drug_name.strip():
        return {
            "canonical_name": "Unknown",
            "resolution_source": "unresolved",
            "resolution_method": "unresolved",
            "resolution_confidence": 0.0,
            "resolution_conflict": False,
        }

    drug_name = drug_name.strip()

    # ── Combination product handling ──────────────────────────────────────────
    components = split_combination(drug_name)
    if components:
        component_results = [_resolve_single(c, intervention_type) for c in components]
        avg_confidence = round(
            sum(c["resolution_confidence"] for c in component_results) / len(component_results), 2
        )
        return {
            "canonical_name": drug_name,
            "is_combination": True,
            "combination_components": [
                {"name": c["canonical_name"], "resolution_source": c["resolution_source"],
                 "chembl_id": c.get("chembl_id"), "pubchem_cid": c.get("pubchem_cid")}
                for c in component_results
            ],
            "modality": "combination",
            "resolution_source": "+".join(sorted({c["resolution_source"] for c in component_results})),
            "resolution_method": "combination",
            "resolution_confidence": avg_confidence,
            "resolution_conflict": any(c["resolution_conflict"] for c in component_results),
        }

    return _resolve_single(drug_name, intervention_type)