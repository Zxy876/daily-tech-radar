"""Source fetchers: RSS feeds and GitHub Trending HTML scraper."""
from __future__ import annotations

import logging
from typing import List

import feedparser
import requests
from bs4 import BeautifulSoup

from .models import RawItem

logger = logging.getLogger("tech-radar.fetchers")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
_REQUEST_TIMEOUT = 20  # seconds


# ---------------------------------------------------------------------------
# RSS fetcher
# ---------------------------------------------------------------------------


def fetch_rss(name: str, url: str) -> List[RawItem]:
    """Fetch and parse an RSS feed. Returns an empty list on any error."""
    items: List[RawItem] = []
    try:
        logger.info("Fetching RSS  : %s  (%s)", name, url)
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            logger.warning("  RSS parse issue for %s: %s", name, feed.bozo_exception)

        for entry in feed.entries[:40]:
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not title or not link:
                continue

            # Extract plain-text summary
            raw_summary = (
                entry.get("summary")
                or entry.get("description")
                or ""
            )
            description: str | None = None
            if raw_summary:
                soup = BeautifulSoup(raw_summary, "html.parser")
                description = soup.get_text(separator=" ", strip=True)[:500] or None

            published = entry.get("published") or entry.get("updated")

            items.append(
                RawItem(
                    title=title,
                    url=link,
                    source=name,
                    published_at=str(published) if published else None,
                    description=description,
                )
            )

        logger.info("  -> %d items from %s", len(items), name)
    except Exception as exc:
        logger.error("Failed to fetch RSS %s: %s", name, exc)

    return items


# ---------------------------------------------------------------------------
# GitHub Trending HTML scraper
# ---------------------------------------------------------------------------


def fetch_github_trending(name: str, url: str) -> List[RawItem]:
    """Scrape a GitHub Trending page. Returns an empty list on any error."""
    items: List[RawItem] = []
    try:
        logger.info("Fetching HTML : %s  (%s)", name, url)
        resp = requests.get(url, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        repo_articles = soup.select("article.Box-row")

        for article in repo_articles[:25]:
            h2 = article.select_one("h2 a")
            if not h2:
                continue
            repo_path = h2.get("href", "").strip().strip("/")
            if not repo_path or "/" not in repo_path:
                continue

            owner, repo = repo_path.split("/", 1)
            title = f"{owner} / {repo}"
            full_url = f"https://github.com/{repo_path}"

            desc_el = article.select_one("p")
            description = desc_el.get_text(strip=True) if desc_el else None

            # Stars today
            stars_el = article.select_one("span.d-inline-block.float-sm-right")
            if stars_el:
                stars_text = stars_el.get_text(strip=True)
                if description:
                    description = f"{description} [{stars_text}]"
                else:
                    description = stars_text

            items.append(
                RawItem(
                    title=title,
                    url=full_url,
                    source=name,
                    description=description,
                )
            )

        logger.info("  -> %d items from %s", len(items), name)
    except Exception as exc:
        logger.error("Failed to fetch GitHub Trending %s: %s", name, exc)

    return items


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def fetch_all(sources: list) -> List[RawItem]:
    """Fetch from all configured sources. Failures are non-fatal."""
    all_items: List[RawItem] = []

    for source in sources:
        src_type = source.get("type", "rss")
        name = source.get("name", "Unknown")
        url = source.get("url", "")

        if not url:
            logger.warning("No URL configured for source '%s', skipping.", name)
            continue

        if src_type == "rss":
            all_items.extend(fetch_rss(name, url))
        elif src_type == "html":
            all_items.extend(fetch_github_trending(name, url))
        else:
            logger.warning("Unknown source type '%s' for '%s', skipping.", src_type, name)

    logger.info("Total raw items fetched: %d", len(all_items))
    return all_items
