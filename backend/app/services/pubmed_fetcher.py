"""
PubMed Fetcher — NCBI E-utilities
Fetches publications for a drug molecule by name or PMID.

Rate limits:
  - With API key:    10 req/sec
  - Without API key: 3 req/sec

Set NCBI_API_KEY in environment for higher throughput.
Get free key at: https://www.ncbi.nlm.nih.gov/account/
"""

import os
import time
import logging
import requests
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from datetime import date, datetime

logger = logging.getLogger(__name__)

NCBI_API_KEY  = os.getenv("NCBI_API_KEY", "")
ESEARCH_URL   = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL    = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
REQUEST_DELAY = 0.1 if NCBI_API_KEY else 0.34   # 10/sec with key, 3/sec without


def _ncbi_params(extra: dict = None) -> dict:
    """Base params for all NCBI requests."""
    params = {"retmode": "json", "db": "pubmed"}
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    if extra:
        params.update(extra)
    return params


def _parse_pub_date(article: ET.Element) -> Optional[date]:
    """Extract publication date from PubMed XML article element."""
    for date_elem in article.findall(".//PubDate"):
        year  = date_elem.findtext("Year")
        month = date_elem.findtext("Month") or "01"
        day   = date_elem.findtext("Day") or "01"
        if year:
            try:
                month_num = int(month) if month.isdigit() else {
                    "Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
                    "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12
                }.get(month[:3], 1)
                return date(int(year), month_num, int(day))
            except (ValueError, TypeError):
                pass
    return None


def search_pubmed(drug_name: str, max_results: int = 20) -> List[str]:
    """
    Search PubMed for publications mentioning a drug name.
    Returns list of PMIDs.
    """
    query = f'"{drug_name}"[Title/Abstract] OR "{drug_name}"[MeSH Terms]'
    time.sleep(REQUEST_DELAY)

    try:
        resp = requests.get(ESEARCH_URL, params=_ncbi_params({
            "term":    query,
            "retmax":  max_results,
            "sort":    "relevance",
            "retmode": "json",
        }), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        pmids = data.get("esearchresult", {}).get("idlist", [])
        logger.info(f"[PubMed] '{drug_name}' → {len(pmids)} PMIDs")
        return pmids
    except requests.RequestException as e:
        logger.error(f"[PubMed] Search failed for '{drug_name}': {e}")
        return []


def fetch_abstracts(pmids: List[str]) -> List[Dict]:
    """
    Fetch full abstract data for a list of PMIDs.
    Returns list of publication dicts mapped to MoleculeLiterature schema.
    """
    if not pmids:
        return []

    # Batch in chunks of 20 to avoid URL length limits
    results = []
    for i in range(0, len(pmids), 20):
        chunk = pmids[i:i+20]
        time.sleep(REQUEST_DELAY)

        try:
            resp = requests.get(EFETCH_URL, params={
                "db":      "pubmed",
                "id":      ",".join(chunk),
                "rettype": "abstract",
                "retmode": "xml",
                **({"api_key": NCBI_API_KEY} if NCBI_API_KEY else {}),
            }, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"[PubMed] Fetch failed for chunk: {e}")
            continue

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as e:
            logger.error(f"[PubMed] XML parse error: {e}")
            continue

        for article in root.findall(".//PubmedArticle"):
            pmid_elem = article.find(".//PMID")
            pmid      = pmid_elem.text if pmid_elem is not None else None

            title_elem   = article.find(".//ArticleTitle")
            title        = "".join(title_elem.itertext()) if title_elem is not None else None

            # Concatenate all AbstractText sections
            abstract_parts = []
            for part in article.findall(".//AbstractText"):
                label = part.get("Label", "")
                text  = "".join(part.itertext())
                if label:
                    abstract_parts.append(f"{label}: {text}")
                else:
                    abstract_parts.append(text)
            abstract = " ".join(abstract_parts) if abstract_parts else None

            journal_elem = article.find(".//Journal/Title")
            journal      = journal_elem.text if journal_elem is not None else None

            pub_date = _parse_pub_date(article)

            # Classify reference type from publication type tags
            pub_types = [pt.text for pt in article.findall(".//PublicationType") if pt.text]
            if any("Clinical Trial" in pt or "Randomized" in pt for pt in pub_types):
                ref_type = "result"
            elif any("Review" in pt or "Meta-Analysis" in pt for pt in pub_types):
                ref_type = "review"
            else:
                ref_type = "background"

            if pmid and title:
                results.append({
                    "pmid":     pmid,
                    "title":    title,
                    "abstract": abstract,
                    "pub_date": pub_date,
                    "journal":  journal,
                    "ref_type": ref_type,
                })

    logger.info(f"[PubMed] Fetched {len(results)} abstracts")
    return results


def fetch_literature_for_molecule(
    drug_name: str,
    max_results: int = 20,
) -> List[Dict]:
    """
    Full pipeline: search PubMed → fetch abstracts → return structured records.
    """
    pmids = search_pubmed(drug_name, max_results=max_results)
    if not pmids:
        return []
    return fetch_abstracts(pmids)
