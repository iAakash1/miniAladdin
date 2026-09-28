"""
News vendors: NewsAPI (delegates to the existing client), GNews, Yahoo RSS
(keyless anchor).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Optional

from src.providers.base import VendorClient
from src.providers.schemas import NewsHeadline


class NewsApiVendor(VendorClient):
    """NewsAPI adapter using the shared vendor transport and health contract."""

    NAME = "newsapi"
    KEY_ENV = "NEWSAPI_KEY"
    DEFAULT_RPM = 10  # 100/day free
    BASE = "https://newsapi.org/v2/everything"

    def get_news(
        self,
        query: str,
        company_name: str = "",
        limit: int = 12,
    ) -> Optional[list[NewsHeadline]]:
        term = (
            f'("{query}" OR "{company_name}") stock'
            if company_name
            else f'"{query}" stock'
        )

        data = self._get_json(
            self.BASE,
            params={
                "q": term,
                "from": (
                    datetime.now(timezone.utc) - timedelta(days=7)
                ).strftime("%Y-%m-%dT%H:%M:%S"),
                "sortBy": "publishedAt",
                "language": "en",
                "pageSize": min(limit, 20),
            },
            headers={"X-Api-Key": self.api_key},
            operation="news",
        )

        headlines: list[NewsHeadline] = []

        for article in (data.get("articles") or [])[:limit]:
            title = str(article.get("title") or "").strip()

            if not title or title == "[Removed]" or len(title) < 10:
                continue

            source = str(
                (article.get("source") or {}).get("name") or "NewsAPI"
            )

            if " - " in title:
                title_part, suffix = title.rsplit(" - ", 1)
                title = title_part.strip()

                if not source or source == "NewsAPI":
                    source = suffix.strip()

            headlines.append(
                NewsHeadline(
                    title=title,
                    source=source,
                    url=str(article.get("url") or ""),
                    published_at=str(article.get("publishedAt") or ""),
                    summary=str(article.get("description") or "")[:280],
                    image_url=str(article.get("urlToImage") or ""),
                    author=str(article.get("author") or ""),
                )
            )

        return headlines or None


class GNewsVendor(VendorClient):
    NAME = "gnews"
    KEY_ENV = "GNEWS_API_KEY"
    DEFAULT_RPM = 10  # 100/day free

    BASE = "https://gnews.io/api/v4"

    def get_news(self, query: str, company_name: str = "", limit: int = 12) -> Optional[list[NewsHeadline]]:
        """Ticker + company-name search.

        Both terms rather than the ticker alone: three-letter tickers collide
        with ordinary words ("V", "ALL", "IT"), and searching the ticker on
        its own returns articles about visas and everything else. Kept to one
        request with an OR rather than fanning out over several phrasings —
        the free tier is 100 calls a day, and a second query would halve the
        number of companies a user can research.

        `image` and `content` were both in the response and both discarded;
        the image is the publisher's own photograph for the story, which is
        the one image the product must never replace with a stock photo.
        """
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
                image_url=str(article.get("image") or ""),
            )
            for article in articles
            if article.get("title")
        ]
        return headlines or None


class MarketauxVendor(VendorClient):
    """Entity-filtered financial headlines, with sentiment kept vendor-attributed."""

    NAME = "marketaux"
    KEY_ENV = "MARKETAUX_API_KEY"
    DEFAULT_RPM = 5
    BASE = "https://api.marketaux.com/v1/news/all"

    def get_news(self, query: str, company_name: str = "", limit: int = 12) -> Optional[list[NewsHeadline]]:
        symbol = query.strip().upper()
        if not symbol:
            return None
        data = self._get_json(
            self.BASE,
            params={
                "symbols": symbol,
                "filter_entities": "true",
                "language": "en",
                "limit": min(max(limit, 1), 20),
                "api_token": self.api_key,
            },
            operation="news",
        )
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            return None
        headlines: list[NewsHeadline] = []
        for article in data["data"][:limit]:
            if not isinstance(article, dict):
                continue
            title = str(article.get("title") or "").strip()
            if not title:
                continue
            entities = [entity for entity in article.get("entities", [])
                        if isinstance(entity, dict)]
            matched = next((entity for entity in entities
                            if str(entity.get("symbol") or "").upper() == symbol), None)
            score = None
            if matched is not None:
                try:
                    score = float(matched["sentiment_score"])
                    if not math.isfinite(score) or not -1 <= score <= 1:
                        score = None
                except (KeyError, TypeError, ValueError):
                    pass
            headlines.append(NewsHeadline(
                title=title,
                source=str(article.get("source") or "Marketaux"),
                url=str(article.get("url") or ""),
                published_at=str(article.get("published_at") or ""),
                summary=str(article.get("description") or "")[:280],
                image_url=str(article.get("image_url") or ""),
                tickers=[str(entity.get("symbol")).upper() for entity in entities
                         if entity.get("symbol")][:8],
                sentiment_score=score,
                sentiment_source=self.NAME if score is not None else None,
            ))
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
            # Yahoo's feed carries `media:content` and `description` on most
            # items; both were being dropped. The image is the publisher's own
            # photograph for the story — the one image that must never be
            # replaced by a stock library, and until now the only news vendor
            # supplying one was GNews.
            media = item.find("media:content") or item.find("content")
            image = ""
            if media is not None:
                candidate = media.get("url") or ""
                # Feeds occasionally point `media:content` at a video or an
                # audio enclosure; only take it when it is declared an image
                # or has an image extension.
                declared = (media.get("medium") or media.get("type") or "").lower()
                if candidate and ("image" in declared or candidate.lower().split("?")[0].endswith(
                    (".jpg", ".jpeg", ".png", ".webp", ".gif")
                )):
                    image = candidate
            desc_tag = item.find("description")
            headlines.append(NewsHeadline(
                title=title_tag.text.strip(),
                source="Yahoo Finance",
                url=(link_tag.text.strip() if link_tag and link_tag.text else ""),
                published_at=(date_tag.text.strip() if date_tag and date_tag.text else ""),
                summary=(desc_tag.text.strip()[:280] if desc_tag and desc_tag.text else ""),
                image_url=image,
            ))
        return headlines or None
