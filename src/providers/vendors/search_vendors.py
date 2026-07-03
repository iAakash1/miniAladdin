"""
Search vendors: Tavily and Exa. Used by SearchProvider and as the deepest
news fallback (news-topic search when every headline vendor is down).
"""

from __future__ import annotations

from typing import Optional

from src.providers.base import VendorClient
from src.providers.schemas import NewsHeadline, SearchResult


class TavilyVendor(VendorClient):
    NAME = "tavily"
    KEY_ENV = "TAVILY_API_KEY"
    DEFAULT_RPM = 20

    BASE = "https://api.tavily.com"

    def search(self, query: str, limit: int = 8, topic: str = "general") -> Optional[list[SearchResult]]:
        data = self._post_json(
            f"{self.BASE}/search",
            json_body={
                "api_key": self.api_key,
                "query": query,
                "topic": topic,
                "max_results": min(limit, 20),
                "include_answer": False,
            },
        )
        results = data.get("results") or []
        parsed = [
            SearchResult(
                title=row.get("title", ""),
                url=row.get("url", ""),
                snippet=(row.get("content") or "")[:400],
                published_at=row.get("published_date", "") or "",
                score=row.get("score"),
            )
            for row in results
            if row.get("title") and row.get("url")
        ]
        return parsed or None

    def get_news(self, query: str, company_name: str = "", limit: int = 8) -> Optional[list[NewsHeadline]]:
        term = f"{company_name or query} stock news"
        results = self.search(term, limit=limit, topic="news")
        if not results:
            return None
        return [
            NewsHeadline(
                title=row.title, source="Tavily", url=row.url,
                published_at=row.published_at, summary=row.snippet[:280],
            )
            for row in results
        ]


class ExaVendor(VendorClient):
    NAME = "exa"
    KEY_ENV = "EXA_API_KEY"
    DEFAULT_RPM = 20

    BASE = "https://api.exa.ai"

    def search(self, query: str, limit: int = 8) -> Optional[list[SearchResult]]:
        data = self._post_json(
            f"{self.BASE}/search",
            json_body={
                "query": query,
                "numResults": min(limit, 20),
                "type": "auto",
                "contents": {"text": {"maxCharacters": 400}},
            },
            headers={"x-api-key": self.api_key},
        )
        results = data.get("results") or []
        parsed = [
            SearchResult(
                title=row.get("title") or "",
                url=row.get("url", ""),
                snippet=((row.get("text") or "") if isinstance(row.get("text"), str) else "")[:400],
                published_at=row.get("publishedDate", "") or "",
                score=row.get("score"),
            )
            for row in results
            if row.get("url")
        ]
        return parsed or None
