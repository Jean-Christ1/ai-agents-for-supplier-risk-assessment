"""CrewAI crew assembly for the Supplier Risk Assessment pipeline.

Author: Armand Amoussou

This module builds and runs the CrewAI crew, but the actual pipeline logic
is handled in app.pipelines.steps to maintain determinism and testability.
The crew serves as the orchestration layer.
"""

from __future__ import annotations

from crewai import Crew, Process

from app.crew.agents import (
    create_auditor_agent,
    create_collector_agent,
    create_financial_scorer_agent,
    create_internal_rules_scorer_agent,
    create_normalizer_agent,
    create_notifier_agent,
    create_risk_aggregator_agent,
)
from app.crew.tasks import (
    create_aggregation_task,
    create_audit_task,
    create_collect_task,
    create_financial_scoring_task,
    create_internal_scoring_task,
    create_normalize_task,
    create_notification_task,
)
from app.observability.logger import get_logger

logger = get_logger("crew")


def build_crew(supplier_context: str = "") -> Crew:
    """Build the full supplier risk assessment crew.

    The crew uses sequential process to ensure proper data flow:
    1. Collect -> 2. Normalize -> 3. Score (internal + financial)
    4. Aggregate -> 5. Notify -> 6. Audit
    """
    # Create agents
    collector = create_collector_agent()
    normalizer = create_normalizer_agent()
    financial_scorer = create_financial_scorer_agent()
    internal_scorer = create_internal_rules_scorer_agent()
    aggregator = create_risk_aggregator_agent()
    notifier = create_notifier_agent()
    auditor = create_auditor_agent()

    # Create tasks
    collect_task = create_collect_task(collector, supplier_context)
    normalize_task = create_normalize_task(normalizer)
    financial_task = create_financial_scoring_task(financial_scorer)
    internal_task = create_internal_scoring_task(internal_scorer)
    aggregation_task = create_aggregation_task(aggregator)
    notification_task = create_notification_task(notifier)
    audit_task = create_audit_task(auditor)

    crew = Crew(
        agents=[
            collector,
            normalizer,
            financial_scorer,
            internal_scorer,
            aggregator,
            notifier,
            auditor,
        ],
        tasks=[
            collect_task,
            normalize_task,
            internal_task,
            financial_task,
            aggregation_task,
            notification_task,
            audit_task,
        ],
        process=Process.sequential,
        verbose=False,
    )

    logger.info("crew_built", agents=7, tasks=7)
    return crew
