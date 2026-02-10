"""Tests for Pydantic schema validation.

Author: Armand Amoussou
"""

from __future__ import annotations

import datetime

import pytest
from pydantic import ValidationError

from app.schemas.financial_output import (
    AlertPayload,
    EvidenceItem,
    EvidenceSource,
    FinancialRiskOutput,
    GlobalRiskLevel,
    RiskLevel,
    RunAuditRecord,
    SupplierDailyScore,
)


class TestEvidenceItem:
    def test_valid_evidence(self) -> None:
        item = EvidenceItem(
            source=EvidenceSource.OFFICIAL_WEB,
            url="https://example.com/report",
            doc_id="DOC-001",
            field="revenue",
            excerpt="Revenue decreased by 18% in fiscal year 2025.",
            content_hash="abc123def456",
            observed_at=datetime.date(2026, 1, 15),
        )
        assert item.source == EvidenceSource.OFFICIAL_WEB
        assert item.observed_at == datetime.date(2026, 1, 15)

    def test_excerpt_max_length(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceItem(
                source=EvidenceSource.OFFICIAL_WEB,
                url="https://example.com",
                doc_id="DOC-001",
                field="test",
                excerpt="x" * 241,
                content_hash="hash",
                observed_at=datetime.date(2026, 1, 1),
            )

    def test_excerpt_empty_whitespace(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceItem(
                source=EvidenceSource.OFFICIAL_WEB,
                url="https://example.com",
                doc_id="DOC-001",
                field="test",
                excerpt="   ",
                content_hash="hash",
                observed_at=datetime.date(2026, 1, 1),
            )


class TestFinancialRiskOutput:
    def test_valid_output(self) -> None:
        output = FinancialRiskOutput(
            supplier_id="SUP-001",
            as_of_date=datetime.date(2026, 1, 15),
            financial_risk_score=72,
            financial_risk_level=RiskLevel.HIGH,
            confidence=0.75,
            risk_drivers=["DEBT_STRESS", "RATING_DOWNGRADE"],
            recommended_actions=["Review credit terms"],
            data_gaps=[],
            evidence_items=[
                EvidenceItem(
                    source=EvidenceSource.OFFICIAL_WEB,
                    url="https://example.com",
                    doc_id="DOC-001",
                    field="debt_ratio",
                    excerpt="Debt ratio at 87%",
                    content_hash="hash123",
                    observed_at=datetime.date(2026, 1, 10),
                )
            ],
            notes="High risk due to debt stress.",
        )
        assert output.financial_risk_score == 72
        assert output.financial_risk_level == RiskLevel.HIGH

    def test_score_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            FinancialRiskOutput(
                supplier_id="SUP-001",
                as_of_date=datetime.date(2026, 1, 15),
                financial_risk_score=101,
                financial_risk_level=RiskLevel.HIGH,
                confidence=0.5,
            )

    def test_confidence_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            FinancialRiskOutput(
                supplier_id="SUP-001",
                as_of_date=datetime.date(2026, 1, 15),
                financial_risk_score=50,
                financial_risk_level=RiskLevel.MEDIUM,
                confidence=1.5,
            )

    def test_anti_hallucination_no_evidence(self) -> None:
        output = FinancialRiskOutput(
            supplier_id="SUP-001",
            as_of_date=datetime.date(2026, 1, 15),
            financial_risk_score=80,
            financial_risk_level=RiskLevel.HIGH,
            confidence=0.9,
            evidence_items=[],
        )
        enforced = output.enforce_anti_hallucination()
        assert enforced.financial_risk_level == RiskLevel.INDETERMINATE
        assert enforced.confidence <= 0.4
        assert len(enforced.data_gaps) > 0

    def test_anti_hallucination_with_evidence(self) -> None:
        output = FinancialRiskOutput(
            supplier_id="SUP-001",
            as_of_date=datetime.date(2026, 1, 15),
            financial_risk_score=65,
            financial_risk_level=RiskLevel.MEDIUM,
            confidence=0.7,
            evidence_items=[
                EvidenceItem(
                    source=EvidenceSource.OFFICIAL_WEB,
                    url="https://example.com",
                    doc_id="DOC-001",
                    field="score",
                    excerpt="Credit score B+",
                    content_hash="hash",
                    observed_at=datetime.date(2026, 1, 10),
                )
            ],
        )
        enforced = output.enforce_anti_hallucination()
        # Should remain unchanged
        assert enforced.financial_risk_level == RiskLevel.MEDIUM
        assert enforced.confidence == 0.7

    def test_notes_max_length(self) -> None:
        with pytest.raises(ValidationError):
            FinancialRiskOutput(
                supplier_id="SUP-001",
                as_of_date=datetime.date(2026, 1, 15),
                financial_risk_score=50,
                financial_risk_level=RiskLevel.MEDIUM,
                confidence=0.5,
                notes="x" * 401,
            )


class TestSupplierDailyScore:
    def test_valid_score(self) -> None:
        score = SupplierDailyScore(
            as_of_date=datetime.date(2026, 1, 15),
            supplier_id="SUP-001",
            c1_score=30,
            c2_score=45,
            c3_score=20,
            financial_score=65,
            global_score=55,
            risk_level=GlobalRiskLevel.MEDIUM,
        )
        assert score.global_score == 55
        assert score.risk_level == GlobalRiskLevel.MEDIUM

    def test_score_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            SupplierDailyScore(
                as_of_date=datetime.date(2026, 1, 15),
                supplier_id="SUP-001",
                global_score=-1,
                risk_level=GlobalRiskLevel.LOW,
            )


class TestRunAuditRecord:
    def test_valid_audit(self) -> None:
        audit = RunAuditRecord(
            run_id="run_20260115_abc123",
            started_at=datetime.datetime(2026, 1, 15, 10, 0, 0),
            status="RUNNING",
        )
        assert audit.status == "RUNNING"

    def test_invalid_status(self) -> None:
        with pytest.raises(ValidationError):
            RunAuditRecord(
                run_id="run_test",
                started_at=datetime.datetime(2026, 1, 15, 10, 0, 0),
                status="INVALID",
            )
