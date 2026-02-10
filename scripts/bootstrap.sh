#!/usr/bin/env bash
# AI Agents for Supplier Risk Assessment
# Author: Armand Amoussou
# Bootstrap script: sets up the full development environment from scratch.
# Usage: bash scripts/bootstrap.sh

set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3.11}"
VENV_DIR=".venv"

echo "=== Supplier Risk Assessment - Bootstrap ==="
echo ""

# 1. Check Python version
echo "[1/6] Checking Python..."
if ! command -v "$PYTHON_BIN" &> /dev/null; then
    echo "ERROR: $PYTHON_BIN not found. Install Python 3.11 first."
    echo "  Ubuntu/Debian: sudo apt install python3.11 python3.11-venv"
    echo "  Fedora: sudo dnf install python3.11"
    exit 1
fi
PYTHON_VERSION=$("$PYTHON_BIN" --version 2>&1)
echo "  Found: $PYTHON_VERSION"

# 2. Create virtual environment
echo "[2/6] Creating virtual environment..."
if [ -d "$VENV_DIR" ]; then
    echo "  Virtual environment already exists, reusing."
else
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    echo "  Created: $VENV_DIR"
fi

# 3. Upgrade pip and install pip-tools
echo "[3/6] Installing pip-tools..."
"$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel
"$VENV_DIR/bin/pip" install pip-tools

# 4. Lock and install dependencies
echo "[4/6] Locking and installing dependencies..."
"$VENV_DIR/bin/pip-compile" --generate-hashes --output-file=requirements.txt requirements.in
"$VENV_DIR/bin/pip" install -r requirements.txt

# 5. Docker services (optional)
echo "[5/6] Docker services..."
if command -v docker &> /dev/null; then
    if docker compose version &> /dev/null; then
        echo "  Starting PostgreSQL via docker compose..."
        docker compose -f docker/docker-compose.yml up -d
        echo "  Waiting for PostgreSQL to be ready..."
        sleep 5
    else
        echo "  docker compose not available. Using DuckDB fallback."
        echo "  Set DB_BACKEND=duckdb in .env"
    fi
else
    echo "  Docker not installed. Using DuckDB fallback."
    echo "  Set DB_BACKEND=duckdb in .env"
fi

# 6. Create .env if not exists
echo "[6/6] Environment configuration..."
if [ ! -f .env ]; then
    cat > .env << 'ENVEOF'
# Supplier Risk Assessment - Environment Configuration
# Author: Armand Amoussou

# Database backend: "postgres" or "duckdb"
DB_BACKEND=duckdb
POSTGRES_DSN=postgresql://riskuser:riskpass_local@localhost:5432/supplier_risk
DUCKDB_PATH=./data/supplier_risk.duckdb

# LLM provider: "openai" or "ollama"
LLM_PROVIDER=openai
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b

# Alerting: "dry_run" or "smtp"
ALERT_MODE=dry_run
SMTP_HOST=localhost
SMTP_PORT=1025

# Golden mode (offline testing): 0 or 1
GOLDEN_MODE=0
ENVEOF
    echo "  Created .env file. Edit it with your API keys."
else
    echo "  .env already exists."
fi

echo ""
echo "=== Bootstrap complete ==="
echo ""
echo "Next steps:"
echo "  1. Activate venv:   source .venv/bin/activate"
echo "  2. Edit .env:       Set OPENAI_API_KEY (or use GOLDEN_MODE=1)"
echo "  3. Seed database:   make seed"
echo "  4. Run pipeline:    make run"
echo "  5. Run tests:       make test"
