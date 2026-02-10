"""Database access layer with PostgreSQL primary and DuckDB fallback.

Author: Armand Amoussou
"""

from __future__ import annotations

import datetime
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional, Protocol

from app.observability.logger import get_logger

logger = get_logger("db")


class DBConnection(Protocol):
    """Protocol for database connections."""

    def execute(self, query: str, params: tuple | None = None) -> Any: ...  # noqa: ANN401
    def fetchall(self) -> list[tuple]: ...
    def fetchone(self) -> Optional[tuple]: ...
    def commit(self) -> None: ...
    def close(self) -> None: ...


class PostgresBackend:
    """PostgreSQL database backend."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._conn = None

    def connect(self) -> None:
        import psycopg2

        self._conn = psycopg2.connect(self.dsn)
        logger.info("db_connected", backend="postgres")

    @contextmanager
    def cursor(self) -> Generator:  # type: ignore[type-arg]
        if self._conn is None:
            self.connect()
        cur = self._conn.cursor()  # type: ignore[union-attr]
        try:
            yield cur
            self._conn.commit()  # type: ignore[union-attr]
        except Exception:
            self._conn.rollback()  # type: ignore[union-attr]
            raise
        finally:
            cur.close()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def execute_schema(self, sql_path: str) -> None:
        """Execute a SQL schema file."""
        sql = Path(sql_path).read_text(encoding="utf-8")
        with self.cursor() as cur:
            cur.execute(sql)
        logger.info("schema_executed", path=sql_path)


class DuckDBBackend:
    """DuckDB fallback database backend."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._conn = None

    def connect(self) -> None:
        import duckdb

        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(self.db_path)
        logger.info("db_connected", backend="duckdb", path=self.db_path)

    @contextmanager
    def cursor(self) -> Generator:  # type: ignore[type-arg]
        if self._conn is None:
            self.connect()
        try:
            yield self._conn
        except Exception:
            raise

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def execute_schema(self, sql_path: str) -> None:
        """Execute SQL schema, adapting Postgres syntax for DuckDB."""
        sql = Path(sql_path).read_text(encoding="utf-8")
        # DuckDB adaptations
        sql = sql.replace("TIMESTAMPTZ", "TIMESTAMP")
        sql = sql.replace("JSONB", "JSON")
        sql = sql.replace("SERIAL", "INTEGER")
        sql = sql.replace("NOW()", "CURRENT_TIMESTAMP")
        # Remove REFERENCES constraints (DuckDB handles differently)
        import re

        sql = re.sub(r"REFERENCES\s+\w+\(\w+\)", "", sql)
        with self.cursor() as conn:
            conn.execute(sql)
        logger.info("schema_executed", path=sql_path, backend="duckdb")


def get_db_backend(
    backend_type: str = "postgres",
    postgres_dsn: str = "",
    duckdb_path: str = "",
) -> PostgresBackend | DuckDBBackend:
    """Factory to get database backend. Tries Postgres first, falls back to DuckDB."""
    if backend_type == "postgres":
        try:
            db = PostgresBackend(postgres_dsn)
            db.connect()
            return db
        except Exception as e:
            logger.warning(
                "postgres_unavailable_fallback_duckdb",
                error=str(e),
            )
            db_duck = DuckDBBackend(duckdb_path or "./data/supplier_risk.duckdb")
            db_duck.connect()
            return db_duck
    else:
        db_duck = DuckDBBackend(duckdb_path or "./data/supplier_risk.duckdb")
        db_duck.connect()
        return db_duck


# --- Data access functions ---


def upsert_supplier(
    db: PostgresBackend | DuckDBBackend, supplier: dict  # type: ignore[type-arg]
) -> None:
    """Insert or update a supplier in supplier_dim."""
    if isinstance(db, PostgresBackend):
        with db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO supplier_dim (supplier_id, name, country, tier, category)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (supplier_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    country = EXCLUDED.country,
                    tier = EXCLUDED.tier,
                    category = EXCLUDED.category
                """,
                (
                    supplier["supplier_id"],
                    supplier["name"],
                    supplier["country"],
                    supplier["tier"],
                    supplier["category"],
                ),
            )
    else:
        with db.cursor() as conn:
            # DuckDB: try insert, ignore on conflict
            try:
                conn.execute(
                    """
                    INSERT INTO supplier_dim (supplier_id, name, country, tier, category)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        supplier["supplier_id"],
                        supplier["name"],
                        supplier["country"],
                        supplier["tier"],
                        supplier["category"],
                    ],
                )
            except Exception:
                conn.execute(
                    """
                    UPDATE supplier_dim SET name=?, country=?, tier=?, category=?
                    WHERE supplier_id=?
                    """,
                    [
                        supplier["name"],
                        supplier["country"],
                        supplier["tier"],
                        supplier["category"],
                        supplier["supplier_id"],
                    ],
                )


def insert_internal_signals(
    db: PostgresBackend | DuckDBBackend,
    as_of_date: datetime.date,
    supplier_id: str,
    c1_raw: float,
    c2_raw: float,
    c3_raw: float,
    payload: dict,  # type: ignore[type-arg]
) -> None:
    """Insert internal signals for a supplier/date."""
    payload_json = json.dumps(payload)
    if isinstance(db, PostgresBackend):
        with db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO internal_signals_daily
                    (as_of_date, supplier_id, c1_raw, c2_raw, c3_raw, payload)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (as_of_date, supplier_id) DO UPDATE SET
                    c1_raw = EXCLUDED.c1_raw,
                    c2_raw = EXCLUDED.c2_raw,
                    c3_raw = EXCLUDED.c3_raw,
                    payload = EXCLUDED.payload
                """,
                (as_of_date, supplier_id, c1_raw, c2_raw, c3_raw, payload_json),
            )
    else:
        with db.cursor() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO internal_signals_daily
                        (as_of_date, supplier_id, c1_raw, c2_raw, c3_raw, payload)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [as_of_date, supplier_id, c1_raw, c2_raw, c3_raw, payload_json],
                )
            except Exception:
                conn.execute(
                    """
                    UPDATE internal_signals_daily
                    SET c1_raw=?, c2_raw=?, c3_raw=?, payload=?
                    WHERE as_of_date=? AND supplier_id=?
                    """,
                    [c1_raw, c2_raw, c3_raw, payload_json, as_of_date, supplier_id],
                )


def insert_financial_score(
    db: PostgresBackend | DuckDBBackend,
    as_of_date: datetime.date,
    supplier_id: str,
    score: int,
    level: str,
    confidence: float,
    output: dict,  # type: ignore[type-arg]
) -> None:
    """Insert a financial score record."""
    output_json = json.dumps(output)
    if isinstance(db, PostgresBackend):
        with db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO financial_scores_daily
                    (as_of_date, supplier_id, score, level, confidence, output)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (as_of_date, supplier_id) DO UPDATE SET
                    score = EXCLUDED.score,
                    level = EXCLUDED.level,
                    confidence = EXCLUDED.confidence,
                    output = EXCLUDED.output
                """,
                (as_of_date, supplier_id, score, level, confidence, output_json),
            )
    else:
        with db.cursor() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO financial_scores_daily
                        (as_of_date, supplier_id, score, level, confidence, output)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [as_of_date, supplier_id, score, level, confidence, output_json],
                )
            except Exception:
                conn.execute(
                    """
                    UPDATE financial_scores_daily
                    SET score=?, level=?, confidence=?, output=?
                    WHERE as_of_date=? AND supplier_id=?
                    """,
                    [score, level, confidence, output_json, as_of_date, supplier_id],
                )


def insert_daily_score(
    db: PostgresBackend | DuckDBBackend,
    score: dict,  # type: ignore[type-arg]
) -> None:
    """Insert a supplier daily aggregate score."""
    if isinstance(db, PostgresBackend):
        with db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO supplier_daily_scores
                    (as_of_date, supplier_id, c1_score, c2_score, c3_score,
                     financial_score, global_score, risk_level)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (as_of_date, supplier_id) DO UPDATE SET
                    c1_score = EXCLUDED.c1_score,
                    c2_score = EXCLUDED.c2_score,
                    c3_score = EXCLUDED.c3_score,
                    financial_score = EXCLUDED.financial_score,
                    global_score = EXCLUDED.global_score,
                    risk_level = EXCLUDED.risk_level
                """,
                (
                    score["as_of_date"],
                    score["supplier_id"],
                    score.get("c1_score"),
                    score.get("c2_score"),
                    score.get("c3_score"),
                    score.get("financial_score"),
                    score["global_score"],
                    score["risk_level"],
                ),
            )
    else:
        with db.cursor() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO supplier_daily_scores
                        (as_of_date, supplier_id, c1_score, c2_score, c3_score,
                         financial_score, global_score, risk_level)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        score["as_of_date"],
                        score["supplier_id"],
                        score.get("c1_score"),
                        score.get("c2_score"),
                        score.get("c3_score"),
                        score.get("financial_score"),
                        score["global_score"],
                        score["risk_level"],
                    ],
                )
            except Exception:
                conn.execute(
                    """
                    UPDATE supplier_daily_scores
                    SET c1_score=?, c2_score=?, c3_score=?,
                        financial_score=?, global_score=?, risk_level=?
                    WHERE as_of_date=? AND supplier_id=?
                    """,
                    [
                        score.get("c1_score"),
                        score.get("c2_score"),
                        score.get("c3_score"),
                        score.get("financial_score"),
                        score["global_score"],
                        score["risk_level"],
                        score["as_of_date"],
                        score["supplier_id"],
                    ],
                )


def insert_run_audit(
    db: PostgresBackend | DuckDBBackend,
    audit: dict,  # type: ignore[type-arg]
) -> None:
    """Insert or update a run audit record."""
    if isinstance(db, PostgresBackend):
        with db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO run_audit
                    (run_id, started_at, finished_at, status, errors,
                     llm_cost_estimate, counts)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET
                    finished_at = EXCLUDED.finished_at,
                    status = EXCLUDED.status,
                    errors = EXCLUDED.errors,
                    llm_cost_estimate = EXCLUDED.llm_cost_estimate,
                    counts = EXCLUDED.counts
                """,
                (
                    audit["run_id"],
                    audit["started_at"],
                    audit.get("finished_at"),
                    audit["status"],
                    json.dumps(audit.get("errors")),
                    audit.get("llm_cost_estimate", 0),
                    json.dumps(audit.get("counts")),
                ),
            )
    else:
        with db.cursor() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO run_audit
                        (run_id, started_at, finished_at, status, errors,
                         llm_cost_estimate, counts)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        audit["run_id"],
                        audit["started_at"],
                        audit.get("finished_at"),
                        audit["status"],
                        json.dumps(audit.get("errors")),
                        audit.get("llm_cost_estimate", 0),
                        json.dumps(audit.get("counts")),
                    ],
                )
            except Exception:
                conn.execute(
                    """
                    UPDATE run_audit
                    SET finished_at=?, status=?, errors=?,
                        llm_cost_estimate=?, counts=?
                    WHERE run_id=?
                    """,
                    [
                        audit.get("finished_at"),
                        audit["status"],
                        json.dumps(audit.get("errors")),
                        audit.get("llm_cost_estimate", 0),
                        json.dumps(audit.get("counts")),
                        audit["run_id"],
                    ],
                )


def get_previous_score(
    db: PostgresBackend | DuckDBBackend,
    supplier_id: str,
    before_date: datetime.date,
) -> Optional[dict]:  # type: ignore[type-arg]
    """Get the most recent daily score before the given date."""
    if isinstance(db, PostgresBackend):
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT as_of_date, global_score, risk_level
                FROM supplier_daily_scores
                WHERE supplier_id = %s AND as_of_date < %s
                ORDER BY as_of_date DESC LIMIT 1
                """,
                (supplier_id, before_date),
            )
            row = cur.fetchone()
    else:
        with db.cursor() as conn:
            result = conn.execute(
                """
                SELECT as_of_date, global_score, risk_level
                FROM supplier_daily_scores
                WHERE supplier_id = ? AND as_of_date < ?
                ORDER BY as_of_date DESC LIMIT 1
                """,
                [supplier_id, before_date],
            )
            row = result.fetchone()

    if row:
        return {
            "as_of_date": row[0],
            "global_score": row[1],
            "risk_level": row[2],
        }
    return None


def get_score_n_days_ago(
    db: PostgresBackend | DuckDBBackend,
    supplier_id: str,
    reference_date: datetime.date,
    days: int = 7,
) -> Optional[int]:
    """Get global_score from N days ago for delta calculation."""
    target_date = reference_date - datetime.timedelta(days=days)
    if isinstance(db, PostgresBackend):
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT global_score FROM supplier_daily_scores
                WHERE supplier_id = %s AND as_of_date = %s
                """,
                (supplier_id, target_date),
            )
            row = cur.fetchone()
    else:
        with db.cursor() as conn:
            result = conn.execute(
                """
                SELECT global_score FROM supplier_daily_scores
                WHERE supplier_id = ? AND as_of_date = ?
                """,
                [supplier_id, target_date],
            )
            row = result.fetchone()

    return row[0] if row else None


def get_all_suppliers(
    db: PostgresBackend | DuckDBBackend,
) -> list[dict]:  # type: ignore[type-arg]
    """Retrieve all suppliers from supplier_dim."""
    if isinstance(db, PostgresBackend):
        with db.cursor() as cur:
            cur.execute(
                "SELECT supplier_id, name, country, tier, category FROM supplier_dim"
            )
            rows = cur.fetchall()
    else:
        with db.cursor() as conn:
            result = conn.execute(
                "SELECT supplier_id, name, country, tier, category FROM supplier_dim"
            )
            rows = result.fetchall()

    return [
        {
            "supplier_id": r[0],
            "name": r[1],
            "country": r[2],
            "tier": r[3],
            "category": r[4],
        }
        for r in rows
    ]
