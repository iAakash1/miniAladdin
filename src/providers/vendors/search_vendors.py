"""
Search vendors: Tavily and Exa. Used by SearchProvider and as the deepest
news fallback (news-topic search when every headline vendor is down).
"""

from __future__ import annotations

from typing import Any, Optional

from src.providers.base import FailureClass, VendorClient, VendorError, read_rows
from src.providers.schemas import NewsHeadline, SearchResult


def _results_or_failure(vendor: VendorClient, rows: Any, make) -> Optional[list[SearchResult]]:
    """Read every hit; one unreadable hit costs that hit only."""
    parsed, unreadable = read_rows(rows, make)
    vendor._note_unreadable("search", unreadable)
    if not parsed and unreadable:
        raise VendorError(
            f"{unreadable} result(s) returned, none readable",
            transient=False, failure_class=FailureClass.PARSE,
        )
    return parsed or None


def _score(value: Any) -> Optional[float]:
    """A relevance score, or None. Booleans and strings are not scores."""
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


class TavilyVendor(VendorClient):
    NAME = "tavily"
    KEY_ENV = "TAVILY_API_KEY"
    DEFAULT_RPM = 20

    BASE = "https://api.tavily.com"

    def search(
        self,
        query: str,
        limit: int = 8,
        topic: str = "general",
        search_depth: str = "basic",
        time_range: Optional[str] = None,
        include_raw_content: bool = False,
    ) -> Optional[list[SearchResult]]:
        """Tavily search. Auth is `Authorization: Bearer` — the api_key-in-body
        form is legacy. search_depth basic|advanced|fast|ultra-fast;
        topic general|news; time_range day|week|month|year."""
        body: dict[str, Any] = {
            "query": query,
            "topic": topic,
            "search_depth": search_depth,
            "max_results": min(limit, 20),
            "include_answer": False,
        }
        if time_range:
            body["time_range"] = time_range
        if include_raw_content:
            body["include_raw_content"] = "text"
        data = self._post_json(
            f"{self.BASE}/search",
            json_body=body,
            headers={"Authorization": f"Bearer {self.api_key}"},
            expect=dict,
        )

        def make_result(row: dict) -> Optional[SearchResult]:
            if not row.get("title") or not row.get("url"):
                return None
            return SearchResult(
                title=str(row["title"]),
                url=str(row["url"]),
                snippet=str(row.get("raw_content") or row.get("content") or "")[:600],
                published_at=str(row.get("published_date") or ""),
                score=_score(row.get("score")),
            )

        return _results_or_failure(self, data.get("results") or [], make_result)

    def get_news(self, query: str, company_name: str = "", limit: int = 8) -> Optional[list[NewsHeadline]]:
        term = f"{company_name or query} stock news"
        results = self.search(term, limit=limit, topic="news")
        if not results:
            return None
        return [
            NewsHeadline(
                title=row.title, source="Tavily", url=row.url,
                published_at=row.published_at, summary=row.snippet[:280],
                # Tavily's own match score for the query. Attributed rather
                # than folded into the sentiment relevance field — a search
                # rank and a sentiment model's ticker-relevance judgement are
                # incomparable scales that happen to share a name.
                relevance=row.score,
                relevance_source=self.NAME,
            )
            for row in results
        ]


class ExaVendor(VendorClient):
    NAME = "exa"
    KEY_ENV = "EXA_API_KEY"
    DEFAULT_RPM = 20

    BASE = "https://api.exa.ai"

    def search(
        self,
        query: str,
        limit: int = 8,
        category: Optional[str] = None,
    ) -> Optional[list[SearchResult]]:
        """Exa semantic search. `category` narrows retrieval by kind
        (company | research paper | news | financial report | people),
        which is what makes Exa useful for discovery rather than lookup."""
        body: dict[str, Any] = {
            "query": query,
            "numResults": min(limit, 20),
            "type": "auto",
            "contents": {
                "text": {"maxCharacters": 600},
                "highlights": True,
            },
        }
        if category:
            body["category"] = category
        data = self._post_json(
            f"{self.BASE}/search",
            json_body=body,
            headers={"x-api-key": self.api_key},
            expect=dict,
        )

        def make_result(row: dict) -> Optional[SearchResult]:
            if not row.get("url"):
                return None
            return SearchResult(
                title=str(row.get("title") or ""),
                url=str(row["url"]),
                snippet=((row.get("text") or "") if isinstance(row.get("text"), str) else "")[:400],
                published_at=str(row.get("publishedDate") or ""),
                score=_score(row.get("score")),
            )

        return _results_or_failure(self, data.get("results") or [], make_result)
