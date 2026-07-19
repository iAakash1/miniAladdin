"""
Research providers — one class per source, all behind ResearchProvider.

Each wraps an existing vendor adapter (rate limiting, retries, cooldown,
health stats already live there) and normalizes into ResearchHit. Adding a
provider means writing one class here and naming it in the registry order.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from src.providers.base import VendorClient
from src.providers.vendors.apify_vendor import ApifyVendor
from src.providers.vendors.news_vendors import YahooRssVendor
from src.providers.vendors.search_vendors import ExaVendor, TavilyVendor
from src.services.research.base import (
    ProviderCapabilities,
    ProviderHealth,
    ResearchHit,
    ResearchProvider,
)

logger = logging.getLogger(__name__)


class _BraveVendor(VendorClient):
    """Brave Search API — independent index, generous free tier (2k/mo)."""

    NAME = "brave"
    KEY_ENV = "BRAVE_API_KEY"
    DEFAULT_RPM = 20  # free tier allows ~1 req/s

    BASE = "https://api.search.brave.com/res/v1"

    def web_search(self, query: str, limit: int) -> list[dict[str, Any]]:
        data = self._get_json(
            f"{self.BASE}/web/search",
            params={"q": query, "count": min(limit, 20), "freshness": "py"},
            headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"},
        )
        return ((data or {}).get("web") or {}).get("results") or []

    def news_search(self, query: str, limit: int) -> list[dict[str, Any]]:
        data = self._get_json(
            f"{self.BASE}/news/search",
            params={"q": query, "count": min(limit, 20)},
            headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"},
        )
        return (data or {}).get("results") or []


class BraveProvider(ResearchProvider):
    name = "brave"

    def __init__(self) -> None:
        self._vendor = _BraveVendor()

    def is_configured(self) -> bool:
        return self._vendor.available

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(search=True, company_research=True, news=True)

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            name=self.name, available=self._vendor.available,
            configured=self._vendor.available, stats=self._vendor.health_snapshot(),
        )

    def search(self, query: str, limit: int = 6) -> list[ResearchHit]:
        if not self._vendor.available:
            return []
        rows = self._vendor.web_search(query, limit)
        return [
            ResearchHit(
                url=str(row.get("url", "")),
                title=str(row.get("title", "")),
                snippet=str(row.get("description", "")),
                published_at=(row.get("page_age") or None),
                provider=self.name,
            )
            for row in rows
            if row.get("url")
        ][:limit]


class TavilyProvider(ResearchProvider):
    """AI-native search: returns extracted content, not just snippets."""

    name = "tavily"

    def __init__(self) -> None:
        self._vendor = TavilyVendor()

    def is_configured(self) -> bool:
        return self._vendor.available

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(search=True, company_research=True,
                                    news=True, extracts_content=True)

    def health(self) -> ProviderHealth:
        return ProviderHealth(name=self.name, available=self._vendor.available,
                              configured=self._vendor.available, stats=self._vendor.health_snapshot())

    def search(self, query: str, limit: int = 6) -> list[ResearchHit]:
        if not self._vendor.available:
            return []
        results = self._vendor.search(query, limit=limit) or []
        return [
            ResearchHit(url=r.url, title=r.title, snippet=getattr(r, "snippet", "") or "",
                        provider=self.name)
            for r in results if getattr(r, "url", "")
        ][:limit]


class ExaProvider(ResearchProvider):
    """Semantic search — finds conceptually related material, not keywords."""

    name = "exa"

    def __init__(self) -> None:
        self._vendor = ExaVendor()

    def is_configured(self) -> bool:
        return self._vendor.available

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(search=True, company_research=True, semantic=True)

    def health(self) -> ProviderHealth:
        return ProviderHealth(name=self.name, available=self._vendor.available,
                              configured=self._vendor.available, stats=self._vendor.health_snapshot())

    def search(self, query: str, limit: int = 6) -> list[ResearchHit]:
        if not self._vendor.available:
            return []
        results = self._vendor.search(query, limit=limit) or []
        return [
            ResearchHit(url=r.url, title=r.title, snippet=getattr(r, "snippet", "") or "",
                        provider=self.name)
            for r in results if getattr(r, "url", "")
        ][:limit]


class NewsProvider(ResearchProvider):
    """Yahoo Finance RSS — keyless, always available, ticker-scoped news."""

    name = "news"

    def __init__(self) -> None:
        self._vendor = YahooRssVendor()

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(search=False, company_research=True, news=True)

    def health(self) -> ProviderHealth:
        return ProviderHealth(name=self.name, available=True, configured=True,
                              stats=self._vendor.health_snapshot())

    def search(self, query: str, limit: int = 6) -> list[ResearchHit]:
        # RSS is ticker-scoped, not a general search index; the first token
        # of the query is treated as the symbol.
        symbol = (query.strip().split() or [""])[0].upper()
        return self._hits_for(symbol, limit)

    def research_company(self, symbol: str, company_name: str = "", question: str = ""):
        return self.normalize(symbol, self._hits_for(symbol.upper(), 6))

    def _hits_for(self, symbol: str, limit: int) -> list[ResearchHit]:
        if not symbol.isalpha():
            return []
        try:
            headlines = self._vendor.get_news(symbol, "", limit=limit) or []
        except Exception:  # noqa: BLE001 — optional like every research source
            return []
        return [
            ResearchHit(url=h.url, title=h.title, snippet=h.title,
                        published_at=h.published_at, provider=self.name)
            for h in headlines if getattr(h, "url", "")
        ][:limit]


class ApifyProvider(ResearchProvider):
    """Kept for unique value (full page extraction); never a dependency."""

    name = "apify"

    def __init__(self) -> None:
        self._vendor = ApifyVendor()

    def is_configured(self) -> bool:
        return self._vendor.available

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(search=True, company_research=True,
                                    extracts_content=True)

    def health(self) -> ProviderHealth:
        return ProviderHealth(name=self.name, available=self._vendor.available,
                              configured=self._vendor.available, stats=self._vendor.health_snapshot())

    def search(self, query: str, limit: int = 6) -> list[ResearchHit]:
        if not self._vendor.available:
            return []
        rows = self._vendor.search(query, limit=limit)
        return [
            ResearchHit(url=row["url"], title=row.get("title", ""),
                        snippet=row.get("snippet", ""), provider=self.name)
            for row in rows if row.get("url")
        ][:limit]
