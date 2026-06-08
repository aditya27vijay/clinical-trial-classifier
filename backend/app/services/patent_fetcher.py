"""
Patent Fetcher — USPTO PatentsView API
Fetches patent records for a drug molecule by name or InChIKey.
Free API, no authentication required.
https://patentsview.org/apis/api-endpoints/patents
"""

import time
import logging
import requests
from typing import List, Dict, Optional
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

PATENTSVIEW_URL = "https://api.patentsview.org/patents/query"
REQUEST_DELAY   = 0.5


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def _classify_patent_type(title: Optional[str]) -> str:
    """Infer patent type from title text."""
    if not title:
        return "unknown"
    title_lower = title.lower()
    if any(t in title_lower for t in ["composition", "compound", "salt", "crystalline"]):
        return "composition"
    if any(t in title_lower for t in ["method", "treatment", "treating", "therapy", "use of"]):
        return "method"
    if any(t in title_lower for t in ["formulation", "pharmaceutical", "dosage"]):
        return "formulation"
    if any(t in title_lower for t in ["process", "synthesis", "preparation"]):
        return "process"
    return "other"


def _estimate_expiry(filing_date: Optional[date], grant_date: Optional[date]) -> Optional[date]:
    """
    Estimate US patent expiry:
    - 20 years from earliest filing date (post-GATT 1995 patents)
    - Composition of matter patents can have 5yr extension
    """
    base = filing_date or grant_date
    if not base:
        return None
    return base.replace(year=base.year + 20)


def fetch_patents_for_molecule(
    drug_name: str,
    inchi_key: Optional[str] = None,
    max_results: int = 10,
) -> List[Dict]:
    """
    Fetch patent records for a drug molecule from USPTO PatentsView.

    Searches by drug name in patent title/abstract.
    Returns list of patent dicts mapped to MoleculePatent schema.
    """
    # Build search query — drug name in title or abstract
    query = {
        "_or": [
            {"_text_phrase": {"patent_title": drug_name}},
            {"_text_phrase": {"patent_abstract": drug_name}},
        ]
    }

    payload = {
        "q": query,
        "f": [
            "patent_number",
            "patent_title",
            "patent_date",
            "app_date",
            "patent_abstract",
            "assignee_organization",
            "assignee_country",
            "cpc_category",
        ],
        "o": {"per_page": max_results, "page": 1},
        "s": [{"patent_date": "desc"}],
    }

    try:
        time.sleep(REQUEST_DELAY)
        resp = requests.post(PATENTSVIEW_URL, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error(f"[Patents] PatentsView request failed for '{drug_name}': {e}")
        return []

    patents_raw = data.get("patents") or []
    results = []

    for p in patents_raw:
        filing_date = _parse_date(p.get("app_date"))
        grant_date  = _parse_date(p.get("patent_date"))
        expiry_date = _estimate_expiry(filing_date, grant_date)
        title       = p.get("patent_title", "")

        # Get primary assignee
        assignees = p.get("assignees") or [{}]
        assignee  = assignees[0].get("assignee_organization") if assignees else None
        country   = assignees[0].get("assignee_country", "US") if assignees else "US"

        results.append({
            "patent_number": p.get("patent_number"),
            "title":         title,
            "assignee":      assignee,
            "filing_date":   filing_date,
            "grant_date":    grant_date,
            "expiry_date":   expiry_date,
            "patent_type":   _classify_patent_type(title),
            "country":       country or "US",
            "source":        "uspto",
        })

    logger.info(f"[Patents] Found {len(results)} patents for '{drug_name}'")
    return results


def determine_ip_status(patents: List[Dict]) -> str:
    """
    Determine overall IP status from a list of patent records.
    Returns: 'active', 'expired', or 'unknown'
    """
    if not patents:
        return "unknown"

    today = date.today()
    has_active  = False
    has_expired = False

    for p in patents:
        expiry = p.get("expiry_date")
        if not expiry:
            continue
        # Only composition patents matter for freedom-to-operate
        if p.get("patent_type") in ("composition", "unknown"):
            if expiry > today:
                has_active = True
            else:
                has_expired = True

    if has_active:
        return "active"
    if has_expired:
        return "expired"
    return "unknown"


def get_earliest_filing_date(patents: List[Dict]) -> Optional[date]:
    """Return the earliest filing date across all patent records."""
    dates = [p["filing_date"] for p in patents if p.get("filing_date")]
    return min(dates) if dates else None


def get_latest_expiry_date(patents: List[Dict]) -> Optional[date]:
    """Return the latest expiry date across all patent records."""
    dates = [p["expiry_date"] for p in patents if p.get("expiry_date")]
    return max(dates) if dates else None
