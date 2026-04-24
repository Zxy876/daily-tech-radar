"""Tech Radar — Daily Inspiration Engine

Entry point:
    python -m src.main

Environment variables (set in .env or GitHub Secrets):
    GEMINI_API_KEY        — required for AI analysis
    TELEGRAM_BOT_TOKEN    — required for Telegram notification
    TELEGRAM_CHAT_ID      — required for Telegram notification
    MOCK_MODE             — set to "true" to skip real API calls (local testing)
    LOG_LEVEL             — default INFO
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .fetchers import fetch_all
from .filters import filter_and_rank
from .gemini_client import analyze, make_fallback_report, mock_analyze
from .models import DailyReport
from .storage import save_data, save_raw, save_report
from .telegram_client import format_message, send_message
from .utils import get_beijing_date, get_project_root, setup_logging

logger = setup_logging(os.environ.get("LOG_LEVEL", "INFO"))


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------


def _load_config() -> tuple[dict, dict]:
    root = get_project_root()
    sources_path = root / "config" / "sources.yaml"
    profile_path = root / "config" / "profile.yaml"

    with open(sources_path, encoding="utf-8") as f:
        sources_cfg: dict = yaml.safe_load(f)
    with open(profile_path, encoding="utf-8") as f:
        profile_cfg: dict = yaml.safe_load(f)

    return sources_cfg, profile_cfg


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run() -> None:
    load_dotenv()

    mock_mode = os.environ.get("MOCK_MODE", "").lower() in ("1", "true", "yes")

    logger.info("=" * 60)
    logger.info("疯狂发明家技术雷达 — Starting%s", " (MOCK MODE)" if mock_mode else "")
    logger.info("=" * 60)

    date = get_beijing_date()
    logger.info("Date (Beijing): %s", date)

    # ── 1. Load config ───────────────────────────────────────────────────────
    try:
        sources_cfg, profile_cfg = _load_config()
    except Exception as exc:
        logger.critical("Cannot load config files: %s", exc)
        sys.exit(1)

    sources = sources_cfg.get("sources", [])
    user_profile = profile_cfg.get("user_profile", {})
    max_candidates: int = user_profile.get("max_candidates", 20)

    # ── 2. Fetch ─────────────────────────────────────────────────────────────
    if mock_mode:
        logger.info("MOCK_MODE: skipping real HTTP fetches.")
        from .models import RawItem  # local import to keep top clean

        raw_items = [
            RawItem(
                title="[Mock] Open Interpreter v2 — local agent framework",
                url="https://github.com/OpenInterpreter/open-interpreter",
                source="Mock Source",
                description="Run LLM-generated code locally on your machine.",
            ),
            RawItem(
                title="[Mock] Gemini 2.0 Flash — sub-second multimodal reasoning",
                url="https://deepmind.google/technologies/gemini/flash/",
                source="Mock Source",
                description=(
                    "Gemini 2.0 Flash achieves state-of-the-art performance "
                    "with sub-second latency for agentic tasks."
                ),
            ),
            RawItem(
                title="[Mock] CrewAI — multi-agent orchestration for AI workflows",
                url="https://github.com/crewAIInc/crewAI",
                source="Mock Source",
                description=(
                    "Framework for orchestrating role-playing autonomous AI agents."
                ),
            ),
        ]
    else:
        raw_items = fetch_all(sources)

    if not raw_items:
        logger.warning("No items fetched from any source. Generating empty fallback.")

    # ── 3. Filter & rank ─────────────────────────────────────────────────────
    candidates = filter_and_rank(raw_items, profile_cfg, max_candidates=max_candidates)

    # ── 4. Save raw data ─────────────────────────────────────────────────────
    try:
        save_raw(candidates, date)
    except Exception as exc:
        logger.error("Failed to save raw data: %s", exc)

    # ── 5. Gemini analysis ───────────────────────────────────────────────────
    gemini_success = False
    analysis_md = ""

    if mock_mode:
        analysis_md = mock_analyze(candidates)
        gemini_success = True
    elif not candidates:
        analysis_md = make_fallback_report(date, candidates, "没有可用的候选内容")
    else:
        try:
            analysis_md = analyze(candidates)
            gemini_success = True
            logger.info("Gemini analysis complete.")
        except ValueError as exc:
            logger.warning("Gemini skipped: %s", exc)
            analysis_md = make_fallback_report(date, candidates, str(exc))
        except Exception as exc:
            logger.error("Gemini failed: %s", exc)
            analysis_md = make_fallback_report(date, candidates, str(exc))

    # ── 6. Assemble full Markdown ────────────────────────────────────────────
    full_markdown = (
        f"# 疯狂发明家技术雷达 - {date}\n\n"
        + analysis_md
    )

    # ── 7. Save report & data ────────────────────────────────────────────────
    report_path = Path(f"reports/{date}.md")
    try:
        report_path = save_report(full_markdown, date)
    except Exception as exc:
        logger.error("Failed to save Markdown report: %s", exc)

    report = DailyReport(
        date=date,
        candidates=candidates,
        raw_markdown=full_markdown,
        gemini_success=gemini_success,
    )

    try:
        save_data(report, date)
    except Exception as exc:
        logger.error("Failed to save JSON data: %s", exc)

    # ── 8. Telegram notification ─────────────────────────────────────────────
    try:
        rel_path = f"reports/{date}.md"
        tg_message = format_message(date, full_markdown, rel_path)
        sent = send_message(tg_message)
        report.telegram_sent = sent
    except Exception as exc:
        logger.error("Telegram notification error: %s", exc)

    # ── Done ─────────────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("Run complete.")
    logger.info("  reports/%s.md", date)
    logger.info("  data/%s.json", date)
    logger.info("  raw/%s.json", date)
    logger.info("  Gemini success : %s", gemini_success)
    logger.info("  Telegram sent  : %s", report.telegram_sent)
    logger.info("=" * 60)


if __name__ == "__main__":
    run()
