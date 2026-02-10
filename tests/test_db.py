"""Database layer tests using DuckDB in-memory for isolation.

Author: Armand Amoussou
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from app.tools.db import (
    DuckDBBackend,
    get_all_suppliers,
    get_previous_score,
    insert_daily_score,
    insert_financial_score,
    insert_internal_signals,
    upsert_supplier,
)


@pytest.fixture()
def db(tmp_path: Path) -> DuckDBBackend:
    """Create a fresh DuckDB database for each test."""
    db_path = str(tmp_path / "test.duckdb")
    backend = DuckDBBackend(db_path)
    backend.connect()
    schema_path = str(
        Path(__file__).resolve().parent.parent / "app" / "configs" / "init_schema.sql"
    )
    backend.execute_schema(schema_path)
    return backend


class TestSupplierCRUD:
    def test_upsert_and_retrieve(self, db: DuckDBBackend) -> None:
        supplier = {
            "supplier_id": "SUP-TEST",
            "name": "Test Corp",
            "country": "FR",
            "tier": 1,
            "category": "steel_components",
        }
        upsert_supplier(db, supplier)
        suppliers = get_all_suppliers(db)
        assert len(suppliers) == 1
        assert suppliers[0]["supplier_id"] == "SUP-TEST"
        assert suppliers[0]["name"] == "Test Corp"

    def test_upsert_update(self, db: DuckDBBackend) -> None:
        supplier = {
            "supplier_id": "SUP-TEST",
            "name": "Test Corp",
            "country": "FR",
            "tier": 1,
            "category": "steel_components",
        }
        upsert_supplier(db, supplier)
        supplier["name"] = "Test Corp Updated"
        upsert_supplier(db, supplier)
        suppliers = get_all_suppliers(db)
        assert len(suppliers) == 1
        assert suppliers[0]["name"] == "Test Corp Updated"


class TestInternalSignals:
    def test_insert_signals(self, db: DuckDBBackend) -> None:
        upsert_supplier(db, {
            "supplier_id": "SUP-001",
            "name": "Test",
            "country": "FR",
            "tier": 1,
            "category": "steel",
        })
        insert_internal_signals(
            db,
            datetime.date(2026, 1, 15),
            "SUP-001",
            30.0,
            45.0,
            20.0,
            {"delays": 3},
        )
        # Verify by querying
        with db.cursor() as conn:
            result = conn.execute(
                "SELECT c1_raw, c2_raw, c3_raw FROM internal_signals_daily WHERE supplier_id = ?",
                ["SUP-001"],
            )
            row = result.fetchone()
        assert row is not None
        assert float(row[0]) == 30.0


class TestDailyScores:
    def test_insert_and_query(self, db: DuckDBBackend) -> None:
        upsert_supplier(db, {
            "supplier_id": "SUP-001",
            "name": "Test",
            "country": "FR",
            "tier": 1,
            "category": "steel",
        })
        score = {
            "as_of_date": datetime.date(2026, 1, 15),
            "supplier_id": "SUP-001",
            "c1_score": 30,
            "c2_score": 45,
            "c3_score": 20,
            "financial_score": 65,
            "global_score": 55,
            "risk_level": "MEDIUM",
        }
        insert_daily_score(db, score)

        prev = get_previous_score(db, "SUP-001", datetime.date(2026, 1, 16))
        assert prev is not None
        assert prev["global_score"] == 55
        assert prev["risk_level"] == "MEDIUM"

    def test_no_previous_score(self, db: DuckDBBackend) -> None:
        upsert_supplier(db, {
            "supplier_id": "SUP-001",
            "name": "Test",
            "country": "FR",
            "tier": 1,
            "category": "steel",
        })
        prev = get_previous_score(db, "SUP-001", datetime.date(2026, 1, 15))
        assert prev is None


class TestFinancialScores:
    def test_insert_financial(self, db: DuckDBBackend) -> None:
        upsert_supplier(db, {
            "supplier_id": "SUP-001",
            "name": "Test",
            "country": "FR",
            "tier": 1,
            "category": "steel",
        })
        insert_financial_score(
            db,
            datetime.date(2026, 1, 15),
            "SUP-001",
            72,
            "HIGH",
            0.8,
            {"risk_drivers": ["DEBT_STRESS"]},
        )
        with db.cursor() as conn:
            result = conn.execute(
                "SELECT score, level FROM financial_scores_daily WHERE supplier_id = ?",
                ["SUP-001"],
            )
            row = result.fetchone()
        assert row is not None
        assert row[0] == 72
        assert row[1] == "HIGH"
