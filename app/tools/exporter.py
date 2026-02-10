"""Export pipeline results to CSV and JSON files.

Author: Armand Amoussou
"""

from __future__ import annotations

import csv
import datetime
import json
from pathlib import Path
from typing import Any

from app.observability.logger import get_logger

logger = get_logger("exporter")


def export_scores_csv(
    scores: list[dict[str, Any]],
    output_dir: str = "./out",
    filename: str | None = None,
) -> str:
    """Export daily scores to CSV file. Returns file path."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if filename is None:
        ts = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"scores_{ts}.csv"

    file_path = out_path / filename
    if not scores:
        logger.warning("export_csv_empty")
        return str(file_path)

    fieldnames = [
        "as_of_date",
        "supplier_id",
        "c1_score",
        "c2_score",
        "c3_score",
        "financial_score",
        "global_score",
        "risk_level",
    ]

    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for score in scores:
            writer.writerow(score)

    logger.info("export_csv_ok", file=str(file_path), count=len(scores))
    return str(file_path)


def export_scores_json(
    scores: list[dict[str, Any]],
    output_dir: str = "./out",
    filename: str | None = None,
) -> str:
    """Export daily scores to JSON file. Returns file path."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if filename is None:
        ts = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"scores_{ts}.json"

    file_path = out_path / filename

    # Convert dates to strings for JSON serialization
    serializable = []
    for s in scores:
        row = {}
        for k, v in s.items():
            if isinstance(v, (datetime.date, datetime.datetime)):
                row[k] = v.isoformat()
            else:
                row[k] = v
        serializable.append(row)

    file_path.write_text(
        json.dumps(serializable, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("export_json_ok", file=str(file_path), count=len(scores))
    return str(file_path)


def export_financial_details(
    details: list[dict[str, Any]],
    output_dir: str = "./out",
    filename: str | None = None,
) -> str:
    """Export detailed financial risk outputs to JSON."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if filename is None:
        ts = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"financial_details_{ts}.json"

    file_path = out_path / filename

    serializable = []
    for d in details:
        row = {}
        for k, v in d.items():
            if isinstance(v, (datetime.date, datetime.datetime)):
                row[k] = v.isoformat()
            else:
                row[k] = v
        serializable.append(row)

    file_path.write_text(
        json.dumps(serializable, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    logger.info("export_financial_ok", file=str(file_path), count=len(details))
    return str(file_path)
