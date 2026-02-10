"""Daily pipeline orchestrator: run_daily(date).

Author: Armand Amoussou

Sequence:
1. Load config + suppliers
2. Initialize DB + tools
3. For each supplier:
   a. Ingest internal signals
   b. Collect official web data
   c. Normalize content
   d. Financial scoring (LLM)
   e. Internal scoring (rules)
   f. Aggregate global score
   g. Check alerts
   h. Persist all results
4. Export results
5. Finalize audit
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from app.configs.settings import AppSettings, get_settings
from app.observability.audit import create_audit_start, finalize_audit, generate_run_id
from app.observability.logger import get_logger, setup_logging
from app.pipelines.steps import (
    step_aggregate_scores,
    step_check_alerts,
    step_collect_web_data,
    step_compute_internal_scores,
    step_financial_scoring,
    step_load_config,
    step_load_suppliers,
    step_normalize_documents,
)
from app.tools.db import (
    DuckDBBackend,
    PostgresBackend,
    get_db_backend,
    insert_daily_score,
    insert_financial_score,
    insert_internal_signals,
    insert_run_audit,
    get_previous_score,
    get_score_n_days_ago,
    upsert_supplier,
)
from app.tools.exporter import export_scores_csv, export_scores_json, export_financial_details
from app.tools.llm_client import LLMClient
from app.tools.notifier import send_alert
from app.tools.web_fetch import WebFetcher

logger = get_logger("run_daily")


def run_daily(
    as_of_date: datetime.date | None = None,
    settings: AppSettings | None = None,
) -> dict[str, Any]:
    """Execute the full daily risk assessment pipeline.

    Args:
        as_of_date: Assessment date (defaults to today).
        settings: Application settings (defaults to env-based).

    Returns:
        dict with run_id, status, counts, and output paths.
    """
    setup_logging()

    if settings is None:
        settings = get_settings()
    if as_of_date is None:
        as_of_date = datetime.date.today()

    run_id = generate_run_id()
    audit = create_audit_start(run_id)
    errors: list[dict[str, Any]] = []
    all_scores: list[dict[str, Any]] = []
    all_financial_details: list[dict[str, Any]] = []
    alerts_sent = 0

    logger.info("pipeline_start", run_id=run_id, as_of_date=as_of_date.isoformat())

    try:
        # 1. Load configuration
        config = step_load_config(settings.config_dir)
        suppliers = step_load_suppliers(settings.config_dir)

        # 2. Initialize database
        db = _init_db(settings)

        # 3. Initialize tools
        fetcher = _init_fetcher(settings)
        llm_client = _init_llm(settings)

        # 4. Seed suppliers into DB
        for supplier in suppliers:
            try:
                upsert_supplier(db, supplier)
            except Exception as e:
                logger.warning(
                    "supplier_upsert_error",
                    supplier_id=supplier.get("supplier_id"),
                    error=str(e),
                )

        # 5. Process each supplier
        for supplier in suppliers:
            supplier_id = supplier["supplier_id"]
            try:
                result = _process_supplier(
                    supplier=supplier,
                    as_of_date=as_of_date,
                    config=config,
                    db=db,
                    fetcher=fetcher,
                    llm_client=llm_client,
                    settings=settings,
                )
                all_scores.append(result["score"])
                all_financial_details.append(result["financial_detail"])
                if result.get("alert_sent"):
                    alerts_sent += 1

            except Exception as e:
                logger.error(
                    "supplier_processing_error",
                    supplier_id=supplier_id,
                    error=str(e),
                )
                errors.append({"supplier_id": supplier_id, "error": str(e)})

        # 6. Export results
        output_paths = _export_results(all_scores, all_financial_details, settings)

        # 7. Finalize audit
        status = "SUCCESS" if not errors else ("PARTIAL" if all_scores else "FAILED")
        counts = {
            "suppliers_total": len(suppliers),
            "suppliers_scored": len(all_scores),
            "suppliers_failed": len(errors),
            "alerts_sent": alerts_sent,
        }
        audit = finalize_audit(
            audit,
            status=status,
            errors=errors if errors else None,
            counts=counts,
            llm_cost=llm_client.estimate_cost() if llm_client else 0.0,
        )

        # Persist audit
        try:
            insert_run_audit(db, audit.model_dump())
        except Exception as e:
            logger.warning("audit_persist_error", error=str(e))

        db.close()

        result = {
            "run_id": run_id,
            "status": status,
            "as_of_date": as_of_date.isoformat(),
            "counts": counts,
            "output_paths": output_paths,
            "errors": errors,
        }
        logger.info("pipeline_complete", **result)
        return result

    except Exception as e:
        logger.error("pipeline_fatal_error", run_id=run_id, error=str(e))
        audit = finalize_audit(
            audit,
            status="FAILED",
            errors=[{"fatal": str(e)}],
        )
        return {
            "run_id": run_id,
            "status": "FAILED",
            "error": str(e),
        }


def _process_supplier(
    supplier: dict[str, Any],
    as_of_date: datetime.date,
    config: dict[str, Any],
    db: PostgresBackend | DuckDBBackend,
    fetcher: WebFetcher | None,
    llm_client: LLMClient | None,
    settings: AppSettings,
) -> dict[str, Any]:
    """Process a single supplier through the full scoring pipeline."""
    supplier_id = supplier["supplier_id"]

    # a. Compute internal scores
    internal_scores = step_compute_internal_scores(supplier, config["thresholds"])

    # b. Persist internal signals
    signals = supplier.get("internal_signals", {})
    try:
        insert_internal_signals(
            db,
            as_of_date,
            supplier_id,
            internal_scores["c1_score"],
            internal_scores["c2_score"],
            internal_scores["c3_score"],
            signals,
        )
    except Exception as e:
        logger.warning("internal_signals_persist_error", supplier_id=supplier_id, error=str(e))

    # c. Collect web data
    documents = step_collect_web_data(
        supplier,
        fetcher,
        golden_mode=settings.golden_mode,
        golden_dir=settings.golden_dir,
    )

    # d. Normalize
    normalized = step_normalize_documents(supplier_id, documents)

    # e. Financial scoring
    financial_output = step_financial_scoring(
        supplier, normalized, as_of_date, llm_client
    )

    # f. Persist financial score
    try:
        insert_financial_score(
            db,
            as_of_date,
            supplier_id,
            financial_output.financial_risk_score,
            financial_output.financial_risk_level.value,
            financial_output.confidence,
            financial_output.model_dump(mode="json"),
        )
    except Exception as e:
        logger.warning("financial_score_persist_error", supplier_id=supplier_id, error=str(e))

    # g. Aggregate
    aggregated = step_aggregate_scores(
        supplier_id,
        as_of_date,
        internal_scores,
        financial_output,
        config["weights"],
        config["risk_levels"],
    )

    # h. Persist daily score
    try:
        insert_daily_score(db, aggregated)
    except Exception as e:
        logger.warning("daily_score_persist_error", supplier_id=supplier_id, error=str(e))

    # i. Check alerts
    alert_sent = False
    try:
        previous = get_previous_score(db, supplier_id, as_of_date)
        score_7d = get_score_n_days_ago(db, supplier_id, as_of_date, 7)
        alert = step_check_alerts(
            supplier,
            aggregated,
            financial_output,
            previous,
            score_7d,
            config["alerting"],
        )
        if alert is not None:
            alert_sent = send_alert(
                alert,
                mode=settings.alert_mode,
                output_dir=str(Path(settings.output_dir) / "alerts"),
                smtp_host=settings.smtp_host,
                smtp_port=settings.smtp_port,
            )
    except Exception as e:
        logger.warning("alert_check_error", supplier_id=supplier_id, error=str(e))

    return {
        "score": aggregated,
        "financial_detail": financial_output.model_dump(mode="json"),
        "alert_sent": alert_sent,
    }


def _init_db(settings: AppSettings) -> PostgresBackend | DuckDBBackend:
    """Initialize database backend."""
    db = get_db_backend(
        backend_type=settings.db_backend,
        postgres_dsn=settings.postgres_dsn,
        duckdb_path=settings.duckdb_path,
    )
    # Ensure schema exists
    schema_path = str(Path(settings.config_dir) / "init_schema.sql")
    try:
        db.execute_schema(schema_path)
    except Exception as e:
        logger.warning("schema_init_warning", error=str(e))
    return db


def _init_fetcher(settings: AppSettings) -> WebFetcher | None:
    """Initialize web fetcher if not in golden mode."""
    if settings.golden_mode:
        return None
    try:
        return WebFetcher(
            config_dir=settings.config_dir,
            cache_dir=settings.cache_dir,
        )
    except Exception as e:
        logger.warning("fetcher_init_error", error=str(e))
        return None


def _init_llm(settings: AppSettings) -> LLMClient | None:
    """Initialize LLM client."""
    if settings.golden_mode:
        return None
    try:
        return LLMClient(
            provider=settings.llm_provider,
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
            ollama_url=settings.ollama_base_url,
            ollama_model=settings.ollama_model,
        )
    except Exception as e:
        logger.warning("llm_init_error", error=str(e))
        return None


def _export_results(
    scores: list[dict[str, Any]],
    financial_details: list[dict[str, Any]],
    settings: AppSettings,
) -> dict[str, str]:
    """Export results to CSV and JSON files."""
    paths = {}
    try:
        paths["csv"] = export_scores_csv(scores, settings.output_dir)
        paths["json"] = export_scores_json(scores, settings.output_dir)
        paths["financial"] = export_financial_details(
            financial_details, settings.output_dir
        )
    except Exception as e:
        logger.warning("export_error", error=str(e))
    return paths
