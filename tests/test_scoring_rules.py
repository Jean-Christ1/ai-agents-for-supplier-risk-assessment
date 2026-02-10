"""Tests for deterministic internal scoring rules.

Author: Armand Amoussou
"""

from __future__ import annotations

import pytest

from app.tools.scoring_rules import (
    compute_c1_score,
    compute_c2_score,
    compute_c3_score,
    compute_global_score,
    determine_risk_level,
)


# Default thresholds matching thresholds.yml
DEFAULT_THRESHOLDS = {
    "c1": {
        "delay_low": 2,
        "delay_high": 8,
        "severity_low": 2.0,
        "severity_high": 7.0,
        "quality_low": 1,
        "quality_high": 5,
    },
    "c2": {
        "monosource_penalty": 50,
        "criticality_scores": {"LOW": 10, "MEDIUM": 30, "HIGH": 50, "CRITICAL": 80},
    },
    "c3": {
        "maturity_low_years": 3,
        "maturity_high_years": 10,
        "litigation_scores": {0: 0, 1: 30, 2: 55, 3: 75},
    },
}

DEFAULT_WEIGHTS = {
    "c1_delivery_performance": 0.20,
    "c2_dependency_criticality": 0.15,
    "c3_relationship_history": 0.15,
    "c4_financial_risk": 0.50,
}


class TestC1Score:
    """C1: Delivery Performance."""

    def test_perfect_supplier(self) -> None:
        signals = {
            "delivery_delays_last_12m": 0,
            "avg_delay_days": 0.0,
            "quality_incidents_last_12m": 0,
        }
        score = compute_c1_score(signals, DEFAULT_THRESHOLDS)
        assert score == 0

    def test_terrible_supplier(self) -> None:
        signals = {
            "delivery_delays_last_12m": 12,
            "avg_delay_days": 10.0,
            "quality_incidents_last_12m": 8,
        }
        score = compute_c1_score(signals, DEFAULT_THRESHOLDS)
        assert score == 100

    def test_medium_supplier(self) -> None:
        signals = {
            "delivery_delays_last_12m": 5,
            "avg_delay_days": 4.5,
            "quality_incidents_last_12m": 3,
        }
        score = compute_c1_score(signals, DEFAULT_THRESHOLDS)
        assert 30 <= score <= 70

    def test_low_threshold(self) -> None:
        signals = {
            "delivery_delays_last_12m": 2,
            "avg_delay_days": 2.0,
            "quality_incidents_last_12m": 1,
        }
        score = compute_c1_score(signals, DEFAULT_THRESHOLDS)
        assert score == 0

    def test_score_range(self) -> None:
        signals = {
            "delivery_delays_last_12m": 4,
            "avg_delay_days": 3.0,
            "quality_incidents_last_12m": 2,
        }
        score = compute_c1_score(signals, DEFAULT_THRESHOLDS)
        assert 0 <= score <= 100


class TestC2Score:
    """C2: Dependency / Criticality."""

    def test_non_critical_non_mono(self) -> None:
        signals = {"is_monosource": False, "criticality": "LOW"}
        score = compute_c2_score(signals, DEFAULT_THRESHOLDS)
        assert score == 5  # (10 + 0) / 2

    def test_critical_monosource(self) -> None:
        signals = {"is_monosource": True, "criticality": "CRITICAL"}
        score = compute_c2_score(signals, DEFAULT_THRESHOLDS)
        assert score == 65  # (80 + 50) / 2

    def test_monosource_low_criticality(self) -> None:
        signals = {"is_monosource": True, "criticality": "LOW"}
        score = compute_c2_score(signals, DEFAULT_THRESHOLDS)
        assert score == 30  # (10 + 50) / 2


class TestC3Score:
    """C3: Relationship History."""

    def test_long_clean_history(self) -> None:
        signals = {"contract_years": 15, "litigation_count": 0}
        score = compute_c3_score(signals, DEFAULT_THRESHOLDS)
        assert score == 0

    def test_short_litigious(self) -> None:
        signals = {"contract_years": 1, "litigation_count": 3}
        score = compute_c3_score(signals, DEFAULT_THRESHOLDS)
        assert score >= 75

    def test_medium_history(self) -> None:
        signals = {"contract_years": 6, "litigation_count": 1}
        score = compute_c3_score(signals, DEFAULT_THRESHOLDS)
        assert 15 <= score <= 50


class TestGlobalScore:
    def test_all_low(self) -> None:
        score = compute_global_score(10, 10, 10, 10, DEFAULT_WEIGHTS)
        assert score == 10

    def test_all_high(self) -> None:
        score = compute_global_score(90, 90, 90, 90, DEFAULT_WEIGHTS)
        assert score == 90

    def test_financial_dominates(self) -> None:
        """Financial has 50% weight, so it should dominate."""
        score = compute_global_score(0, 0, 0, 100, DEFAULT_WEIGHTS)
        assert score == 50

    def test_none_financial(self) -> None:
        """When financial is None, redistribute weight to internals."""
        score = compute_global_score(50, 50, 50, None, DEFAULT_WEIGHTS)
        assert score == 50

    def test_score_clamped(self) -> None:
        score = compute_global_score(100, 100, 100, 100, DEFAULT_WEIGHTS)
        assert 0 <= score <= 100


class TestRiskLevel:
    def test_high(self) -> None:
        assert determine_risk_level(70) == "HIGH"
        assert determine_risk_level(85) == "HIGH"
        assert determine_risk_level(100) == "HIGH"

    def test_medium(self) -> None:
        assert determine_risk_level(55) == "MEDIUM"
        assert determine_risk_level(65) == "MEDIUM"
        assert determine_risk_level(69) == "MEDIUM"

    def test_low(self) -> None:
        assert determine_risk_level(0) == "LOW"
        assert determine_risk_level(30) == "LOW"
        assert determine_risk_level(54) == "LOW"
