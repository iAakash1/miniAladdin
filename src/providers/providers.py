"""
The five provider facades. Each exposes one clean, vendor-agnostic
interface; chain order, fallback, caching, dedupe, confidence and health
all live below this line. Callers never learn which vendor answered.
"""

from __future__ import annotations

from typing import Optional

from src.providers.cache import CacheBackend
from src.providers.dedupe import SingleFlight
from src.providers.orchestrator import ChainLink, FallbackChain
from src.providers.schemas import (
    AnalystTargets,
    CompanyProfile,
    FundamentalsData,
    MacroSnapshot,
    NewsHeadline,
    PriceQuote,
    PriceSeries,
    ProviderResult,
    SearchResult,
    StreetData,
)
from src.providers.vendors.data_vendors import AlphaVantageVendor, FredVendor
from src.providers.vendors.market_vendors import (
    FinnhubVendor,
    FMPVendor,
    MarketStackVendor,
    PolygonVendor,
    TwelveDataVendor,
    YFinanceVendor,
)
from src.providers.vendors.news_vendors import GNewsVendor, NewsApiVendor, YahooRssVendor
from src.providers.vendors.search_vendors import ExaVendor, TavilyVendor


class MarketDataProvider:
    """get_price / get_prices / get_series — quotes and OHLCV history."""

    PRICE_TTL = 60.0
    SERIES_TTL = 300.0

    def __init__(self, cache: CacheBackend, flight: SingleFlight):
        self.polygon = PolygonVendor()
        self.finnhub = FinnhubVendor()
        self.twelvedata = TwelveDataVendor()
        self.fmp = FMPVendor()
        self.marketstack = MarketStackVendor()
        self.yfinance = YFinanceVendor()
        self._price_chain = FallbackChain[PriceQuote]("market.price", cache, flight, self.PRICE_TTL)
        self._series_chain = FallbackChain[PriceSeries]("market.series", cache, flight, self.SERIES_TTL)

    @property
    def vendors(self):
        return [self.polygon, self.finnhub, self.twelvedata, self.fmp, self.marketstack, self.yfinance]

    def get_price(self, symbol: str, validate: bool = True) -> ProviderResult[PriceQuote]:
        symbol = symbol.upper()
        links = [
            ChainLink(self.polygon, lambda: self.polygon.get_price(symbol)),
            ChainLink(self.finnhub, lambda: self.finnhub.get_price(symbol)),
            ChainLink(self.twelvedata, lambda: self.twelvedata.get_price(symbol)),
            ChainLink(self.fmp, lambda: self.fmp.get_price(symbol)),
            ChainLink(self.marketstack, lambda: self.marketstack.get_price(symbol)),
            ChainLink(self.yfinance, lambda: self.yfinance.get_price(symbol)),
        ]
        return self._price_chain.execute(
            f"price:{symbol}",
            links,
            cross_validate=(lambda quote: quote.price) if validate else None,
        )

    def get_prices(self, symbols: list[str]) -> dict[str, ProviderResult[PriceQuote]]:
        """Batched quotes: cache + single-flight make repeats free; symbols
        are resolved individually so per-vendor availability still applies."""
        return {symbol.upper(): self.get_price(symbol, validate=False) for symbol in symbols}

    def get_series(self, symbol: str, period: str = "3mo") -> ProviderResult[PriceSeries]:
        symbol = symbol.upper()
        links = [
            ChainLink(self.polygon, lambda: self.polygon.get_series(symbol, period)),
            ChainLink(self.twelvedata, lambda: self.twelvedata.get_series(symbol, period)),
            ChainLink(self.fmp, lambda: self.fmp.get_series(symbol, period)),
            ChainLink(self.marketstack, lambda: self.marketstack.get_series(symbol, period)),
            ChainLink(self.yfinance, lambda: self.yfinance.get_series(symbol, period)),
        ]
        return self._series_chain.execute(f"series:{symbol}:{period}", links)


class FundamentalsProvider:
    """get_company / get_fundamentals / get_analyst_targets."""

    TTL = 3600.0  # fundamentals move slowly

    def __init__(self, cache: CacheBackend, flight: SingleFlight,
                 market: Optional[MarketDataProvider] = None):
        # Reuse market vendors where they overlap so stats/ratelimits are shared.
        self.alpha_vantage = AlphaVantageVendor()
        self.finnhub = market.finnhub if market else FinnhubVendor()
        self.fmp = market.fmp if market else FMPVendor()
        self._company_chain = FallbackChain[CompanyProfile]("fund.company", cache, flight, self.TTL)
        self._fund_chain = FallbackChain[FundamentalsData]("fund.metrics", cache, flight, self.TTL)
        self._target_chain = FallbackChain[AnalystTargets]("fund.targets", cache, flight, self.TTL)
        self._street_chain = FallbackChain[StreetData]("fund.street", cache, flight, 21600.0)

    @property
    def vendors(self):
        return [self.alpha_vantage, self.finnhub, self.fmp]

    def get_company(self, symbol: str) -> ProviderResult[CompanyProfile]:
        symbol = symbol.upper()
        links = [
            ChainLink(self.finnhub, lambda: self.finnhub.get_company(symbol)),
            ChainLink(self.fmp, lambda: self.fmp.get_company(symbol)),
            ChainLink(self.alpha_vantage,
                      lambda: (self.alpha_vantage.get_fundamentals(symbol) or FundamentalsData(symbol=symbol)).profile),
        ]
        return self._company_chain.execute(f"company:{symbol}", links)

    def get_fundamentals(self, symbol: str) -> ProviderResult[FundamentalsData]:
        symbol = symbol.upper()
        links = [
            ChainLink(self.alpha_vantage, lambda: self.alpha_vantage.get_fundamentals(symbol)),
            ChainLink(self.finnhub, lambda: self.finnhub.get_fundamentals(symbol)),
            ChainLink(self.fmp, lambda: self.fmp.get_fundamentals(symbol)),
        ]
        return self._fund_chain.execute(f"fundamentals:{symbol}", links)

    def get_analyst_targets(self, symbol: str) -> ProviderResult[AnalystTargets]:
        symbol = symbol.upper()
        links = [
            ChainLink(self.alpha_vantage, lambda: self.alpha_vantage.get_analyst_targets(symbol)),
            ChainLink(self.finnhub, lambda: self.finnhub.get_analyst_targets(symbol)),
        ]
        return self._target_chain.execute(f"targets:{symbol}", links)

    def get_street(self, symbol: str) -> ProviderResult[StreetData]:
        """v4.5: recommendation trends, EPS surprises, insider sentiment.
        Finnhub-only (the sole vendor with these on a free tier); 6h TTL —
        this data moves on a monthly cadence."""
        symbol = symbol.upper()
        links = [ChainLink(self.finnhub, lambda: self.finnhub.get_street(symbol))]
        return self._street_chain.execute(f"street:{symbol}", links)


class NewsProvider:
    """get_news — ticker headlines, newest first, deduplicated by title."""

    TTL = 300.0

    def __init__(self, cache: CacheBackend, flight: SingleFlight):
        self.newsapi = NewsApiVendor()
        self.gnews = GNewsVendor()
        self.yahoo_rss = YahooRssVendor()
        self.tavily = TavilyVendor()
        self._chain = FallbackChain[list[NewsHeadline]]("news.headlines", cache, flight, self.TTL)

    @property
    def vendors(self):
        return [self.newsapi, self.gnews, self.yahoo_rss, self.tavily]

    def get_news(self, symbol: str, company_name: str = "", limit: int = 12) -> ProviderResult[list[NewsHeadline]]:
        symbol = symbol.upper()
        links = [
            ChainLink(self.newsapi, lambda: self.newsapi.get_news(symbol, company_name, limit)),
            ChainLink(self.gnews, lambda: self.gnews.get_news(symbol, company_name, limit)),
            ChainLink(self.yahoo_rss, lambda: self.yahoo_rss.get_news(symbol, company_name, limit)),
            ChainLink(self.tavily, lambda: self.tavily.get_news(symbol, company_name, limit)),
        ]
        result = self._chain.execute(f"news:{symbol}:{limit}", links)
        if result.data:
            seen: set[str] = set()
            deduped = []
            for headline in result.data:
                key = headline.title.lower().strip()[:80]
                if key and key not in seen:
                    seen.add(key)
                    deduped.append(headline)
            result = result.model_copy(update={"data": deduped[:limit]})
        return result


class MacroProvider:
    """get_macro / get_series_snapshot — FRED behind cache; callers keep demo fallbacks."""

    TTL = 900.0        # headline snapshot
    SERIES_TTL = 1800.0  # individual series move at most daily

    def __init__(self, cache: CacheBackend, flight: SingleFlight):
        self.fred = FredVendor()
        self._chain = FallbackChain[MacroSnapshot]("macro.snapshot", cache, flight, self.TTL)
        self._series_chain = FallbackChain[list]("macro.series", cache, flight, self.SERIES_TTL)

    @property
    def vendors(self):
        return [self.fred]

    def get_macro(self) -> ProviderResult[MacroSnapshot]:
        return self._chain.execute(
            "macro:snapshot",
            [ChainLink(self.fred, self.fred.get_macro)],
        )

    def get_series_snapshot(self, series_id: str, count: int = 8) -> ProviderResult[list]:
        """Last N (date, value) pairs of any FRED series, cached per series."""
        return self._series_chain.execute(
            f"macro:series:{series_id}:{count}",
            [ChainLink(self.fred, lambda: self.fred.get_observations(series_id, count))],
        )


class SearchProvider:
    """search — research context via Tavily, falling back to Exa."""

    TTL = 600.0

    def __init__(self, cache: CacheBackend, flight: SingleFlight,
                 news: Optional[NewsProvider] = None):
        self.tavily = news.tavily if news else TavilyVendor()
        self.exa = ExaVendor()
        self._chain = FallbackChain[list[SearchResult]]("search.web", cache, flight, self.TTL)

    @property
    def vendors(self):
        return [self.tavily, self.exa]

    def search(self, query: str, limit: int = 8) -> ProviderResult[list[SearchResult]]:
        normalized = query.strip()
        links = [
            ChainLink(self.tavily, lambda: self.tavily.search(normalized, limit)),
            ChainLink(self.exa, lambda: self.exa.search(normalized, limit)),
        ]
        return self._chain.execute(f"search:{normalized.lower()}:{limit}", links)
