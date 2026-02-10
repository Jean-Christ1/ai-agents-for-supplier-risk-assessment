"""Golden test suite: validates pipeline outputs against expected results.

Author: Armand Amoussou

Uses local golden test data (no internet required) to verify:
- Content parsing works correctly
- Internal scoring is deterministic and correct
- Schema validation works end-to-end
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
import yaml

from app.pipelines.steps import (
    step_compute_internal_scores,
    step_load_config,
    step_load_suppliers,
    step_normalize_documents,
)
from app.tools.cache import content_hash
from app.tools.json_validate import build_indeterminate_output, validate_financial_output
from app.tools.web_parse import extract_snippets, parse_html_to_text

# Path to config and golden data
CONFIG_DIR = str(Path(__file__).resolve().parent.parent / "app" / "configs")
GOLDEN_DIR = str(Path(__file__).resolve().parent.parent / "app" / "golden")


class TestGoldenContentParsing:
    """Test that golden files are correctly parsed."""

    def test_parse_sup005_bodacc(self) -> None:
        path = Path(GOLDEN_DIR) / "cases" / "SUP-005_bodacc.txt"
        if not path.exists():
            pytest.skip("Golden file not available")
        content = path.read_text(encoding="utf-8")
        # This is plain text, not HTML, so parse_html_to_text may return None
        # but extract_snippets should work on raw text
        snippets = extract_snippets(content)
        assert len(snippets) > 0
        # Should contain key financial distress terms
        full_text = " ".join(snippets).lower()
        assert "redressement" in full_text or "procedure" in full_text

    def test_parse_sup002_financial(self) -> None:
        path = Path(GOLDEN_DIR) / "cases" / "SUP-002_financial.txt"
        if not path.exists():
            pytest.skip("Golden file not available")
        content = path.read_text(encoding="utf-8")
        snippets = extract_snippets(content)
        assert len(snippets) > 0
        full_text = " ".join(snippets).lower()
        assert "stable" in full_text or "solide" in full_text


class TestGoldenInternalScoring:
    """Test deterministic scoring against golden supplier data."""

    @pytest.fixture()
    def config(self) -> dict:  # type: ignore[type-arg]
        return step_load_config(CONFIG_DIR)

    @pytest.fixture()
    def suppliers(self) -> list[dict]:  # type: ignore[type-arg]
        return step_load_suppliers(CONFIG_DIR)

    def test_sup002_low_risk_internal(self, config: dict, suppliers: list) -> None:  # type: ignore[type-arg]
        """MetalWerk GmbH: zero delays, zero incidents -> low scores."""
        sup = next(s for s in suppliers if s["supplier_id"] == "SUP-002")
        scores = step_compute_internal_scores(sup, config["thresholds"])
        assert scores["c1_score"] == 0
        assert scores["c2_score"] < 20
        assert scores["c3_score"] < 10

    def test_sup005_high_risk_internal(self, config: dict, suppliers: list) -> None:  # type: ignore[type-arg]
        """ElektronikParts AG: many delays, critical monosource -> high scores."""
        sup = next(s for s in suppliers if s["supplier_id"] == "SUP-005")
        scores = step_compute_internal_scores(sup, config["thresholds"])
        assert scores["c1_score"] >= 70
        assert scores["c2_score"] >= 50
        assert scores["c3_score"] >= 40

    def test_sup003_high_risk_monosource(self, config: dict, suppliers: list) -> None:  # type: ignore[type-arg]
        """RoueExpress SARL: many delays, monosource, critical -> high."""
        sup = next(s for s in suppliers if s["supplier_id"] == "SUP-003")
        scores = step_compute_internal_scores(sup, config["thresholds"])
        assert scores["c1_score"] >= 60
        assert scores["c2_score"] >= 50

    def test_sup009_zero_risk_internal(self, config: dict, suppliers: list) -> None:  # type: ignore[type-arg]
        """NordicBolt AB: perfect delivery, low criticality, long history."""
        sup = next(s for s in suppliers if s["supplier_id"] == "SUP-009")
        scores = step_compute_internal_scores(sup, config["thresholds"])
        assert scores["c1_score"] == 0
        assert scores["c2_score"] < 10
        assert scores["c3_score"] == 0

    def test_all_suppliers_score_in_range(self, config: dict, suppliers: list) -> None:  # type: ignore[type-arg]
        """All 20 suppliers must produce valid scores in [0,100]."""
        for sup in suppliers:
            scores = step_compute_internal_scores(sup, config["thresholds"])
            for key in ("c1_score", "c2_score", "c3_score"):
                assert 0 <= scores[key] <= 100, (
                    f"{sup['supplier_id']}.{key} = {scores[key]}"
                )


class TestGoldenFinancialValidation:
    """Test schema validation with golden data patterns."""

    def test_valid_high_risk(self) -> None:
        data = {
            "supplier_id": "SUP-005",
            "as_of_date": "2026-01-15",
            "financial_risk_score": 85,
            "financial_risk_level": "HIGH",
            "confidence": 0.8,
            "risk_drivers": ["PROCEEDING", "DEBT_STRESS"],
            "recommended_actions": ["Immediate review", "Find backup supplier"],
            "data_gaps": [],
            "evidence_items": [
                {
                    "source": "INTERNAL_GOLDEN",
                    "url": "file://golden/SUP-005_bodacc.txt",
                    "doc_id": "SUP-005_bodacc",
                    "field": "procedure_type",
                    "excerpt": "Ouverture de procedure de redressement judiciaire",
                    "content_hash": "abc123",
                    "observed_at": "2026-01-15",
                },
                {
                    "source": "INTERNAL_GOLDEN",
                    "url": "file://golden/SUP-005_financial.txt",
                    "doc_id": "SUP-005_financial",
                    "field": "debt_ratio",
                    "excerpt": "Ratio d'endettement: 87%",
                    "content_hash": "def456",
                    "observed_at": "2026-01-12",
                },
            ],
            "notes": "Critical financial distress confirmed.",
        }
        output, errors = validate_financial_output(data)
        assert output is not None
        assert len(errors) == 0
        assert output.financial_risk_level.value == "HIGH"
        assert len(output.evidence_items) == 2

    def test_indeterminate_no_evidence(self) -> None:
        output = build_indeterminate_output(
            "SUP-999", "2026-01-15", "No data available"
        )
        assert output.financial_risk_level.value == "INDETERMINATE"
        assert output.confidence <= 0.4
        assert len(output.data_gaps) > 0
        assert output.financial_risk_score == 50
