"""
OmniSignal NewsAPI Integration
Fetches multi-source news headlines as primary sentiment input.

Free tier: 100 requests/day.
Covers: Reuters, Bloomberg, FT, WSJ, CNBC, AP, and 80k+ sources.
Falls back gracefully to empty list if key missing or quota exceeded.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

NEWSAPI_BASE = "https://newsapi.org/v2/everything"


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
        self.available = bool(self.api_key and len(self.api_key) > 5)
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
            Empty list on failure.
        """
        if not self.available:
            return []

        # Build a focused query: ticker + optional company name
        # Using OR logic broadens recall without sacrificing precision
        if company_name:
            query = f'("{ticker}" OR "{company_name}") stock'
        else:
            query = f'"{ticker}" stock'

        # Last 7 days
        from_date = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")

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
                print(f"[NewsAPI] Non-ok status: {data.get('message', 'unknown error')}")
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

                results.append({
                    "title":      title,
                    "source":     source,
                    "is_breaking": False,   # NewsAPI doesn't flag breaking; sentiment scorer handles it
                    "url":        article.get("url", ""),
                    "published":  article.get("publishedAt", ""),
                })

            return results

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 426:
                print("[NewsAPI] Upgrade required — free tier only supports headlines endpoint with developer account")
            elif e.response is not None and e.response.status_code == 401:
                print("[NewsAPI] Invalid API key")
            elif e.response is not None and e.response.status_code == 429:
                print("[NewsAPI] Rate limit exceeded")
            else:
                print(f"[NewsAPI] HTTP error: {e}")
            return []
        except Exception as e:
            print(f"[NewsAPI] Fetch failed: {e}")
            return []
