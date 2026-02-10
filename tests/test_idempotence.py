"""Idempotence tests: verify that running the same input twice produces the same output.

Author: Armand Amoussou
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from app.pipelines.steps import (
    step_aggregate_scores,
    step_compute_internal_scores,
    step_load_config,
    step_load_suppliers,
)
from app.schemas.financial_output import (
    EvidenceItem,
    EvidenceSource,
    FinancialRiskOutput,
    RiskLevel,
)

CONFIG_DIR = str(Path(__file__).resolve().parent.parent / "app" / "configs")


class TestIdempotence:
    """Verify that deterministic pipeline steps produce identical results on repeat."""

    @pytest.fixture()
    def config(self) -> dict:  # type: ignore[type-arg]
        return step_load_config(CONFIG_DIR)

    @pytest.fixture()
    def suppliers(self) -> list[dict]:  # type: ignore[type-arg]
        return step_load_suppliers(CONFIG_DIR)

    def test_internal_scores_idempotent(self, config: dict, suppliers: list) -> None:  # type: ignore[type-arg]
        """Same supplier data must produce identical scores every time."""
        for sup in suppliers:
            scores_1 = step_compute_internal_scores(sup, config["thresholds"])
            scores_2 = step_compute_internal_scores(sup, config["thresholds"])
            assert scores_1 == scores_2, (
                f"Non-idempotent for {sup['supplier_id']}: {scores_1} != {scores_2}"
            )

    def test_aggregation_idempotent(self, config: dict) -> None:
        """Same inputs to aggregation must produce identical global score."""
        internal = {"c1_score": 40, "c2_score": 30, "c3_score": 20}
        financial = FinancialRiskOutput(
            supplier_id="SUP-TEST",
            as_of_date=datetime.date(2026, 1, 15),
            financial_risk_score=60,
            financial_risk_level=RiskLevel.MEDIUM,
            confidence=0.7,
            evidence_items=[
                EvidenceItem(
                    source=EvidenceSource.INTERNAL_GOLDEN,
                    url="file://test",
                    doc_id="test",
                    field="test",
                    excerpt="Test evidence",
                    content_hash="hash",
                    observed_at=datetime.date(2026, 1, 10),
                )
            ],
        )

        for _ in range(5):
            result = step_aggregate_scores(
                "SUP-TEST",
                datetime.date(2026, 1, 15),
                internal,
                financial,
                config["weights"],
                config["risk_levels"],
            )
            assert result["global_score"] == result["global_score"]  # self-check

        # Run twice and compare
        r1 = step_aggregate_scores(
            "SUP-TEST",
            datetime.date(2026, 1, 15),
            internal,
            financial,
            config["weights"],
            config["risk_levels"],
        )
        r2 = step_aggregate_scores(
            "SUP-TEST",
            datetime.date(2026, 1, 15),
            internal,
            financial,
            config["weights"],
            config["risk_levels"],
        )
        assert r1 == r2

    def test_anti_hallucination_idempotent(self) -> None:
        """Anti-hallucination enforcement must be idempotent."""
        output = FinancialRiskOutput(
            supplier_id="SUP-TEST",
            as_of_date=datetime.date(2026, 1, 15),
            financial_risk_score=80,
            financial_risk_level=RiskLevel.HIGH,
            confidence=0.9,
            evidence_items=[],
        )
        enforced_1 = output.enforce_anti_hallucination()
        enforced_2 = enforced_1.enforce_anti_hallucination()
        assert enforced_1.financial_risk_level == enforced_2.financial_risk_level
        assert enforced_1.confidence == enforced_2.confidence
        assert enforced_1.data_gaps == enforced_2.data_gaps
