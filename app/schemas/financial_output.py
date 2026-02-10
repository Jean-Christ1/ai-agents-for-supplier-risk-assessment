"""Pydantic v2 schemas for financial risk scoring output.

Author: Armand Amoussou
"""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    INDETERMINATE = "INDETERMINATE"


class EvidenceSource(str, Enum):
    OFFICIAL_WEB = "OFFICIAL_WEB"
    INTERNAL_GOLDEN = "INTERNAL_GOLDEN"


class EvidenceItem(BaseModel):
    source: EvidenceSource
    url: str = Field(..., min_length=1)
    doc_id: str = Field(..., min_length=1)
    field: str = Field(..., min_length=1)
    excerpt: str = Field(..., max_length=240)
    content_hash: str = Field(..., min_length=1)
    observed_at: datetime.date

    @field_validator("excerpt")
    @classmethod
    def excerpt_not_empty(cls, v: str) -> str:
        if not v.strip():
            msg = "excerpt must contain non-whitespace text"
            raise ValueError(msg)
        return v


class FinancialRiskOutput(BaseModel):
    supplier_id: str = Field(..., min_length=1)
    as_of_date: datetime.date
    financial_risk_score: int = Field(..., ge=0, le=100)
    financial_risk_level: RiskLevel
    confidence: float = Field(..., ge=0.0, le=1.0)
    risk_drivers: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    notes: str = Field(default="", max_length=400)

    def enforce_anti_hallucination(self) -> FinancialRiskOutput:
        """Post-validation: if evidence_items < 1, force INDETERMINATE."""
        if len(self.evidence_items) < 1:
            return self.model_copy(
                update={
                    "financial_risk_level": RiskLevel.INDETERMINATE,
                    "confidence": min(self.confidence, 0.4),
                    "data_gaps": self.data_gaps
                    if self.data_gaps
                    else ["No evidence items available"],
                }
            )
        return self


class GlobalRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SupplierDailyScore(BaseModel):
    as_of_date: datetime.date
    supplier_id: str
    c1_score: Optional[int] = Field(None, ge=0, le=100)
    c2_score: Optional[int] = Field(None, ge=0, le=100)
    c3_score: Optional[int] = Field(None, ge=0, le=100)
    financial_score: Optional[int] = Field(None, ge=0, le=100)
    global_score: int = Field(..., ge=0, le=100)
    risk_level: GlobalRiskLevel


class AlertPayload(BaseModel):
    supplier_id: str
    supplier_name: str
    as_of_date: datetime.date
    global_score: int
    financial_score: Optional[int] = None
    previous_risk_level: Optional[str] = None
    current_risk_level: str
    risk_drivers: list[str] = Field(default_factory=list)
    top_evidences: list[EvidenceItem] = Field(default_factory=list, max_length=3)
    recommended_actions: list[str] = Field(default_factory=list)
    trigger_reason: str


class RunAuditRecord(BaseModel):
    run_id: str
    started_at: datetime.datetime
    finished_at: Optional[datetime.datetime] = None
    status: str = Field(..., pattern=r"^(RUNNING|SUCCESS|FAILED|PARTIAL)$")
    errors: Optional[list[dict]] = None  # type: ignore[type-arg]
    llm_cost_estimate: float = 0.0
    counts: Optional[dict] = None  # type: ignore[type-arg]
