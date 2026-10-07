"""
OmniSignal NewsAPI Integration
Fetches multi-source news headlines as primary sentiment input.

Free tier: 100 requests/day.
Covers: Reuters, Bloomberg, FT, WSJ, CNBC, AP, and 80k+ sources.
Falls back gracefully to empty list if key missing or quota exceeded.
"""

from __future__ import annotations

import logging

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

NEWSAPI_BASE = "https://newsapi.org/v2/everything"

#: When NewsAPI last answered 401, this process stops sending it requests for
#: a while. A 401 is not transient: the same key gets the same answer, so
#: retrying on every analysis spends quota and log lines to learn nothing.
#: Process-wide on purpose — each analysis builds its own client, so state on
#: the instance would be forgotten between requests.
REJECTION_WINDOW_SECONDS = 900.0
_rejected_until = 0.0


def credential_rejected() -> bool:
    """True while a recent 401 says the configured key is not accepted."""
    return time.monotonic() < _rejected_until


class NewsAPIClient:
    """
    Thin wrapper around NewsAPI /v2/everything endpoint.
    Returns structured headline dicts compatible with SentimentAnalyzer.
    """

    # Prioritised sources for financial news — NewsAPI source IDs
    FINANCE_SOURCES = ",".join([
        "reuters", "bloomberg", "financial-times", "the-wall-street-journal",
        "cnbc", "fortune", "business-insider", "the-economist",
    ])

    def __init__(self, api_key: Optional[str] = None):
        self.api_key  = api_key or os.getenv("NEWSAPI_KEY", "")
        # A key that is present *and* not recently refused. Presence alone
        # reported a key NewsAPI had answered `apiKeyInvalid` as available.
        self.available = bool(self.api_key and len(self.api_key) > 5) and not credential_rejected()
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "OmniSignal/1.0",
            "X-Api-Key": self.api_key,
        })

    def fetch_headlines(self, ticker: str, company_name: str = "", max_results: int = 8) -> list[dict]:
        """
        Fetch recent news for a ticker from NewsAPI.

        Args:
            ticker: Stock ticker symbol e.g. "NVDA"
            company_name: Optional full name e.g. "Nvidia" for better search
            max_results: Max headlines to return

        Returns:
            List of {"title": str, "source": str, "is_breaking": bool} dicts.
            Empty list when nothing was retrieved — the caller falls through to
            the next source and names the one that actually answered, so an
            empty list here is never presented as "no news exists".
        """
        if not self.available or credential_rejected():
            return []

        # Build a focused query: ticker + optional company name
        # Using OR logic broadens recall without sacrificing precision
        if company_name:
            query = f'("{ticker}" OR "{company_name}") stock'
        else:
            query = f'"{ticker}" stock'

        # Last 7 days
        from_date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")

        params = {
            "q":        query,
            "from":     from_date,
            "sortBy":   "publishedAt",
            "language": "en",
            "pageSize": min(max_results, 20),  # API max is 100 but keep it lean
        }

        try:
            r = self._session.get(NEWSAPI_BASE, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()

            if data.get("status") != "ok":
                logger.warning("NewsAPI non-ok status: %s", data.get('message', 'unknown error'))
                return []

            articles = data.get("articles", [])
            results  = []

            for article in articles[:max_results]:
                title  = article.get("title", "").strip()
                source = article.get("source", {}).get("name", "NewsAPI")

                # Skip removed/placeholder articles
                if not title or title == "[Removed]" or len(title) < 10:
                    continue

                # Strip source suffix if present (some titles include " - Reuters")
                if " - " in title:
                    parts  = title.rsplit(" - ", 1)
                    # Only strip if the suffix is a known source name
                    title = parts[0].strip()
                    if not source or source == "NewsAPI":
                        source = parts[1].strip()

                # `urlToImage`, `description` and `author` were all in this
                # response and all dropped. The image is the publisher's own
                # photograph for the story — the one image the product must
                # never substitute a stock library for — and NewsAPI was the
                # last news vendor still discarding it.
                results.append({
                    "title":      title,
                    "source":     source,
                    "is_breaking": False,   # NewsAPI doesn't flag breaking; sentiment scorer handles it
                    "url":        article.get("url", ""),
                    "published":  article.get("publishedAt", ""),
                    "image":      article.get("urlToImage") or "",
                    "summary":    (article.get("description") or "")[:280],
                    "author":     article.get("author") or "",
                })

            return results

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 426:
                logger.warning("NewsAPI upgrade required (426) — free tier limitation")
            elif e.response is not None and e.response.status_code == 401:
                global _rejected_until
                if not credential_rejected():
                    logger.error(
                        "NewsAPI rejected the API key (401); not retrying for %.0fs",
                        REJECTION_WINDOW_SECONDS,
                    )
                _rejected_until = time.monotonic() + REJECTION_WINDOW_SECONDS
            elif e.response is not None and e.response.status_code == 429:
                logger.warning("NewsAPI rate limit exceeded (429)")
            else:
                logger.warning("NewsAPI HTTP error: %s", e)
            return []
        except Exception as e:
            logger.warning("NewsAPI fetch failed: %s", e)
            return []
