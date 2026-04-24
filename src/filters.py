"""Deduplication, scoring, and candidate selection."""
from __future__ import annotations

import logging
from typing import List
from urllib.parse import urlparse

from .models import FilteredItem, RawItem

logger = logging.getLogger("tech-radar.filters")

# Keywords that raise the score
_PRIORITY_KEYWORDS: List[str] = [
    "AI", "agent", "LLM", "Claude", "Gemini", "Copilot",
    "spec-driven", "workflow", "automation", "creative coding",
    "HCI", "game", "Minecraft", "simulation", "world generation",
    "generative art", "open source", "developer tools",
    "GPT", "transformer", "diffusion", "neural", "language model",
    "code generation", "autonomous", "multimodal", "RAG",
    "embedding", "vector", "tool use", "function calling",
    "fine-tuning", "inference", "prompt", "context window",
    "reasoning", "planning", "memory", "retrieval",
    "creative tool", "narrative", "procedural", "generative",
    "self-hosted", "local model", "open weights",
]

# Keywords that lower the score
_DEFAULT_AVOID: List[str] = [
    "crypto", "bitcoin", "blockchain", "nft", "web3",
    "defi", "token sale", "ico", "marketing", "press release",
    "funding round", "series a", "series b",
]


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def _normalize_url(url: str) -> str:
    """Strip scheme, www, and trailing slash for dedup comparison."""
    try:
        parsed = urlparse(url.lower())
        host = parsed.netloc.removeprefix("www.")
        path = parsed.path.rstrip("/")
        return f"{host}{path}"
    except Exception:
        return url.lower().rstrip("/")


def deduplicate(items: List[RawItem]) -> List[RawItem]:
    """Remove items with duplicate URLs, keeping the first occurrence."""
    seen: set[str] = set()
    unique: List[RawItem] = []
    for item in items:
        key = _normalize_url(item.url)
        if key not in seen:
            seen.add(key)
            unique.append(item)

    removed = len(items) - len(unique)
    if removed:
        logger.info("Dedup removed %d duplicates → %d unique items.", removed, len(unique))
    return unique


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _score(item: RawItem, avoid_keywords: List[str]) -> FilteredItem:
    """Compute a relevance score for a single item."""
    text = f"{item.title} {item.description or ''}".lower()

    matched = [kw for kw in _PRIORITY_KEYWORDS if kw.lower() in text]
    avoided = [kw for kw in avoid_keywords if kw.lower() in text]

    # +2 per priority hit, -3 per avoid hit
    score = float(len(matched) * 2 - len(avoided) * 3)

    return FilteredItem(
        **item.model_dump(),
        score=score,
        keywords_matched=matched,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def filter_and_rank(
    items: List[RawItem],
    profile: dict,
    max_candidates: int = 20,
) -> List[FilteredItem]:
    """Deduplicate, score, and return the top-N candidates.

    Args:
        items: Raw items from all sources.
        profile: Parsed profile.yaml dict.
        max_candidates: How many items to forward to Gemini.

    Returns:
        Sorted list of up to *max_candidates* FilteredItems.
    """
    user = profile.get("user_profile", {})
    avoid_keywords = user.get("avoid", _DEFAULT_AVOID)
    # Merge user avoid list with defaults
    all_avoid = list({kw.lower() for kw in _DEFAULT_AVOID + avoid_keywords})

    unique = deduplicate(items)
    scored = [_score(item, all_avoid) for item in unique]
    scored.sort(key=lambda x: x.score, reverse=True)

    top = scored[:max_candidates]
    logger.info(
        "filter_and_rank: %d unique → top %d candidates selected.",
        len(scored),
        len(top),
    )
    return top
