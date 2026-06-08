"""
SQLAlchemy models for the molecule intelligence layer.
Four tables:
  molecules          — deduplicated master molecule registry
  molecule_trials    — join: which trials a molecule appeared in
  molecule_patents   — USPTO patent records per molecule
  molecule_literature — PubMed references per molecule
"""

from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, JSON,
    DateTime, Date, Boolean, Numeric, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database.db import Base


class Molecule(Base):
    __tablename__ = "molecules"

    id                      = Column(BigInteger, primary_key=True, index=True)

    # ── Identity ──────────────────────────────────────────────────────────────
    canonical_name          = Column(String(500), nullable=False, index=True)
    inn_name                = Column(String(300), nullable=True)
    trade_names             = Column(JSON, nullable=True)   # ["Gleevec", "Glivec"]
    research_codes          = Column(JSON, nullable=True)   # ["STI-571", "CGP57148B"]

    # ── Chemical identifiers ──────────────────────────────────────────────────
    pubchem_cid             = Column(Integer, unique=True, nullable=True, index=True)
    inchi_key               = Column(String(27), unique=True, nullable=True, index=True)
    smiles                  = Column(Text, nullable=True)
    inchi                   = Column(Text, nullable=True)
    chembl_id               = Column(String(20), nullable=True, index=True)
    chembl_pref_name        = Column(String(300), nullable=True)

    # ── Biology ───────────────────────────────────────────────────────────────
    mechanism_of_action     = Column(String(500), nullable=True)
    primary_targets         = Column(JSON, nullable=True)   # ["ABL1", "KIT"]
    target_classes          = Column(JSON, nullable=True)   # ["Kinase", "GPCR"]
    modality                = Column(String(50), nullable=True, index=True)
    molecular_weight        = Column(Numeric(8, 2), nullable=True)
    logp                    = Column(Numeric(5, 2), nullable=True)
    bioavailability_route   = Column(String(50), nullable=True)

    # ── Trial aggregate signals ───────────────────────────────────────────────
    total_trials            = Column(Integer, default=0)
    total_indications       = Column(Integer, default=0)
    failure_categories      = Column(JSON, nullable=True)   # {"Toxicity": 2}
    best_salvageability     = Column(Integer, nullable=True, index=True)
    avg_salvageability      = Column(Numeric(5, 2), nullable=True)
    latest_phase_reached    = Column(String(50), nullable=True)

    # ── Patent ────────────────────────────────────────────────────────────────
    earliest_patent_date    = Column(Date, nullable=True)
    patent_expiry_date      = Column(Date, nullable=True)
    patent_age_years        = Column(Integer, nullable=True)
    is_composition_patent   = Column(Boolean, nullable=True)
    ip_status               = Column(String(30), nullable=True)  # active/expired/unknown

    # ── Literature ────────────────────────────────────────────────────────────
    pubmed_result_count     = Column(Integer, default=0)
    pubmed_background_count = Column(Integer, default=0)
    pmids                   = Column(JSON, nullable=True)

    # ── BD signals ────────────────────────────────────────────────────────────
    has_orphan_designation  = Column(Boolean, default=False)
    has_expanded_access     = Column(Boolean, default=False)
    has_posted_results      = Column(Boolean, default=False)
    repurposing_hypotheses  = Column(JSON, nullable=True)

    # ── Data quality ──────────────────────────────────────────────────────────
    resolution_source       = Column(String(30), nullable=True)   # pubchem/chembl/manual/unresolved
    resolution_confidence   = Column(Numeric(3, 2), nullable=True)

    created_at              = Column(DateTime(timezone=True), server_default=func.now())
    updated_at              = Column(DateTime(timezone=True), onupdate=func.now())

    # ── Relationships ─────────────────────────────────────────────────────────
    trials      = relationship("MoleculeTrial",    back_populates="molecule", cascade="all, delete-orphan")
    patents     = relationship("MoleculePatent",   back_populates="molecule", cascade="all, delete-orphan")
    literature  = relationship("MoleculeLiterature", back_populates="molecule", cascade="all, delete-orphan")


class MoleculeTrial(Base):
    __tablename__ = "molecule_trials"

    id                   = Column(BigInteger, primary_key=True, index=True)
    molecule_id          = Column(BigInteger, ForeignKey("molecules.id", ondelete="CASCADE"), nullable=False)
    nct_id               = Column(String(20), nullable=False, index=True)
    indication           = Column(String(300), nullable=True)
    phase                = Column(String(50), nullable=True)
    failure_category     = Column(String(100), nullable=True)
    salvageability_score = Column(Integer, nullable=True)

    molecule = relationship("Molecule", back_populates="trials")

    __table_args__ = (
        UniqueConstraint("molecule_id", "nct_id", name="uq_molecule_trial"),
    )


class MoleculePatent(Base):
    __tablename__ = "molecule_patents"

    id             = Column(BigInteger, primary_key=True, index=True)
    molecule_id    = Column(BigInteger, ForeignKey("molecules.id", ondelete="CASCADE"), nullable=False)
    patent_number  = Column(String(30), nullable=True)
    title          = Column(Text, nullable=True)
    assignee       = Column(String(300), nullable=True)
    filing_date    = Column(Date, nullable=True)
    grant_date     = Column(Date, nullable=True)
    expiry_date    = Column(Date, nullable=True)
    patent_type    = Column(String(50), nullable=True)   # composition/method/formulation
    country        = Column(String(10), nullable=True)   # US/EP/WO
    source         = Column(String(20), nullable=True)   # uspto/espacenet

    molecule = relationship("Molecule", back_populates="patents")

    __table_args__ = (
        UniqueConstraint("patent_number", "country", name="uq_patent_country"),
    )


class MoleculeLiterature(Base):
    __tablename__ = "molecule_literature"

    id          = Column(BigInteger, primary_key=True, index=True)
    molecule_id = Column(BigInteger, ForeignKey("molecules.id", ondelete="CASCADE"), nullable=False)
    pmid        = Column(String(20), nullable=True)
    title       = Column(Text, nullable=True)
    abstract    = Column(Text, nullable=True)
    pub_date    = Column(Date, nullable=True)
    journal     = Column(String(300), nullable=True)
    ref_type    = Column(String(20), nullable=True)   # result/background/review

    molecule = relationship("Molecule", back_populates="literature")

    __table_args__ = (
        UniqueConstraint("molecule_id", "pmid", name="uq_molecule_pmid"),
    )
