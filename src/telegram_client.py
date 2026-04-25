"""Telegram Bot API client.

Sends a concise daily summary to a Telegram chat.
All failures are non-fatal — report generation continues regardless.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger("tech-radar.telegram")

_SEND_MESSAGE_URL = "https://api.telegram.org/bot{token}/sendMessage"
_MAX_MESSAGE_LEN = 4096  # Telegram hard limit


@dataclass
class TelegramResult:
    """Result of a Telegram send attempt.

    Attributes:
        sent: True if the message was delivered successfully.
        status: One of "sent", "skipped_missing_credentials", "failed", or "not_attempted".
        reason: Human-readable description of the outcome or error.
    """

    sent: bool
    status: str
    reason: str


# ---------------------------------------------------------------------------
# Message formatter
# ---------------------------------------------------------------------------


def _extract_section(lines: list[str], keyword: str) -> str:
    """Extract text content of a Markdown section matching *keyword*."""
    content: list[str] = []
    capturing = False
    for line in lines:
        if keyword in line and line.startswith("##"):
            capturing = True
            continue
        if capturing:
            if line.startswith("## "):
                break
            content.append(line)
    return "\n".join(content).strip()


def format_message(date: str, markdown_report: str, report_path: str) -> str:
    """Build a Telegram-ready summary from the Markdown report."""
    lines = markdown_report.split("\n")

    # Collect item titles (lines starting with "## " that are NOT section headers)
    _section_keywords = {"今日模式", "今日可做", "今日小实验", "今日精选", "候选内容"}
    item_titles: list[str] = []
    for line in lines:
        if line.startswith("## ") and not any(kw in line for kw in _section_keywords):
            title = line.lstrip("# ").strip("[] ").strip()
            if title:
                item_titles.append(title)

    # Pattern summary
    pattern = _extract_section(lines, "今日模式总结")[:350]

    # Experiment
    experiment = _extract_section(lines, "今日可做小实验")[:450]

    parts: list[str] = [
        f"🔭 *疯狂发明家技术雷达* | {date}",
        "",
    ]

    if item_titles:
        parts.append(f"📌 *今日精选（{len(item_titles)} 条）*")
        for t in item_titles[:5]:
            # Escape special Markdown characters for Telegram v1 Markdown
            safe = t.replace("*", "").replace("_", "").replace("`", "")
            parts.append(f"• {safe}")
        parts.append("")

    if pattern:
        parts.append("🧩 *今日技术模式*")
        parts.append(pattern)
        parts.append("")

    if experiment:
        parts.append("⚡ *今日可做小实验*")
        parts.append(experiment)
        parts.append("")

    parts += [
        f"📄 报告：`{report_path}`",
        "",
        "💬 反馈格式（回复本消息）：",
        "👍 关键词 = 喜欢  |  ⭐ 关键词 = 想深入  |  👎 关键词 = 不感兴趣",
    ]

    message = "\n".join(parts)

    if len(message) > _MAX_MESSAGE_LEN:
        message = message[: _MAX_MESSAGE_LEN - 20] + "\n…（消息已截断）"

    return message


# ---------------------------------------------------------------------------
# Sender
# ---------------------------------------------------------------------------


def send_message(
    message: str,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> TelegramResult:
    """Send *message* to a Telegram chat. Returns a TelegramResult."""
    token = (bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip()
    cid = (chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")).strip()

    if not token or not cid:
        logger.warning(
            "Telegram credentials not configured "
            "(TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID). Skipping notification."
        )
        return TelegramResult(
            sent=False,
            status="skipped_missing_credentials",
            reason="TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing",
        )

    url = _SEND_MESSAGE_URL.format(token=token)
    payload = {
        "chat_id": cid,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    try:
        resp = requests.post(url, json=payload, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            logger.info("Telegram message sent successfully.")
            return TelegramResult(
                sent=True,
                status="sent",
                reason="Telegram message sent successfully",
            )
        logger.error("Telegram API error: %s", data)
        return TelegramResult(sent=False, status="failed", reason=str(data))
    except Exception as exc:
        logger.error("Failed to send Telegram message: %s", exc)
        return TelegramResult(sent=False, status="failed", reason=str(exc))
