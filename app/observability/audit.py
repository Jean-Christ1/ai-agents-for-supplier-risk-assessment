"""Run audit tracking for pipeline executions.

Author: Armand Amoussou
"""

from __future__ import annotations

import datetime
import uuid

from app.observability.logger import get_logger
from app.schemas.financial_output import RunAuditRecord

logger = get_logger("audit")


def generate_run_id() -> str:
    """Generate a unique run ID."""
    ts = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"run_{ts}_{short_uuid}"


def create_audit_start(run_id: str) -> RunAuditRecord:
    """Create an audit record at pipeline start."""
    record = RunAuditRecord(
        run_id=run_id,
        started_at=datetime.datetime.now(tz=datetime.timezone.utc),
        status="RUNNING",
    )
    logger.info(
        "pipeline_started",
        run_id=run_id,
        started_at=record.started_at.isoformat(),
    )
    return record


def finalize_audit(
    record: RunAuditRecord,
    status: str,
    errors: list[dict] | None = None,  # type: ignore[type-arg]
    counts: dict | None = None,  # type: ignore[type-arg]
    llm_cost: float = 0.0,
) -> RunAuditRecord:
    """Finalize the audit record at pipeline end."""
    updated = record.model_copy(
        update={
            "finished_at": datetime.datetime.now(tz=datetime.timezone.utc),
            "status": status,
            "errors": errors,
            "counts": counts,
            "llm_cost_estimate": llm_cost,
        }
    )
    logger.info(
        "pipeline_finished",
        run_id=updated.run_id,
        status=status,
        duration_seconds=(
            (updated.finished_at - updated.started_at).total_seconds()
            if updated.finished_at
            else None
        ),
        counts=counts,
        errors_count=len(errors) if errors else 0,
    )
    return updated
