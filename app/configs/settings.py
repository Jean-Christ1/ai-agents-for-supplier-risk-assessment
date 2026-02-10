"""Application settings loaded from environment variables.

Author: Armand Amoussou
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):
    # Database
    db_backend: str = "postgres"  # "postgres" or "duckdb"
    postgres_dsn: str = (
        "postgresql://riskuser:riskpass_local@localhost:5432/supplier_risk"
    )
    duckdb_path: str = "./data/supplier_risk.duckdb"

    # LLM provider
    llm_provider: str = "openai"  # "openai" or "ollama"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    # Paths
    project_root: str = str(Path(__file__).resolve().parent.parent.parent)
    config_dir: str = str(Path(__file__).resolve().parent)
    cache_dir: str = "./cache/web"
    output_dir: str = "./out"
    golden_dir: str = str(Path(__file__).resolve().parent.parent / "golden")

    # Scraping
    request_timeout_seconds: int = 30
    max_retries: int = 3
    backoff_factor: float = 2.0

    # Alerting
    alert_mode: str = "dry_run"  # "dry_run" or "smtp"
    smtp_host: str = "localhost"
    smtp_port: int = 1025

    # Mode
    golden_mode: bool = False

    model_config = {"env_prefix": "", "env_file": ".env", "case_sensitive": False}

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        if os.environ.get("GOLDEN_MODE", "0") == "1":
            object.__setattr__(self, "golden_mode", True)


def get_settings() -> AppSettings:
    return AppSettings()
