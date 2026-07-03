"""
News vendors: NewsAPI (delegates to the existing client), GNews, Yahoo RSS
(keyless anchor).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from src.providers.base import VendorClient
from src.providers.schemas import NewsHeadline


class NewsApiVendor(VendorClient):
    """Thin adapter over src/news_api.NewsAPIClient."""

    NAME = "newsapi"
    KEY_ENV = "NEWSAPI_KEY"
    DEFAULT_RPM = 10  # 100/day free

    def __init__(self, session=None):
        super().__init__(session)
        from src.news_api import NewsAPIClient

        self._client = NewsAPIClient()

    def get_news(self, query: str, company_name: str = "", limit: int = 12) -> Optional[list[NewsHeadline]]:
        rows = self.timed_call(
            lambda: self._client.fetch_headlines(query, company_name=company_name, max_results=limit)
        )
        if not rows:
            return None
        return [
            NewsHeadline(
                title=row.get("title", ""),
                source=row.get("source", "NewsAPI"),
                url=row.get("url", ""),
                published_at=row.get("published", ""),
            )
            for row in rows
            if row.get("title")
        ]


class GNewsVendor(VendorClient):
    NAME = "gnews"
    KEY_ENV = "GNEWS_API_KEY"
    DEFAULT_RPM = 10  # 100/day free

    BASE = "https://gnews.io/api/v4"

    def get_news(self, query: str, company_name: str = "", limit: int = 12) -> Optional[list[NewsHeadline]]:
        term = f'"{query}" OR "{company_name}"' if company_name else f'"{query}" stock'
        data = self._get_json(
            f"{self.BASE}/search",
            params={
                "q": term, "lang": "en", "country": "us",
                "max": min(limit, 25), "sortby": "publishedAt",
                "from": (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "apikey": self.api_key,
            },
        )
        articles = data.get("articles") or []
        headlines = [
            NewsHeadline(
                title=article.get("title", "").strip(),
                source=(article.get("source") or {}).get("name", "GNews"),
                url=article.get("url", ""),
                published_at=article.get("publishedAt", ""),
                summary=(article.get("description") or "")[:280],
            )
            for article in articles
            if article.get("title")
        ]
        return headlines or None


class YahooRssVendor(VendorClient):
    """Keyless ticker headlines via Yahoo Finance RSS — the reliable anchor."""

    NAME = "yahoo_rss"
    KEY_ENV = None
    DEFAULT_RPM = 30

    URL_TEMPLATE = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"

    def get_news(self, query: str, company_name: str = "", limit: int = 12) -> Optional[list[NewsHeadline]]:
        from bs4 import BeautifulSoup

        def _fetch():
            response = self._session.get(
                self.URL_TEMPLATE.format(symbol=query.upper()),
                timeout=self.TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.content

        content = self.timed_call(_fetch)
        soup = BeautifulSoup(content, "xml")
        headlines = []
        for item in soup.find_all("item", limit=limit):
            title_tag = item.find("title")
            if not title_tag or not title_tag.text:
                continue
            link_tag = item.find("link")
            date_tag = item.find("pubDate")
            headlines.append(NewsHeadline(
                title=title_tag.text.strip(),
                source="Yahoo Finance",
                url=(link_tag.text.strip() if link_tag and link_tag.text else ""),
                published_at=(date_tag.text.strip() if date_tag and date_tag.text else ""),
            ))
        return headlines or None
