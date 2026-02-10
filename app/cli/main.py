"""CLI entry point for the Supplier Risk Assessment system.

Author: Armand Amoussou

Usage:
    python -m app.cli.main run-daily [--date YYYY-MM-DD]
    python -m app.cli.main seed
    python -m app.cli.main export [--date YYYY-MM-DD]
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import click
import yaml

from app.configs.settings import get_settings
from app.observability.logger import setup_logging, get_logger


@click.group()
def cli() -> None:
    """Supplier Risk Assessment System - CLI."""
    setup_logging()


@cli.command("run-daily")
@click.option(
    "--date",
    "run_date",
    default=None,
    help="Assessment date (YYYY-MM-DD). Defaults to today.",
)
def cmd_run_daily(run_date: str | None) -> None:
    """Execute the daily risk assessment pipeline."""
    from app.pipelines.run_daily import run_daily

    settings = get_settings()

    if run_date:
        as_of_date = datetime.date.fromisoformat(run_date)
    else:
        as_of_date = datetime.date.today()

    click.echo(f"Starting daily pipeline for {as_of_date.isoformat()}...")
    result = run_daily(as_of_date=as_of_date, settings=settings)

    click.echo(f"Run ID: {result.get('run_id', 'N/A')}")
    click.echo(f"Status: {result.get('status', 'UNKNOWN')}")

    counts = result.get("counts", {})
    if counts:
        click.echo(f"Suppliers scored: {counts.get('suppliers_scored', 0)}/{counts.get('suppliers_total', 0)}")
        click.echo(f"Alerts sent: {counts.get('alerts_sent', 0)}")

    paths = result.get("output_paths", {})
    if paths:
        click.echo("Output files:")
        for key, path in paths.items():
            click.echo(f"  {key}: {path}")

    errors = result.get("errors", [])
    if errors:
        click.echo(f"Errors: {len(errors)}")
        for err in errors[:5]:
            click.echo(f"  - {err}")


@cli.command("seed")
def cmd_seed() -> None:
    """Load seed supplier data into the database."""
    from app.tools.db import get_db_backend, upsert_supplier

    settings = get_settings()
    logger = get_logger("cli")

    # Load suppliers from seed file
    seed_path = Path(settings.config_dir) / "suppliers_seed.yml"
    with open(seed_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    suppliers = data.get("suppliers", [])

    # Init DB
    db = get_db_backend(
        backend_type=settings.db_backend,
        postgres_dsn=settings.postgres_dsn,
        duckdb_path=settings.duckdb_path,
    )

    # Apply schema
    schema_path = str(Path(settings.config_dir) / "init_schema.sql")
    try:
        db.execute_schema(schema_path)
        click.echo("Schema initialized.")
    except Exception as e:
        click.echo(f"Schema warning: {e}")

    # Upsert suppliers
    count = 0
    for supplier in suppliers:
        try:
            upsert_supplier(db, supplier)
            count += 1
        except Exception as e:
            click.echo(f"Error seeding {supplier.get('supplier_id')}: {e}")

    db.close()
    click.echo(f"Seeded {count}/{len(suppliers)} suppliers.")


@cli.command("export")
@click.option(
    "--date",
    "export_date",
    default=None,
    help="Export date filter (YYYY-MM-DD). Defaults to all.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["csv", "json", "both"]),
    default="both",
    help="Export format.",
)
def cmd_export(export_date: str | None, fmt: str) -> None:
    """Export latest scores to CSV/JSON files."""
    from app.tools.db import get_db_backend, PostgresBackend, DuckDBBackend
    from app.tools.exporter import export_scores_csv, export_scores_json

    settings = get_settings()

    db = get_db_backend(
        backend_type=settings.db_backend,
        postgres_dsn=settings.postgres_dsn,
        duckdb_path=settings.duckdb_path,
    )

    # Query scores
    query = "SELECT as_of_date, supplier_id, c1_score, c2_score, c3_score, financial_score, global_score, risk_level FROM supplier_daily_scores"
    params: list = []

    if export_date:
        if isinstance(db, PostgresBackend):
            query += " WHERE as_of_date = %s"
        else:
            query += " WHERE as_of_date = ?"
        params.append(export_date)

    query += " ORDER BY as_of_date DESC, supplier_id"

    try:
        if isinstance(db, PostgresBackend):
            with db.cursor() as cur:
                cur.execute(query, tuple(params) if params else None)
                rows = cur.fetchall()
        else:
            with db.cursor() as conn:
                result = conn.execute(query, params if params else None)
                rows = result.fetchall()

        scores = [
            {
                "as_of_date": str(r[0]),
                "supplier_id": r[1],
                "c1_score": r[2],
                "c2_score": r[3],
                "c3_score": r[4],
                "financial_score": r[5],
                "global_score": r[6],
                "risk_level": r[7],
            }
            for r in rows
        ]

        if not scores:
            click.echo("No scores found.")
            db.close()
            return

        if fmt in ("csv", "both"):
            csv_path = export_scores_csv(scores, settings.output_dir)
            click.echo(f"CSV exported: {csv_path}")
        if fmt in ("json", "both"):
            json_path = export_scores_json(scores, settings.output_dir)
            click.echo(f"JSON exported: {json_path}")

    except Exception as e:
        click.echo(f"Export error: {e}")

    db.close()


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
