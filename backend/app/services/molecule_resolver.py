"""
Molecule Resolver — PubChem + ChEMBL
Resolves drug names → InChIKey → SMILES → targets → mechanism

Resolution chain:
  1. PubChem exact name lookup
  2. PubChem synonym search
  3. INN stem pre-processing (biologics: -mab, -nib, -zumab)
  4. ChEMBL name search
  5. Mark unresolved (confidence 0.3)

All results are cached in-memory per session to avoid redundant API calls.
"""

import re
import time
import logging
import requests
from typing import Dict, Optional, Tuple
from functools import lru_cache

logger = logging.getLogger(__name__)

PUBCHEM_BASE  = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
CHEMBL_BASE   = "https://www.ebi.ac.uk/chembl/api/data"
REQUEST_DELAY = 0.34   # 3 req/sec PubChem polite limit

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


def _detect_modality_from_name(name: str) -> Optional[str]:
    """Quick modality detection from INN stem before API calls."""
    name_lower = name.lower()
    for stem, modality in INN_STEMS.items():
        if name_lower.endswith(stem):
            return modality
    return None


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


def resolve_pubchem_by_name(drug_name: str) -> Optional[dict]:
    """
    Look up a drug name in PubChem.
    Returns resolved fields or None if not found.
    """
    # Try exact name first
    data = _pubchem_request(f"compound/name/{requests.utils.quote(drug_name)}/JSON")
    if not data:
        # Try synonym search
        syn_data = _pubchem_request(f"compound/name/{requests.utils.quote(drug_name)}/cids/JSON")
        if not syn_data:
            return None
        cids = syn_data.get("IdentifierList", {}).get("CID", [])
        if not cids:
            return None
        data = _pubchem_request(f"compound/cid/{cids[0]}/JSON")

    if not data:
        return None

    compounds = data.get("PC_Compounds", [])
    if not compounds:
        return None

    compound = compounds[0]
    cid = compound.get("id", {}).get("id", {}).get("cid")
    props = _extract_pubchem_props(compound)

    if not props.get("inchi_key"):
        return None

    return {
        "pubchem_cid":      cid,
        "inchi_key":        props.get("inchi_key"),
        "smiles":           props.get("smiles"),
        "inchi":            props.get("inchi"),
        "molecular_weight": props.get("molecular_weight"),
        "logp":             props.get("logp"),
        "resolution_source": "pubchem",
        "resolution_confidence": 0.95,
    }


def resolve_chembl_by_name(drug_name: str) -> Optional[dict]:
    """
    Look up a drug name in ChEMBL for targets and mechanism.
    Returns enrichment fields or None.
    """
    data = _chembl_request("molecule.json", params={
        "pref_name__iexact": drug_name,
        "limit": 1,
    })

    # Fallback: search by synonym
    if not data or not data.get("molecules"):
        data = _chembl_request("molecule.json", params={
            "molecule_synonyms__molecule_synonym__iexact": drug_name,
            "limit": 1,
        })

    if not data or not data.get("molecules"):
        return None

    mol = data["molecules"][0]
    chembl_id = mol.get("molecule_chembl_id")

    # Get mechanism of action
    mech_data = _chembl_request(f"mechanism.json", params={
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
                # Get target name
                tgt = _chembl_request(f"target/{m['target_chembl_id']}.json")
                if tgt:
                    targets.append(tgt.get("pref_name", m["target_chembl_id"]))
                    for comp in tgt.get("target_components", []):
                        for cls in comp.get("target_component_synonyms", []):
                            if cls.get("syn_type") == "GENE_SYMBOL":
                                target_classes.append(cls.get("component_synonym"))

    props = mol.get("molecule_properties") or {}

    return {
        "chembl_id":          chembl_id,
        "chembl_pref_name":   mol.get("pref_name"),
        "mechanism_of_action": mechanisms[0] if mechanisms else None,
        "primary_targets":    targets[:5],
        "target_classes":     list(set(target_classes))[:5],
        "molecular_weight":   props.get("full_mwt"),
        "logp":               props.get("alogp"),
        "resolution_source":  "chembl",
        "resolution_confidence": 0.85,
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


def resolve(drug_name: str, intervention_type: str = None) -> dict:
    """
    Main entry point. Resolve a drug name to full chemical identity.

    Returns a dict with all available fields. Always returns something —
    worst case is confidence=0.3 with just the original name.
    """
    if not drug_name or not drug_name.strip():
        return {
            "canonical_name": "Unknown",
            "resolution_source": "unresolved",
            "resolution_confidence": 0.0,
        }

    drug_name = drug_name.strip()

    # Quick modality detection from INN stem (before API calls)
    modality = _detect_modality_from_name(drug_name)
    if intervention_type:
        t = intervention_type.upper()
        if t == "GENETIC":
            modality = "gene_therapy"
        elif t == "BIOLOGICAL":
            modality = "biologic_antibody"
        elif t == "DRUG":
            modality = modality or "small_molecule"

    result = {
        "canonical_name": drug_name,
        "modality":       modality,
        "resolution_source": "unresolved",
        "resolution_confidence": 0.3,
    }

    # ── Step 1: PubChem lookup ────────────────────────────────────────────────
    pubchem = resolve_pubchem_by_name(drug_name)
    if pubchem:
        result.update(pubchem)
        logger.info(f"[Resolver] PubChem: {drug_name} → CID={pubchem.get('pubchem_cid')} InChIKey={pubchem.get('inchi_key')}")

        # ── Step 2: ChEMBL enrichment ─────────────────────────────────────────
        chembl = resolve_chembl_by_name(drug_name)
        if chembl:
            # ChEMBL fills in targets/mechanism — don't overwrite InChIKey from PubChem
            for k, v in chembl.items():
                if k not in result or result[k] is None:
                    result[k] = v
            result["resolution_confidence"] = 0.97
            result["resolution_source"] = "pubchem+chembl"
            logger.info(f"[Resolver] ChEMBL enriched: {drug_name} → {chembl.get('chembl_id')}")
    else:
        # ── Step 3: ChEMBL only fallback ─────────────────────────────────────
        chembl = resolve_chembl_by_name(drug_name)
        if chembl:
            result.update(chembl)
            logger.info(f"[Resolver] ChEMBL only: {drug_name} → {chembl.get('chembl_id')}")
        else:
            logger.info(f"[Resolver] Unresolved: {drug_name}")

    return result
