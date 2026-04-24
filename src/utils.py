"""Utility helpers: logging setup, date, path resolution."""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure root logging and return the project logger."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    return logging.getLogger("tech-radar")


def get_beijing_date() -> str:
    """Return today's date string in Beijing timezone (UTC+8) as YYYY-MM-DD."""
    beijing_tz = timezone(timedelta(hours=8))
    return datetime.now(beijing_tz).strftime("%Y-%m-%d")


def get_project_root() -> Path:
    """Return the absolute path to the project root directory."""
    # src/utils.py -> src/ -> project root
    return Path(__file__).parent.parent
