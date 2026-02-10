"""CrewAI agent definitions for the Supplier Risk Assessment system.

Author: Armand Amoussou

Agents:
- Collector: fetches data from official web sources
- Normalizer: parses and normalizes collected content
- FinancialScorer: uses LLM to produce financial risk scores
- InternalRulesScorer: applies deterministic scoring rules (C1, C2, C3)
- RiskAggregator: computes global weighted score
- Notifier: generates and dispatches alerts
- Auditor: logs run metadata and audit trail
"""

from __future__ import annotations

from crewai import Agent


def create_collector_agent() -> Agent:
    """Agent that collects data from official web sources."""
    return Agent(
        role="Data Collector",
        goal=(
            "Fetch relevant public information about suppliers from official "
            "web sources (registries, regulatory bodies, financial publications). "
            "Respect allowlist, robots.txt, and rate limits."
        ),
        backstory=(
            "You are a specialized data collection agent for supplier risk "
            "assessment. You only access pre-approved official sources and "
            "follow strict scraping policies."
        ),
        verbose=False,
        allow_delegation=False,
    )


def create_normalizer_agent() -> Agent:
    """Agent that parses and normalizes collected web content."""
    return Agent(
        role="Content Normalizer",
        goal=(
            "Parse raw HTML/text content from official sources into clean, "
            "structured text snippets suitable for financial risk analysis."
        ),
        backstory=(
            "You are a content processing specialist. You extract meaningful "
            "financial and corporate information from raw web content, removing "
            "noise and irrelevant elements."
        ),
        verbose=False,
        allow_delegation=False,
    )


def create_financial_scorer_agent() -> Agent:
    """Agent that uses LLM to produce financial risk scores."""
    return Agent(
        role="Financial Risk Scorer",
        goal=(
            "Analyze collected evidence about a supplier and produce a "
            "structured JSON financial risk score following strict anti-"
            "hallucination rules. Score must be evidence-based only."
        ),
        backstory=(
            "You are a financial risk analysis engine. You ONLY use provided "
            "evidence to assess risk. You NEVER invent sources or data. "
            "When evidence is insufficient, you report INDETERMINATE with "
            "specific data gaps."
        ),
        verbose=False,
        allow_delegation=False,
    )


def create_internal_rules_scorer_agent() -> Agent:
    """Agent that applies deterministic rules for C1, C2, C3 scores."""
    return Agent(
        role="Internal Rules Scorer",
        goal=(
            "Compute three internal risk criteria scores (C1: delivery "
            "performance, C2: dependency/criticality, C3: relationship history) "
            "using deterministic rules on internal supplier data."
        ),
        backstory=(
            "You are a deterministic scoring engine. You apply predefined "
            "rules and thresholds to internal supplier signals to produce "
            "reproducible, auditable risk scores."
        ),
        verbose=False,
        allow_delegation=False,
    )


def create_risk_aggregator_agent() -> Agent:
    """Agent that computes global weighted risk score."""
    return Agent(
        role="Risk Aggregator",
        goal=(
            "Combine C1, C2, C3 internal scores with the financial score "
            "using configured weights to produce a global risk score and "
            "risk level classification."
        ),
        backstory=(
            "You are the final scoring engine. You apply weighted aggregation "
            "to all four criteria and determine the overall risk level."
        ),
        verbose=False,
        allow_delegation=False,
    )


def create_notifier_agent() -> Agent:
    """Agent that generates and dispatches risk alerts."""
    return Agent(
        role="Alert Notifier",
        goal=(
            "Evaluate scoring results against alerting thresholds and generate "
            "alerts when risk escalation, significant score changes, or "
            "critical drivers are detected."
        ),
        backstory=(
            "You are the alerting engine. You monitor risk level transitions "
            "and score variations to notify the supply chain team of "
            "actionable risk changes."
        ),
        verbose=False,
        allow_delegation=False,
    )


def create_auditor_agent() -> Agent:
    """Agent that logs run metadata and maintains audit trail."""
    return Agent(
        role="Run Auditor",
        goal=(
            "Record complete audit trail for each pipeline run including "
            "timestamps, status, error counts, LLM cost estimates, and "
            "processing statistics."
        ),
        backstory=(
            "You are the compliance and audit engine. You ensure full "
            "traceability of every pipeline execution for governance purposes."
        ),
        verbose=False,
        allow_delegation=False,
    )
