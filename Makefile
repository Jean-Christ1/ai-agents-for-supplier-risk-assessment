# AI Agents for Supplier Risk Assessment
# Author: Armand Amoussou

.PHONY: bootstrap test lint typecheck run run-golden export clean docker-up docker-down help

PYTHON ?= python3.11
VENV := .venv
PIP := $(VENV)/bin/pip
PYTHON_BIN := $(VENV)/bin/python
PYTEST := $(VENV)/bin/pytest
RUFF := $(VENV)/bin/ruff
MYPY := $(VENV)/bin/mypy

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

bootstrap: ## Full setup: venv + deps + DB schema
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install pip-tools
	$(VENV)/bin/pip-compile --generate-hashes --output-file=requirements.txt requirements.in
	$(PIP) install -r requirements.txt
	@echo "--- Bootstrap complete. Activate venv: source $(VENV)/bin/activate ---"

install: ## Install deps from locked requirements.txt
	$(PIP) install -r requirements.txt

lock: ## Re-lock dependencies
	$(VENV)/bin/pip-compile --generate-hashes --output-file=requirements.txt requirements.in

test: ## Run all tests with coverage
	$(PYTEST) tests/ -v --tb=short --cov=app --cov-report=term-missing

test-golden: ## Run golden test suite only
	$(PYTEST) tests/test_financial_golden.py -v --tb=short

lint: ## Run ruff linter + formatter check
	$(RUFF) check app/ tests/
	$(RUFF) format --check app/ tests/

lint-fix: ## Auto-fix lint issues
	$(RUFF) check --fix app/ tests/
	$(RUFF) format app/ tests/

typecheck: ## Run mypy type checking
	$(MYPY) app/ --ignore-missing-imports

run: ## Run daily pipeline (today)
	$(PYTHON_BIN) -m app.cli.main run-daily

run-date: ## Run pipeline for specific date: make run-date DATE=2026-01-15
	$(PYTHON_BIN) -m app.cli.main run-daily --date $(DATE)

run-golden: ## Run pipeline in golden/offline mode
	GOLDEN_MODE=1 $(PYTHON_BIN) -m app.cli.main run-daily

export: ## Export latest scores to CSV/JSON
	$(PYTHON_BIN) -m app.cli.main export

seed: ## Load seed supplier data into DB
	$(PYTHON_BIN) -m app.cli.main seed

docker-up: ## Start PostgreSQL (+ optional MailHog)
	docker compose -f docker/docker-compose.yml up -d

docker-up-mail: ## Start PostgreSQL + MailHog
	docker compose -f docker/docker-compose.yml --profile mailhog up -d

docker-down: ## Stop all Docker services
	docker compose -f docker/docker-compose.yml --profile mailhog down

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov .coverage out/
