"""File storage: raw JSON, structured JSON, and Markdown reports."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List

from .models import DailyReport, FilteredItem
from .utils import get_project_root

logger = logging.getLogger("tech-radar.storage")


def _ensure_dirs() -> None:
    """Create output directories if they don't exist."""
    root = get_project_root()
    for d in ("reports", "data", "raw", "feedback"):
        (root / d).mkdir(parents=True, exist_ok=True)


def save_raw(items: List[FilteredItem], date: str) -> Path:
    """Save raw (filtered) candidates to raw/<date>.json."""
    _ensure_dirs()
    path = get_project_root() / "raw" / f"{date}.json"
    payload = [item.model_dump() for item in items]
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Raw data saved  → %s", path.relative_to(get_project_root()))
    return path


def save_report(markdown: str, date: str) -> Path:
    """Save the Markdown report to reports/<date>.md."""
    _ensure_dirs()
    path = get_project_root() / "reports" / f"{date}.md"
    path.write_text(markdown, encoding="utf-8")
    logger.info("Report saved    → %s", path.relative_to(get_project_root()))
    return path


def save_data(report: DailyReport, date: str) -> Path:
    """Save the structured DailyReport to data/<date>.json."""
    _ensure_dirs()
    path = get_project_root() / "data" / f"{date}.json"
    path.write_text(
        json.dumps(report.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Data saved      → %s", path.relative_to(get_project_root()))
    return path
