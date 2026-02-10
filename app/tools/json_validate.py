"""JSON schema validation for LLM outputs using Pydantic v2.

Author: Armand Amoussou
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.observability.logger import get_logger
from app.schemas.financial_output import FinancialRiskOutput, RiskLevel

logger = get_logger("json_validate")


def validate_financial_output(
    data: dict[str, Any],
) -> tuple[FinancialRiskOutput | None, list[str]]:
    """Validate a dict against the FinancialRiskOutput schema.

    Returns: (validated_output or None, list of error messages)
    """
    errors: list[str] = []
    try:
        output = FinancialRiskOutput.model_validate(data)
        # Apply anti-hallucination enforcement
        output = output.enforce_anti_hallucination()
        logger.info(
            "validation_ok",
            supplier_id=output.supplier_id,
            level=output.financial_risk_level.value,
        )
        return output, []
    except ValidationError as e:
        for err in e.errors():
            field = ".".join(str(loc) for loc in err["loc"])
            errors.append(f"{field}: {err['msg']}")
        logger.warning("validation_failed", errors=errors, data_keys=list(data.keys()))
        return None, errors


def build_indeterminate_output(
    supplier_id: str,
    as_of_date: str,
    reason: str,
) -> FinancialRiskOutput:
    """Build a safe INDETERMINATE output when validation fails or no data."""
    import datetime

    return FinancialRiskOutput(
        supplier_id=supplier_id,
        as_of_date=datetime.date.fromisoformat(as_of_date),
        financial_risk_score=50,
        financial_risk_level=RiskLevel.INDETERMINATE,
        confidence=0.2,
        risk_drivers=[],
        recommended_actions=["Manual review required due to insufficient data"],
        data_gaps=[reason],
        evidence_items=[],
        notes=f"Automatic INDETERMINATE: {reason[:350]}",
    )
