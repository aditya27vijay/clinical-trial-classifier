"""
Molecules API Router
/molecules/         — list + filter
/molecules/stats    — dashboard statistics
/molecules/export   — BD Excel export
/molecules/{id}     — full detail
/molecules/{id}/hypotheses — trigger LLM repurposing hypothesis generation
"""

import io
import json
import logging
import os
from typing import Optional, List, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.db import get_db, SessionLocal
from app.models.molecule_model import Molecule, MoleculeTrial, MoleculePatent, MoleculeLiterature
from app.services import molecule_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class PatentOut(BaseModel):
    id:            int
    patent_number: Optional[str]
    title:         Optional[str]
    assignee:      Optional[str]
    filing_date:   Optional[Any]
    expiry_date:   Optional[Any]
    patent_type:   Optional[str]
    country:       Optional[str]
    class Config:
        from_attributes = True


class LiteratureOut(BaseModel):
    id:       int
    pmid:     Optional[str]
    title:    Optional[str]
    abstract: Optional[str]
    pub_date: Optional[Any]
    journal:  Optional[str]
    ref_type: Optional[str]
    class Config:
        from_attributes = True


class TrialLinkOut(BaseModel):
    nct_id:               str
    indication:           Optional[str]
    phase:                Optional[str]
    failure_category:     Optional[str]
    salvageability_score: Optional[int]
    class Config:
        from_attributes = True


class MoleculeListItem(BaseModel):
    id:                     int
    canonical_name:         str
    inn_name:               Optional[str]
    modality:               Optional[str]
    mechanism_of_action:    Optional[str]
    primary_targets:        Optional[Any]
    total_trials:           Optional[int]
    total_indications:      Optional[int]
    best_salvageability:    Optional[int]
    avg_salvageability:     Optional[Any]
    latest_phase_reached:   Optional[str]
    ip_status:              Optional[str]
    patent_expiry_date:     Optional[Any]
    pubmed_result_count:    Optional[int]
    has_posted_results:     Optional[bool]
    has_expanded_access:    Optional[bool]
    failure_categories:     Optional[Any]
    resolution_confidence:  Optional[Any]
    resolution_source:      Optional[str]
    class Config:
        from_attributes = True


class MoleculeDetail(MoleculeListItem):
    pubchem_cid:             Optional[int]
    inchi_key:               Optional[str]
    smiles:                  Optional[str]
    chembl_id:               Optional[str]
    molecular_weight:        Optional[Any]
    logp:                    Optional[Any]
    trade_names:             Optional[Any]
    research_codes:          Optional[Any]
    target_classes:          Optional[Any]
    repurposing_hypotheses:  Optional[Any]
    pubmed_background_count: Optional[int]
    pmids:                   Optional[Any]
    earliest_patent_date:    Optional[Any]
    is_composition_patent:   Optional[bool]
    trials:                  List[TrialLinkOut] = []
    patents:                 List[PatentOut]    = []
    literature:              List[LiteratureOut] = []
    class Config:
        from_attributes = True


class MoleculeListResponse(BaseModel):
    total:     int
    page:      int
    page_size: int
    results:   List[MoleculeListItem]


class MoleculeStatsResponse(BaseModel):
    total_molecules:   int
    resolved_count:    int
    resolution_rate:   float
    by_modality:       dict
    by_ip_status:      dict
    avg_salvageability: float
    top_molecules:     List[MoleculeListItem]


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/", response_model=MoleculeListResponse)
def list_molecules(
    page:             int           = Query(1, ge=1),
    page_size:        int           = Query(20, ge=1, le=100),
    search:           Optional[str] = Query(None),
    modality:         Optional[str] = Query(None),
    min_score:        Optional[int] = Query(None, ge=0, le=100),
    max_score:        Optional[int] = Query(None, ge=0, le=100),
    ip_status:        Optional[str] = Query(None),
    has_results:      Optional[bool] = Query(None),
    has_publications: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    """List molecules with pagination and filters."""
    skip = (page - 1) * page_size
    total, results = molecule_service.get_molecules(
        db,
        skip=skip,
        limit=page_size,
        search=search,
        modality=modality,
        min_score=min_score,
        max_score=max_score,
        ip_status=ip_status,
        has_results=has_results,
        has_publications=has_publications,
    )
    return MoleculeListResponse(
        total=total,
        page=page,
        page_size=page_size,
        results=results,
    )


@router.get("/stats", response_model=MoleculeStatsResponse)
def molecule_stats(db: Session = Depends(get_db)):
    """Dashboard statistics for the molecule library."""
    return molecule_service.get_molecule_stats(db)


@router.get("/export")
def export_molecules(
    min_score: Optional[int] = Query(None),
    modality:  Optional[str] = Query(None),
    ip_status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Export molecules as a BD-ready Excel file.
    Filters: min_score, modality, ip_status.
    """
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl not installed")

    _, molecules = molecule_service.get_molecules(
        db,
        skip=0,
        limit=10000,
        modality=modality,
        min_score=min_score,
        ip_status=ip_status,
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Molecule Intelligence"

    # Header
    headers = [
        "Molecule Name", "INN Name", "Trade Names", "Modality",
        "Mechanism of Action", "Primary Targets", "Phase Reached",
        "Indications Tried", "Total Trials", "Failure Categories",
        "Best Score", "Avg Score", "Data IP Status", "Patent Expiry",
        "PubMed Result Count", "Has Results Posted", "Has Expanded Access",
        "Rescue Recommendations", "PubChem CID", "ChEMBL ID",
        "Resolution Confidence", "InChIKey",
    ]

    # Style header row
    header_fill = PatternFill("solid", fgColor="1a1a2e")
    header_font = Font(bold=True, color="FFFFFF")
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    # Data rows
    for row_idx, mol in enumerate(molecules, 2):
        hypotheses = mol.repurposing_hypotheses
        if isinstance(hypotheses, list):
            hyp_text = "; ".join(hypotheses[:3])
        else:
            hyp_text = str(hypotheses) if hypotheses else ""

        ws.append([
            mol.canonical_name,
            mol.inn_name or "",
            ", ".join(mol.trade_names or []),
            mol.modality or "",
            mol.mechanism_of_action or "",
            ", ".join(mol.primary_targets or []),
            mol.latest_phase_reached or "",
            mol.total_indications or 0,
            mol.total_trials or 0,
            json.dumps(mol.failure_categories or {}),
            mol.best_salvageability or "",
            float(mol.avg_salvageability) if mol.avg_salvageability else "",
            mol.ip_status or "unknown",
            str(mol.patent_expiry_date) if mol.patent_expiry_date else "",
            mol.pubmed_result_count or 0,
            "Yes" if mol.has_posted_results else "No",
            "Yes" if mol.has_expanded_access else "No",
            hyp_text,
            mol.pubchem_cid or "",
            mol.chembl_id or "",
            float(mol.resolution_confidence) if mol.resolution_confidence else "",
            mol.inchi_key or "",
        ])

    # Auto-size columns
    for col in ws.columns:
        max_len = max((len(str(cell.value or "")) for cell in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 50)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename  = f"peptris_molecule_intelligence_{timestamp}.xlsx"

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/{molecule_id}", response_model=MoleculeDetail)
def get_molecule(molecule_id: int, db: Session = Depends(get_db)):
    """Full molecule detail including trials, patents, and literature."""
    mol = molecule_service.get_molecule_by_id(db, molecule_id)
    if not mol:
        raise HTTPException(status_code=404, detail="Molecule not found")
    return mol


@router.post("/{molecule_id}/hypotheses")
def generate_repurposing_hypotheses(
    molecule_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Trigger on-demand LLM repurposing hypothesis generation for a molecule.
    Returns immediately — generation runs in background and is cached in DB.
    """
    mol = molecule_service.get_molecule_by_id(db, molecule_id)
    if not mol:
        raise HTTPException(status_code=404, detail="Molecule not found")

    if mol.repurposing_hypotheses:
        return {
            "status": "cached",
            "hypotheses": mol.repurposing_hypotheses,
        }

    background_tasks.add_task(_generate_hypotheses_task, molecule_id)
    return {
        "status": "generating",
        "message": "Hypothesis generation started. Refresh molecule detail in ~10 seconds.",
    }


def _generate_hypotheses_task(molecule_id: int):
    """Background task: generate repurposing hypotheses via Groq."""
    import requests as http_requests

    db  = SessionLocal()
    try:
        mol = molecule_service.get_molecule_by_id(db, molecule_id)
        if not mol:
            return

        groq_key   = os.getenv("GROQ_API_KEY", "")
        groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

        if not groq_key:
            logger.warning("[Hypotheses] No GROQ_API_KEY set")
            return

        # Build prompt from molecule data
        targets  = ", ".join(mol.primary_targets or []) or "unknown"
        failed_in = ", ".join([
            f"{t.indication or 'unknown indication'} ({t.failure_category or 'unknown reason'})"
            for t in mol.trials[:5]
        ]) if mol.trials else "unknown"

        prompt = f"""You are a drug repurposing expert.

Molecule: {mol.canonical_name}
Modality: {mol.modality or 'unknown'}
Mechanism: {mol.mechanism_of_action or 'unknown'}
Primary targets: {targets}
Failed in: {failed_in}
Phase reached: {mol.latest_phase_reached or 'unknown'}

Generate 3-5 specific, scientifically grounded repurposing hypotheses for this molecule.
Each hypothesis must:
1. Name the specific new indication
2. Explain the mechanistic rationale (why the target/mechanism is relevant)
3. Cite any known disease biology that supports the connection

Return ONLY a JSON array of strings, no preamble:
["hypothesis 1...", "hypothesis 2...", ...]"""

        resp = http_requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {groq_key}",
                "Content-Type": "application/json",
            },
            json={
                "model":    groq_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 800,
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw  = resp.json()["choices"][0]["message"]["content"]
        data = json.loads(raw)

        # Handle both {"hypotheses": [...]} and [...] response shapes
        if isinstance(data, list):
            hypotheses = data
        elif isinstance(data, dict):
            hypotheses = data.get("hypotheses") or list(data.values())[0]
        else:
            hypotheses = [str(data)]

        mol.repurposing_hypotheses = hypotheses
        db.commit()
        logger.info(f"[Hypotheses] Generated {len(hypotheses)} hypotheses for molecule {molecule_id}")

    except Exception as e:
        logger.error(f"[Hypotheses] Generation failed for molecule {molecule_id}: {e}")
    finally:
        db.close()
