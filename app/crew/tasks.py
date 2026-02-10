"""CrewAI task definitions for the Supplier Risk Assessment pipeline.

Author: Armand Amoussou
"""

from __future__ import annotations

from crewai import Agent, Task


def create_collect_task(agent: Agent, supplier_context: str) -> Task:
    """Task: Collect official web data for a supplier."""
    return Task(
        description=(
            f"Collect official public information for the following supplier:\n"
            f"{supplier_context}\n\n"
            f"Use the web fetcher tool to retrieve content from allowlisted "
            f"official sources. Return a structured dict with collected documents."
        ),
        expected_output=(
            "A dict containing: supplier_id, documents list (each with url, "
            "domain, content, content_hash, http_status)."
        ),
        agent=agent,
    )


def create_normalize_task(agent: Agent) -> Task:
    """Task: Parse and normalize collected web content."""
    return Task(
        description=(
            "Parse the collected raw web content into clean text snippets. "
            "Extract meaningful financial and corporate information. "
            "Remove HTML noise, navigation elements, and irrelevant content. "
            "Return structured snippets suitable for financial analysis."
        ),
        expected_output=(
            "A dict containing: supplier_id, normalized_snippets list "
            "(each with source_url, doc_id, content_hash, snippets list)."
        ),
        agent=agent,
    )


def create_financial_scoring_task(agent: Agent) -> Task:
    """Task: Produce financial risk score using LLM analysis."""
    return Task(
        description=(
            "Analyze the normalized evidence snippets and produce a financial "
            "risk score following the strict JSON schema. Apply anti-hallucination "
            "rules: every claim must have evidence, use INDETERMINATE when data "
            "is insufficient. Score range [0,100], confidence [0,1]."
        ),
        expected_output=(
            "A valid FinancialRiskOutput JSON object with supplier_id, "
            "financial_risk_score, financial_risk_level, confidence, "
            "risk_drivers, evidence_items, and data_gaps."
        ),
        agent=agent,
    )


def create_internal_scoring_task(agent: Agent) -> Task:
    """Task: Compute C1, C2, C3 deterministic scores."""
    return Task(
        description=(
            "Compute the three internal risk scores using deterministic rules:\n"
            "- C1: Delivery performance (delays, quality incidents)\n"
            "- C2: Dependency / criticality (monosource, component criticality)\n"
            "- C3: Relationship history (contract maturity, litigation)\n"
            "Apply configured thresholds and weights."
        ),
        expected_output=(
            "A dict with supplier_id, c1_score, c2_score, c3_score, "
            "each in [0,100]."
        ),
        agent=agent,
    )


def create_aggregation_task(agent: Agent) -> Task:
    """Task: Compute global weighted risk score."""
    return Task(
        description=(
            "Combine all four scores (C1, C2, C3, Financial) using configured "
            "weights to produce the global_score. Determine risk_level based "
            "on thresholds (HIGH >= 70, MEDIUM >= 55, LOW < 55). "
            "Handle INDETERMINATE financial scores by redistributing weight."
        ),
        expected_output=(
            "A SupplierDailyScore with all scores, global_score, and risk_level."
        ),
        agent=agent,
    )


def create_notification_task(agent: Agent) -> Task:
    """Task: Evaluate and send alerts if thresholds are exceeded."""
    return Task(
        description=(
            "Check alerting conditions:\n"
            "1. Risk level escalation (MEDIUM -> HIGH)\n"
            "2. Score delta >= +15 over 7 days\n"
            "3. Critical financial drivers detected\n"
            "If triggered, generate and dispatch alert with supplier details, "
            "scores, drivers, top 3 evidences, and recommended actions."
        ),
        expected_output=(
            "Alert sent status: True/False, with alert details if triggered."
        ),
        agent=agent,
    )


def create_audit_task(agent: Agent) -> Task:
    """Task: Record pipeline run audit trail."""
    return Task(
        description=(
            "Record the complete audit trail for this pipeline run:\n"
            "- Run ID, start/end timestamps\n"
            "- Final status (SUCCESS/FAILED/PARTIAL)\n"
            "- Error details if any\n"
            "- Processing counts (suppliers, scores, alerts)\n"
            "- Estimated LLM costs\n"
            "Persist to run_audit table."
        ),
        expected_output="RunAuditRecord with complete run metadata.",
        agent=agent,
    )
