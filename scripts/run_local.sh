#!/usr/bin/env bash
# AI Agents for Supplier Risk Assessment
# Author: Armand Amoussou
# Run the daily pipeline locally.
# Usage: bash scripts/run_local.sh [YYYY-MM-DD]

set -euo pipefail

VENV_DIR=".venv"
DATE="${1:-$(date +%Y-%m-%d)}"

if [ ! -d "$VENV_DIR" ]; then
    echo "ERROR: Virtual environment not found. Run: bash scripts/bootstrap.sh"
    exit 1
fi

echo "=== Running daily pipeline for $DATE ==="
"$VENV_DIR/bin/python" -m app.cli.main run-daily --date "$DATE"

echo ""
echo "=== Exporting results ==="
"$VENV_DIR/bin/python" -m app.cli.main export --date "$DATE"

echo ""
echo "=== Done ==="
echo "Check output in: ./out/"
