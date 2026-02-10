"""Deterministic internal scoring rules (C1, C2, C3) and global aggregation.

Author: Armand Amoussou

Three internal criteria scored 0-100:
- C1: Delivery performance (delays, quality incidents)
- C2: Dependency / criticality (monosource, component criticality)
- C3: Relationship history (contract maturity, litigation)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.observability.logger import get_logger

logger = get_logger("scoring_rules")


def _load_yaml(path: str) -> dict:  # type: ignore[type-arg]
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)  # type: ignore[no-any-return]


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> int:
    return int(max(lo, min(hi, round(value))))


def _linear_scale(
    value: float, low_threshold: float, high_threshold: float
) -> float:
    """Scale value linearly between 0 and 100 based on thresholds.

    Values <= low_threshold -> 0 (low risk)
    Values >= high_threshold -> 100 (high risk)
    """
    if value <= low_threshold:
        return 0.0
    if value >= high_threshold:
        return 100.0
    return ((value - low_threshold) / (high_threshold - low_threshold)) * 100.0


def compute_c1_score(signals: dict[str, Any], thresholds: dict[str, Any]) -> int:
    """C1: Delivery Performance score (0-100).

    Higher score = higher risk.
    """
    t = thresholds.get("c1", {})
    delay_low = t.get("delay_low", 2)
    delay_high = t.get("delay_high", 8)
    severity_low = t.get("severity_low", 2.0)
    severity_high = t.get("severity_high", 7.0)
    quality_low = t.get("quality_low", 1)
    quality_high = t.get("quality_high", 5)

    delay_freq = signals.get("delivery_delays_last_12m", 0)
    avg_delay = signals.get("avg_delay_days", 0.0)
    quality_inc = signals.get("quality_incidents_last_12m", 0)

    freq_score = _linear_scale(delay_freq, delay_low, delay_high)
    sev_score = _linear_scale(avg_delay, severity_low, severity_high)
    qual_score = _linear_scale(quality_inc, quality_low, quality_high)

    # Weighted average using sub-weights (default 40/30/30)
    c1 = freq_score * 0.40 + sev_score * 0.30 + qual_score * 0.30
    return _clamp(c1)


def compute_c2_score(signals: dict[str, Any], thresholds: dict[str, Any]) -> int:
    """C2: Dependency / Criticality score (0-100).

    Higher score = higher risk.
    """
    t = thresholds.get("c2", {})
    mono_penalty = t.get("monosource_penalty", 50)
    crit_scores = t.get("criticality_scores", {})

    is_mono = signals.get("is_monosource", False)
    criticality = signals.get("criticality", "LOW")

    crit_val = crit_scores.get(criticality, 10)
    mono_val = mono_penalty if is_mono else 0

    # Combined: average of criticality and monosource components
    c2 = (crit_val + mono_val) / 2.0
    return _clamp(c2)


def compute_c3_score(signals: dict[str, Any], thresholds: dict[str, Any]) -> int:
    """C3: Relationship History score (0-100).

    Higher score = higher risk.
    """
    t = thresholds.get("c3", {})
    mat_low = t.get("maturity_low_years", 3)
    mat_high = t.get("maturity_high_years", 10)
    lit_scores = t.get("litigation_scores", {})

    contract_years = signals.get("contract_years", 0)
    litigation_count = signals.get("litigation_count", 0)

    # Contract maturity: longer = lower risk (invert the scale)
    if contract_years >= mat_high:
        maturity_risk = 0.0
    elif contract_years <= mat_low:
        maturity_risk = 100.0
    else:
        maturity_risk = (
            (mat_high - contract_years) / (mat_high - mat_low)
        ) * 100.0

    # Litigation: lookup or cap at highest
    lit_key = min(litigation_count, max(int(k) for k in lit_scores.keys()) if lit_scores else 3)
    lit_risk = lit_scores.get(str(lit_key), lit_scores.get(lit_key, 75))

    # Weighted: 40% maturity, 60% litigation
    c3 = maturity_risk * 0.40 + lit_risk * 0.60
    return _clamp(c3)


def compute_global_score(
    c1: int,
    c2: int,
    c3: int,
    financial: int | None,
    weights: dict[str, float] | None = None,
) -> int:
    """Compute weighted global risk score.

    If financial score is None (INDETERMINATE), redistribute its weight
    proportionally to the 3 internal criteria.
    """
    if weights is None:
        weights = {
            "c1_delivery_performance": 0.20,
            "c2_dependency_criticality": 0.15,
            "c3_relationship_history": 0.15,
            "c4_financial_risk": 0.50,
        }

    w1 = weights["c1_delivery_performance"]
    w2 = weights["c2_dependency_criticality"]
    w3 = weights["c3_relationship_history"]
    w4 = weights["c4_financial_risk"]

    if financial is not None:
        total = c1 * w1 + c2 * w2 + c3 * w3 + financial * w4
    else:
        # Redistribute financial weight proportionally
        internal_total = w1 + w2 + w3
        if internal_total > 0:
            total = c1 * (w1 / internal_total) + c2 * (w2 / internal_total) + c3 * (w3 / internal_total)
            total *= (w1 + w2 + w3 + w4)  # Normalize to full scale
        else:
            total = 50.0  # Fallback

    return _clamp(total)


def determine_risk_level(global_score: int, thresholds: dict[str, Any] | None = None) -> str:
    """Map global score to risk level string."""
    if thresholds is None:
        thresholds = {"high": 70, "medium": 55}
    high_t = thresholds.get("high", 70)
    medium_t = thresholds.get("medium", 55)

    if global_score >= high_t:
        return "HIGH"
    if global_score >= medium_t:
        return "MEDIUM"
    return "LOW"


def load_weights(config_dir: str) -> dict[str, float]:
    """Load scoring weights from YAML config."""
    data = _load_yaml(str(Path(config_dir) / "weights.yml"))
    return data.get("weights", {})  # type: ignore[no-any-return]


def load_thresholds(config_dir: str) -> dict[str, Any]:
    """Load thresholds from YAML config."""
    data = _load_yaml(str(Path(config_dir) / "thresholds.yml"))
    return data  # type: ignore[no-any-return]
