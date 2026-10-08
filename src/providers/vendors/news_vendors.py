"""
News vendors: NewsAPI (delegates to the existing client), GNews, Yahoo RSS
(keyless anchor).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Optional

from src.providers.base import FailureClass, VendorClient, VendorError, read_rows
from src.providers.schemas import NewsHeadline


def _text(value, default: str = "") -> str:
    """A text field, or TypeError when the vendor sent a container.

    Absent (`null`, `false`) is the default and a scalar is its text, but
    `str(value)` would turn a list or a dict into a headline's worth of
    brackets; refusing it makes the article unreadable, which is what it is.
    """
    if value is None or value is False:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    raise TypeError(f"expected text, got {type(value).__name__}")


def _name_of(source, default: str) -> str:
    """A publisher name from `{"name": ...}`, a bare string, or the default."""
    if isinstance(source, dict):
        name = source.get("name")
        return name if isinstance(name, str) and name.strip() else default
    return source if isinstance(source, str) and source.strip() else default


def _headlines_or_failure(vendor: VendorClient, operation: str, rows, make) -> Optional[list[NewsHeadline]]:
    """Read every article; one unreadable article costs that article only.

    If *nothing* in a non-empty reply could be read, that is a parse failure
    and not "no news": the vendor answered and we could not understand it.
    """
    headlines, unreadable = read_rows(rows, make)
    vendor._note_unreadable(operation, unreadable)
    if not headlines and unreadable:
        raise VendorError(
            f"{unreadable} article(s) returned, none readable",
            transient=False, failure_class=FailureClass.PARSE,
        )
    return headlines or None


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
            expect=dict,
        )

        def make_headline(article: dict) -> Optional[NewsHeadline]:
            title = _text(article.get("title")).strip()

            if not title or title == "[Removed]" or len(title) < 10:
                return None

            source = _name_of(article.get("source"), "NewsAPI")

            if " - " in title:
                title_part, suffix = title.rsplit(" - ", 1)
                title = title_part.strip()

                if not source or source == "NewsAPI":
                    source = suffix.strip()

            return NewsHeadline(
                title=title,
                source=source,
                url=_text(article.get("url")),
                published_at=_text(article.get("publishedAt")),
                summary=_text(article.get("description"))[:280],
                image_url=_text(article.get("urlToImage")),
                author=_text(article.get("author")),
            )

        articles = data.get("articles")
        return _headlines_or_failure(
            self, "news", articles[:limit] if isinstance(articles, list) else articles, make_headline,
        )


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
            expect=dict,
        )

        def make_headline(article: dict) -> Optional[NewsHeadline]:
            title = _text(article.get("title")).strip()
            if not title:
                return None
            return NewsHeadline(
                title=title,
                source=_name_of(article.get("source"), "GNews"),
                url=_text(article.get("url")),
                published_at=_text(article.get("publishedAt")),
                summary=_text(article.get("description"))[:280],
                image_url=_text(article.get("image")),
            )

        return _headlines_or_failure(self, "news", data.get("articles") or [], make_headline)


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
            expect=dict,
        )
        rows = data.get("data")
        if not isinstance(rows, list):
            return None

        def make_headline(article: dict) -> Optional[NewsHeadline]:
            title = _text(article.get("title")).strip()
            if not title:
                return None
            entities = [entity for entity in (article.get("entities") or [])
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
            return NewsHeadline(
                title=title,
                source=_text(article.get("source")) or "Marketaux",
                url=_text(article.get("url")),
                published_at=_text(article.get("published_at")),
                summary=_text(article.get("description"))[:280],
                image_url=_text(article.get("image_url")),
                tickers=[str(entity.get("symbol")).upper() for entity in entities
                         if entity.get("symbol")][:8],
                sentiment_score=score,
                sentiment_source=self.NAME if score is not None else None,
            )

        return _headlines_or_failure(self, "news", rows[:limit], make_headline)


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
        if soup.find(["rss", "feed", "channel"]) is None:
            # HTTP 200 carrying something that is not a feed (a consent page, a
            # captcha, an empty body). It has no items for the same reason a
            # quiet day has none, and the two must not read alike: an empty
            # channel is "no headlines", this is "we were not given the feed".
            raise ValueError("reply is not an RSS or Atom feed")
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
