"""Data models for the Tech Radar system."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class RawItem(BaseModel):
    """A single raw item fetched from a source."""

    title: str
    url: str
    source: str
    published_at: Optional[str] = None
    description: Optional[str] = None


class FilteredItem(RawItem):
    """A raw item after scoring and filtering."""

    score: float = 0.0
    keywords_matched: List[str] = Field(default_factory=list)


class DailyReport(BaseModel):
    """The full daily report data structure."""

    date: str
    candidates: List[FilteredItem] = Field(default_factory=list)
    raw_markdown: str = ""
    gemini_success: bool = False
    telegram_sent: bool = False
    telegram_status: str = "not_attempted"
    telegram_reason: str = ""


class FeedbackEntry(BaseModel):
    """A single feedback entry from Telegram.
    
    V1 feedback format (future use):
      👍 关键词  = 喜欢
      ⭐ 关键词  = 想深入
      👎 关键词  = 不感兴趣
    
    Stored in feedback/feedback.jsonl, one JSON per line.
    """

    date: str
    timestamp: str
    reaction: str  # "👍" | "⭐" | "👎"
    keyword: str
    source: Optional[str] = None
