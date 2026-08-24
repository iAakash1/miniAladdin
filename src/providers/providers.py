"""
## Why FallbackChain and the evidence fabric both exist

Every provider below keeps *both* a chain and a fan-out, and an audit that
sees `FallbackChain` and assumes it is a leftover is reading it wrong. They
serve different questions:

* The **chain** serves a value. One answer, fast, cached, single-flighted,
  with a defined degradation path. The scoring engine, the quotes endpoint
  and the portfolio series loader all need exactly this — a price, now, not a
  study of who agrees about it. Running a six-vendor fan-out on the batch
  quote path would multiply a watchlist refresh by six for no gain, because
  the caller wants one number.
* The **fabric** builds evidence. Every capable vendor is asked, all answers
  are kept, failures are retained and classified, and the interesting output
  is the agreement rather than the value. Research surfaces and the
  provenance ledger use this.

So the rule is not "fan-out everywhere". It is: fan out where the *question*
is about corroboration, and chain where the question is about a value. Both
draw on the same vendor objects, the same rate limiters and the same cache,
so a fan-out that follows a chain for the same symbol is largely free.

Single-link chains are deliberate too where they remain: they exist so a
second vendor can be added at one line without changing any call site, and
the corresponding capability is still fanned out for the evidence path.

The provider facades. Each exposes one clean, vendor-agnostic interface;
chain order, fallback, caching, dedupe, confidence and health all live below
this line. Callers of the chain never learn which vendor answered; callers of
the fabric are told exactly who did.
"""

from __future__ import annotations

from typing import Optional

from src.providers.cache import CacheBackend
from src.providers.dedupe import SingleFlight
from src.providers import fabric
from src.providers.fabric import Evidence
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
from src.providers.vendors.market_vendors import (  # noqa: F401 — PolygonVendor/YFinanceVendor used standalone
    FinnhubVendor,
    FMPVendor,
    MarketStackVendor,
    PolygonVendor,
    TwelveDataVendor,
    YFinanceVendor,
)
from src.providers.vendors.news_vendors import GNewsVendor, NewsApiVendor, YahooRssVendor
from src.providers.vendors.search_vendors import ExaVendor, TavilyVendor
from src.providers.vendors.sec_vendor import SECVendor
from src.providers.vendors.tiingo_vendor import TiingoVendor


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
        # Tiingo is the only vendor here with a real quote — bid, ask, mid and
        # size, not just a close — so it leads the price chain. It is also a
        # split/dividend-adjusted daily source, which matters for the
        # portfolio value curve.
        self.tiingo = TiingoVendor()
        self._price_chain = FallbackChain[PriceQuote]("market.price", cache, flight, self.PRICE_TTL)
        self._series_chain = FallbackChain[PriceSeries]("market.series", cache, flight, self.SERIES_TTL)

    @property
    def vendors(self):
        return [self.tiingo, self.polygon, self.finnhub, self.twelvedata,
                self.fmp, self.marketstack, self.yfinance]

    def get_price(self, symbol: str, validate: bool = True) -> ProviderResult[PriceQuote]:
        symbol = symbol.upper()
        links = [
            ChainLink(self.tiingo, lambda: self.tiingo.get_price(symbol)),
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
            ChainLink(self.tiingo, lambda: self.tiingo.get_series(symbol, period)),
            ChainLink(self.polygon, lambda: self.polygon.get_series(symbol, period)),
            ChainLink(self.twelvedata, lambda: self.twelvedata.get_series(symbol, period)),
            ChainLink(self.fmp, lambda: self.fmp.get_series(symbol, period)),
            ChainLink(self.marketstack, lambda: self.marketstack.get_series(symbol, period)),
            ChainLink(self.yfinance, lambda: self.yfinance.get_series(symbol, period)),
        ]
        return self._series_chain.execute(f"series:{symbol}:{period}", links)

    # ── multi-source ─────────────────────────────────────────────────────────

    def quote_evidence(self, symbol: str) -> list[Evidence]:
        """Ask **every** quote-capable vendor, concurrently, and keep them all.

        Distinct from `get_price`, which stops at the first answer. Here the
        interesting output is not the price but the agreement: five vendors
        within a cent of each other is a materially different claim from two
        vendors 3% apart, and the chain cannot express the difference because
        it never asks the other four.
        """
        symbol = symbol.upper()
        return fabric.collect(
            "quote", symbol, self.vendors, lambda v: v.get_price(symbol),
        )

    def series_evidence(self, symbol: str, period: str = "1y") -> list[Evidence]:
        """Every history-capable vendor's series for one symbol."""
        symbol = symbol.upper()
        return fabric.collect(
            "series", symbol, self.vendors, lambda v: v.get_series(symbol, period),
            timeout=20.0,
        )


class FundamentalsProvider:
    """get_company / get_fundamentals / get_analyst_targets."""

    TTL = 3600.0  # fundamentals move slowly

    def __init__(self, cache: CacheBackend, flight: SingleFlight,
                 market: Optional[MarketDataProvider] = None):
        # Reuse market vendors where they overlap so stats/ratelimits are shared.
        self.alpha_vantage = AlphaVantageVendor()
        self.finnhub = market.finnhub if market else FinnhubVendor()
        self.fmp = market.fmp if market else FMPVendor()
        # Reused from the market provider so one Tiingo key means one token
        # bucket — a second instance would give two buckets over one quota and
        # the vendor would 429 while both believed they had headroom.
        self.tiingo = market.tiingo if market else TiingoVendor()
        # Three more profile sources the fabric had no idea existed: Polygon's
        # reference endpoint, yfinance's info payload (keyless, so it answers
        # when every authenticated vendor is rate-limited) and Tiingo's meta.
        # All reused from the market provider so each keeps one token bucket.
        self.polygon = market.polygon if market else PolygonVendor()
        self.yfinance = market.yfinance if market else YFinanceVendor()
        self._company_chain = FallbackChain[CompanyProfile]("fund.company", cache, flight, self.TTL)
        self._fund_chain = FallbackChain[FundamentalsData]("fund.metrics", cache, flight, self.TTL)
        self._target_chain = FallbackChain[AnalystTargets]("fund.targets", cache, flight, self.TTL)
        self._street_chain = FallbackChain[StreetData]("fund.street", cache, flight, 21600.0)

    @property
    def vendors(self):
        return [self.alpha_vantage, self.finnhub, self.fmp, self.tiingo,
                self.polygon, self.yfinance]

    def ownership_evidence(self, symbol: str) -> list[Evidence]:
        """Share count, float, holdings and short interest.

        Only yfinance supplies this today, which is precisely why it is worth
        having: it is keyless, so this is one of the few capabilities that
        answers in every environment including CI. Routed through the fabric
        rather than called directly so that adding a second ownership vendor
        later needs no change here.
        """
        symbol = symbol.upper()
        return fabric.collect(
            "ownership", symbol, self.vendors, lambda v: v.get_ownership(symbol),
        )

    def street_evidence(self, symbol: str) -> list[Evidence]:
        """Recommendation trends, EPS surprises and insider sentiment.

        Only Finnhub implements this today, and it was reached through a
        one-link FallbackChain — which is a chain in name only and, more to
        the point, made the capability invisible to the fabric. Routed here
        so it appears in the provenance roster like every other input, and so
        a second vendor needs no change at this call site.
        """
        symbol = symbol.upper()
        return fabric.collect(
            "street", symbol, self.vendors, lambda v: v.get_street(symbol),
        )

    def target_evidence(self, symbol: str) -> list[Evidence]:
        """Analyst price targets from every vendor that publishes them.

        Distinct from `analyst_evidence`, which returns a whole consensus
        object including the rating distribution; this is the bare target and
        is supplied by vendors that do not carry the distribution. Both are
        kept per-vendor rather than merged — each polls a different analyst
        set, so a median across them is a consensus of no actual group.
        """
        symbol = symbol.upper()
        return fabric.collect(
            "analyst_targets", symbol, self.vendors,
            lambda v: v.get_analyst_targets(symbol),
        )

    def analyst_evidence(self, symbol: str) -> list[Evidence]:
        """Price targets and rating distributions, one entry per vendor.

        Deliberately *not* reconciled into a single consensus. Each vendor
        polls a different set of analysts, so a median across vendors would
        be a consensus of no actual group of people. The readings are kept
        side by side and the UI shows them that way.
        """
        symbol = symbol.upper()
        return fabric.collect(
            "analyst_consensus", symbol, self.vendors,
            lambda v: v.get_analyst_consensus(symbol),
        )

    def profile_evidence(self, symbol: str) -> list[Evidence]:
        """Every profile-capable vendor, concurrently.

        A union rather than a choice, for the same reason as fundamentals: no
        single vendor carries every field. Finnhub has the domain and IPO
        date, Polygon the SIC description and headcount, yfinance the GICS
        sector and the business summary. Picking the "best" vendor would
        discard whichever fields the others uniquely hold.
        """
        symbol = symbol.upper()
        return fabric.collect(
            "company", symbol, self.vendors, lambda v: v.get_company(symbol),
        )

    def statement_evidence(self, symbol: str) -> list[Evidence]:
        """Reported statement figures from every vendor that has them.

        A union, not a choice: no single vendor here covers every line, so
        picking one discards fields only the others have. Tiingo's
        fundamentals are an add-on and answer 403 for unentitled symbols,
        which the fabric records as `not_entitled` rather than as an outage.
        """
        symbol = symbol.upper()
        return fabric.collect(
            "fundamentals", symbol, self.vendors, lambda v: v.get_fundamentals(symbol),
        )

    def get_company(self, symbol: str) -> ProviderResult[CompanyProfile]:
        symbol = symbol.upper()
        links = [
            ChainLink(self.finnhub, lambda: self.finnhub.get_company(symbol)),
            ChainLink(self.polygon, lambda: self.polygon.get_company(symbol)),
            ChainLink(self.yfinance, lambda: self.yfinance.get_company(symbol)),
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


class FilingsProvider:
    """SEC EDGAR — primary-source regulatory evidence.

    Deliberately its own provider rather than a fourth fundamentals vendor.
    Everything in `FundamentalsProvider` is a vendor's *interpretation* of a
    filing — parsed, relabelled, sometimes restated. This is the filing, from
    the regulator, with the date it was actually filed. When a vendor's
    revenue disagrees with the 10-K, the 10-K is not a fourth opinion to
    median against; it is the document the others are describing.

    Keyless, so it is available in every environment including local
    development and CI — which makes it the one fundamentals-adjacent source
    that never answers `not_configured`.
    """

    TTL = 21600.0  # filings appear on a daily cadence at best

    def __init__(self, cache: CacheBackend, flight: SingleFlight):
        self.sec = SECVendor()

    @property
    def vendors(self):
        return [self.sec]

    def filings_evidence(self, symbol: str, limit: int = 12) -> list[Evidence]:
        symbol = symbol.upper()
        return fabric.collect(
            "filings", symbol, self.vendors, lambda v: v.get_filings(symbol, limit) or None,
            timeout=15.0,
        )

    def facts_evidence(self, symbol: str) -> list[Evidence]:
        symbol = symbol.upper()
        return fabric.collect(
            "xbrl_facts", symbol, self.vendors, lambda v: v.get_xbrl_facts(symbol) or None,
            timeout=20.0,
        )


class NewsProvider:
    """get_news — ticker headlines, newest first, deduplicated by title."""

    TTL = 300.0

    def __init__(self, cache: CacheBackend, flight: SingleFlight):
        self.newsapi = NewsApiVendor()
        self.gnews = GNewsVendor()
        self.yahoo_rss = YahooRssVendor()
        self.tavily = TavilyVendor()
        # Tiingo carries tags and a ticker list the other news vendors do not,
        # which the categoriser downstream uses as a prior.
        self.tiingo = TiingoVendor()
        # Alpha Vantage contributes *scored* articles — per-ticker sentiment
        # with a relevance weight, which no other news vendor here produces.
        # It joins the fan-out through `get_news_sentiment`, a separate
        # capability, so vendors without sentiment are never asked for it.
        self.alpha_vantage = AlphaVantageVendor()
        self._chain = FallbackChain[list[NewsHeadline]]("news.headlines", cache, flight, self.TTL)

    @property
    def vendors(self):
        return [self.newsapi, self.gnews, self.yahoo_rss, self.tavily,
                self.tiingo, self.alpha_vantage]

    def news_evidence(self, symbol: str, company_name: str = "", limit: int = 12) -> list[Evidence]:
        """Every news vendor, concurrently — this one genuinely must not fall back.

        News is the clearest case against a fallback chain: five vendors do
        not carry the same stories, so stopping at the first success does not
        get you a faster answer to the same question, it gets you a *smaller*
        answer to a different one. Fanning out and merging is what makes the
        stream complete, and corroboration across vendors is the only
        verification signal a headline feed offers.
        """
        symbol = symbol.upper()

        def fetch(vendor):
            # Tiingo's news is ticker-indexed and takes no company name.
            if getattr(vendor, "NAME", "") == "tiingo":
                return vendor.get_news(symbol, limit)
            return vendor.get_news(symbol, company_name, limit)

        headlines = fabric.collect("news", symbol, self.vendors, fetch)
        # Scored articles are a *separate* capability, collected in the same
        # pass. Alpha Vantage is the only vendor here that implements it, so
        # capability discovery asks it and nobody else — and its articles
        # merge into the same stream, carrying sentiment the others lack.
        scored = fabric.collect(
            "news_sentiment", symbol, self.vendors,
            lambda v: v.get_news_sentiment(symbol, limit),
        )
        return headlines + scored

    def get_news(self, symbol: str, company_name: str = "", limit: int = 12) -> ProviderResult[list[NewsHeadline]]:
        symbol = symbol.upper()
        links = [
            ChainLink(self.newsapi, lambda: self.newsapi.get_news(symbol, company_name, limit)),
            ChainLink(self.gnews, lambda: self.gnews.get_news(symbol, company_name, limit)),
            ChainLink(self.yahoo_rss, lambda: self.yahoo_rss.get_news(symbol, company_name, limit)),
            ChainLink(self.tavily, lambda: self.tavily.get_news(symbol, company_name, limit)),
            ChainLink(self.tiingo, lambda: self.tiingo.get_news(symbol, limit)),
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
