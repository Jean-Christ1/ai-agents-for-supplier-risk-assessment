"""Pipeline step functions: deterministic, testable building blocks.

Author: Armand Amoussou

Each step is a pure or near-pure function that can be tested independently.
The pipeline orchestrator (run_daily) calls these in sequence.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import yaml

from app.observability.logger import get_logger
from app.schemas.financial_output import (
    AlertPayload,
    EvidenceItem,
    FinancialRiskOutput,
    RiskLevel,
)
from app.tools.cache import content_hash
from app.tools.json_validate import build_indeterminate_output, validate_financial_output
from app.tools.llm_client import (
    FINANCIAL_SCORER_DEVELOPER_PROMPT,
    FINANCIAL_SCORER_SYSTEM_PROMPT,
    FINANCIAL_SCORER_USER_TEMPLATE,
    LLMClient,
)
from app.tools.scoring_rules import (
    compute_c1_score,
    compute_c2_score,
    compute_c3_score,
    compute_global_score,
    determine_risk_level,
)
from app.tools.web_fetch import WebFetcher
from app.tools.web_parse import extract_snippets, load_golden_content, parse_html_to_text

logger = get_logger("steps")


def step_load_suppliers(config_dir: str) -> list[dict[str, Any]]:
    """Load supplier seed data from YAML config."""
    seed_path = Path(config_dir) / "suppliers_seed.yml"
    with open(seed_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    suppliers = data.get("suppliers", [])
    logger.info("suppliers_loaded", count=len(suppliers))
    return suppliers


def step_load_config(config_dir: str) -> dict[str, Any]:
    """Load weights and thresholds configuration."""
    weights_path = Path(config_dir) / "weights.yml"
    thresholds_path = Path(config_dir) / "thresholds.yml"

    with open(weights_path, encoding="utf-8") as f:
        weights_data = yaml.safe_load(f)
    with open(thresholds_path, encoding="utf-8") as f:
        thresholds_data = yaml.safe_load(f)

    return {
        "weights": weights_data.get("weights", {}),
        "thresholds": thresholds_data,
        "risk_levels": thresholds_data.get("risk_levels", {}),
        "alerting": thresholds_data.get("alerting", {}),
        "internal": thresholds_data.get("internal", {}),
    }


def step_compute_internal_scores(
    supplier: dict[str, Any],
    thresholds: dict[str, Any],
) -> dict[str, int]:
    """Compute C1, C2, C3 scores for a supplier using deterministic rules."""
    signals = supplier.get("internal_signals", {})
    internal_t = thresholds.get("internal", {})

    c1 = compute_c1_score(signals, internal_t)
    c2 = compute_c2_score(signals, internal_t)
    c3 = compute_c3_score(signals, internal_t)

    logger.info(
        "internal_scores_computed",
        supplier_id=supplier["supplier_id"],
        c1=c1,
        c2=c2,
        c3=c3,
    )
    return {"c1_score": c1, "c2_score": c2, "c3_score": c3}


def step_collect_web_data(
    supplier: dict[str, Any],
    fetcher: WebFetcher | None,
    golden_mode: bool = False,
    golden_dir: str = "",
) -> list[dict[str, Any]]:
    """Collect web data for a supplier (or load golden test data)."""
    supplier_id = supplier["supplier_id"]

    if golden_mode:
        return _load_golden_data(supplier_id, golden_dir)

    if fetcher is None:
        logger.warning("no_fetcher_available", supplier_id=supplier_id)
        return []

    # Build search URLs based on supplier info (simplified for MVP)
    # In production, this would use supplier-specific URLs from config
    collected = []
    country = supplier.get("country", "")
    name = supplier.get("name", "")

    # For MVP, we log that collection would happen but return empty
    # as actual URLs depend on the specific supplier's web presence
    logger.info(
        "web_collection_attempted",
        supplier_id=supplier_id,
        name=name,
        country=country,
    )
    return collected


def _load_golden_data(supplier_id: str, golden_dir: str) -> list[dict[str, Any]]:
    """Load golden test data for a supplier."""
    cases_dir = Path(golden_dir) / "cases"
    if not cases_dir.exists():
        return []

    collected = []
    for f in sorted(cases_dir.glob(f"{supplier_id}*.txt")):
        content = load_golden_content(str(f))
        if content:
            c_hash = content_hash(content)
            collected.append(
                {
                    "url": f"file://{f}",
                    "domain": "localhost",
                    "content": content,
                    "content_hash": c_hash,
                    "http_status": 200,
                    "doc_id": f.stem,
                }
            )
    logger.info(
        "golden_data_loaded",
        supplier_id=supplier_id,
        docs_count=len(collected),
    )
    return collected


def step_normalize_documents(
    supplier_id: str,
    documents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Parse and normalize collected documents into snippets."""
    normalized = []
    for doc in documents:
        content = doc.get("content", "")
        # Try HTML parsing first, fall back to raw text
        parsed = parse_html_to_text(content, url=doc.get("url", ""))
        if parsed is None:
            parsed = content

        snippets = extract_snippets(parsed)
        if snippets:
            normalized.append(
                {
                    "doc_id": doc.get("doc_id", "unknown"),
                    "url": doc.get("url", ""),
                    "content_hash": doc.get("content_hash", ""),
                    "snippets": snippets,
                }
            )

    logger.info(
        "documents_normalized",
        supplier_id=supplier_id,
        input_docs=len(documents),
        output_docs=len(normalized),
    )
    return normalized


def step_financial_scoring(
    supplier: dict[str, Any],
    normalized_docs: list[dict[str, Any]],
    as_of_date: datetime.date,
    llm_client: LLMClient | None,
    max_retries: int = 2,
) -> FinancialRiskOutput:
    """Run LLM-based financial risk scoring with validation and retry."""
    supplier_id = supplier["supplier_id"]

    # Build evidence text from normalized docs
    evidence_parts = []
    for doc in normalized_docs:
        for snippet in doc.get("snippets", []):
            evidence_parts.append(
                f"[Source: {doc['url']}] {snippet}"
            )
    evidence_text = "\n".join(evidence_parts) if evidence_parts else "No evidence collected."

    # If no LLM client or no evidence, return INDETERMINATE
    if llm_client is None:
        logger.warning("no_llm_client", supplier_id=supplier_id)
        return build_indeterminate_output(
            supplier_id, as_of_date.isoformat(), "LLM client not available"
        )

    if not evidence_parts:
        logger.info("no_evidence_for_scoring", supplier_id=supplier_id)
        return build_indeterminate_output(
            supplier_id, as_of_date.isoformat(), "No evidence collected from official sources"
        )

    # Build user prompt
    user_prompt = FINANCIAL_SCORER_USER_TEMPLATE.format(
        supplier_id=supplier_id,
        supplier_name=supplier.get("name", "Unknown"),
        country=supplier.get("country", "Unknown"),
        category=supplier.get("category", "Unknown"),
        as_of_date=as_of_date.isoformat(),
        evidence_text=evidence_text,
    )

    # Call LLM with retry
    for attempt in range(max_retries + 1):
        result = llm_client.call(
            system_prompt=FINANCIAL_SCORER_SYSTEM_PROMPT,
            developer_prompt=FINANCIAL_SCORER_DEVELOPER_PROMPT,
            user_prompt=user_prompt,
        )

        if result["parsed_json"] is not None:
            validated, errors = validate_financial_output(result["parsed_json"])
            if validated is not None:
                logger.info(
                    "financial_scoring_ok",
                    supplier_id=supplier_id,
                    score=validated.financial_risk_score,
                    level=validated.financial_risk_level.value,
                    attempt=attempt + 1,
                )
                return validated
            else:
                logger.warning(
                    "financial_validation_failed",
                    supplier_id=supplier_id,
                    errors=errors,
                    attempt=attempt + 1,
                )
        else:
            logger.warning(
                "financial_llm_no_json",
                supplier_id=supplier_id,
                attempt=attempt + 1,
            )

    # All retries exhausted
    return build_indeterminate_output(
        supplier_id,
        as_of_date.isoformat(),
        f"LLM validation failed after {max_retries + 1} attempts",
    )


def step_aggregate_scores(
    supplier_id: str,
    as_of_date: datetime.date,
    internal_scores: dict[str, int],
    financial_output: FinancialRiskOutput,
    weights: dict[str, float],
    risk_level_thresholds: dict[str, Any],
) -> dict[str, Any]:
    """Compute global score and risk level."""
    c1 = internal_scores["c1_score"]
    c2 = internal_scores["c2_score"]
    c3 = internal_scores["c3_score"]

    # Financial score: use None if INDETERMINATE
    financial_score: int | None = None
    if financial_output.financial_risk_level != RiskLevel.INDETERMINATE:
        financial_score = financial_output.financial_risk_score

    global_score = compute_global_score(c1, c2, c3, financial_score, weights)
    risk_level = determine_risk_level(global_score, risk_level_thresholds)

    result = {
        "as_of_date": as_of_date,
        "supplier_id": supplier_id,
        "c1_score": c1,
        "c2_score": c2,
        "c3_score": c3,
        "financial_score": financial_score,
        "global_score": global_score,
        "risk_level": risk_level,
    }
    logger.info(
        "scores_aggregated",
        supplier_id=supplier_id,
        global_score=global_score,
        risk_level=risk_level,
    )
    return result


def step_check_alerts(
    supplier: dict[str, Any],
    current_score: dict[str, Any],
    financial_output: FinancialRiskOutput,
    previous_score: dict[str, Any] | None,
    score_7d_ago: int | None,
    alerting_config: dict[str, Any],
) -> AlertPayload | None:
    """Evaluate alerting conditions and build alert payload if triggered."""
    supplier_id = supplier["supplier_id"]
    current_level = current_score["risk_level"]
    global_score = current_score["global_score"]

    # Condition 1: Risk level escalation MEDIUM -> HIGH
    if previous_score is not None:
        prev_level = previous_score.get("risk_level", "LOW")
        if prev_level == "MEDIUM" and current_level == "HIGH":
            return _build_alert(
                supplier,
                current_score,
                financial_output,
                prev_level,
                "Risk level escalation from MEDIUM to HIGH",
            )

    # Condition 2: Score delta >= threshold over N days
    delta_threshold = alerting_config.get("score_delta_threshold", 15)
    if score_7d_ago is not None:
        delta = global_score - score_7d_ago
        if delta >= delta_threshold:
            return _build_alert(
                supplier,
                current_score,
                financial_output,
                previous_score.get("risk_level") if previous_score else None,
                f"Score increased by {delta} points over 7 days",
            )

    # Condition 3: Critical financial drivers
    critical_drivers = set(alerting_config.get("critical_drivers", []))
    if critical_drivers:
        found_critical = [
            d for d in financial_output.risk_drivers if d in critical_drivers
        ]
        if found_critical:
            return _build_alert(
                supplier,
                current_score,
                financial_output,
                previous_score.get("risk_level") if previous_score else None,
                f"Critical drivers detected: {', '.join(found_critical)}",
            )

    return None


def _build_alert(
    supplier: dict[str, Any],
    current_score: dict[str, Any],
    financial_output: FinancialRiskOutput,
    previous_level: str | None,
    trigger_reason: str,
) -> AlertPayload:
    """Build an AlertPayload from current data."""
    return AlertPayload(
        supplier_id=supplier["supplier_id"],
        supplier_name=supplier.get("name", "Unknown"),
        as_of_date=current_score["as_of_date"],
        global_score=current_score["global_score"],
        financial_score=current_score.get("financial_score"),
        previous_risk_level=previous_level,
        current_risk_level=current_score["risk_level"],
        risk_drivers=financial_output.risk_drivers,
        top_evidences=financial_output.evidence_items[:3],
        recommended_actions=financial_output.recommended_actions,
        trigger_reason=trigger_reason,
    )
