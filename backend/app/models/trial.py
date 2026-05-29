from sqlalchemy import Column, Integer, String, Text, JSON, DateTime
from sqlalchemy.sql import func
from app.database.db import Base


class FailedTrial(Base):
    __tablename__ = "failed_trials"

    id = Column(Integer, primary_key=True, index=True)
    nct_id = Column(String(20), unique=True, index=True, nullable=False)
    title = Column(Text, nullable=True)
    condition = Column(Text, nullable=True)
    drug_name = Column(Text, nullable=True)
    phase = Column(String(50), nullable=True)
    overall_status = Column(String(50), nullable=True)
    why_stopped = Column(Text, nullable=True)
    failure_category = Column(String(100), nullable=True)
    salvageability_score = Column(Integer, nullable=True)
    recommended_actions = Column(JSON, nullable=True)
    sponsor = Column(Text, nullable=True)
    start_date = Column(String(20), nullable=True)
    completion_date = Column(String(20), nullable=True)
    enrollment = Column(Integer, nullable=True)
    data_confidence = Column(String(20), nullable=True)  # low/medium/high
    score_breakdown = Column(JSON, nullable=True)  # Three-tier breakdown
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())