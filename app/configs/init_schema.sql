-- AI Agents for Supplier Risk Assessment
-- Author: Armand Amoussou
-- Database schema for PostgreSQL
-- Executed automatically by docker-compose on first start

CREATE TABLE IF NOT EXISTS supplier_dim (
    supplier_id   TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    country       TEXT NOT NULL,
    tier          INTEGER NOT NULL DEFAULT 1,
    category      TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS internal_signals_daily (
    as_of_date    DATE NOT NULL,
    supplier_id   TEXT NOT NULL REFERENCES supplier_dim(supplier_id),
    c1_raw        NUMERIC,
    c2_raw        NUMERIC,
    c3_raw        NUMERIC,
    payload       JSONB,
    PRIMARY KEY (as_of_date, supplier_id)
);

CREATE TABLE IF NOT EXISTS official_docs_raw (
    doc_id        TEXT PRIMARY KEY,
    supplier_id   TEXT NOT NULL REFERENCES supplier_dim(supplier_id),
    url           TEXT NOT NULL,
    domain        TEXT NOT NULL,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    http_status   INTEGER,
    content_hash  TEXT NOT NULL,
    content_text  TEXT,
    metadata      JSONB
);

CREATE TABLE IF NOT EXISTS financial_scores_daily (
    as_of_date    DATE NOT NULL,
    supplier_id   TEXT NOT NULL REFERENCES supplier_dim(supplier_id),
    score         INTEGER NOT NULL CHECK (score >= 0 AND score <= 100),
    level         TEXT NOT NULL CHECK (level IN ('LOW', 'MEDIUM', 'HIGH', 'INDETERMINATE')),
    confidence    NUMERIC NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    output        JSONB NOT NULL,
    PRIMARY KEY (as_of_date, supplier_id)
);

CREATE TABLE IF NOT EXISTS supplier_daily_scores (
    as_of_date       DATE NOT NULL,
    supplier_id      TEXT NOT NULL REFERENCES supplier_dim(supplier_id),
    c1_score         INTEGER,
    c2_score         INTEGER,
    c3_score         INTEGER,
    financial_score  INTEGER,
    global_score     INTEGER NOT NULL CHECK (global_score >= 0 AND global_score <= 100),
    risk_level       TEXT NOT NULL CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH')),
    PRIMARY KEY (as_of_date, supplier_id)
);

CREATE TABLE IF NOT EXISTS supplier_score_explanations (
    run_id        TEXT NOT NULL,
    as_of_date    DATE NOT NULL,
    supplier_id   TEXT NOT NULL REFERENCES supplier_dim(supplier_id),
    evidences     JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS run_audit (
    run_id            TEXT PRIMARY KEY,
    started_at        TIMESTAMPTZ NOT NULL,
    finished_at       TIMESTAMPTZ,
    status            TEXT NOT NULL CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED', 'PARTIAL')),
    errors            JSONB,
    llm_cost_estimate NUMERIC DEFAULT 0,
    counts            JSONB
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_daily_scores_date
    ON supplier_daily_scores(as_of_date);
CREATE INDEX IF NOT EXISTS idx_daily_scores_supplier
    ON supplier_daily_scores(supplier_id);
CREATE INDEX IF NOT EXISTS idx_financial_scores_date
    ON financial_scores_daily(as_of_date);
CREATE INDEX IF NOT EXISTS idx_official_docs_supplier
    ON official_docs_raw(supplier_id);
CREATE INDEX IF NOT EXISTS idx_run_audit_status
    ON run_audit(status);
