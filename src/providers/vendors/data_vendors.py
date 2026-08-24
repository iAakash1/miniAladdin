"""
Data vendors: Alpha Vantage (delegates to the existing client — no logic
duplication) and FRED (macro series via fredapi).
"""

from __future__ import annotations

from typing import Optional

from src.providers.base import VendorClient, VendorError
from src.providers.schemas import (
    AnalystTargets,
    CompanyProfile,
    FundamentalsData,
    MacroSnapshot,
    NewsHeadline,
)


def _av_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _av_time(raw: str) -> str:
    """Alpha Vantage stamps news as `YYYYMMDDTHHMMSS`; everything downstream
    expects ISO-8601, and a mixed-format timestamp column sorts wrongly."""
    if len(raw) == 15 and raw[8] == "T":
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}T{raw[9:11]}:{raw[11:13]}:{raw[13:15]}Z"
    return raw


class AlphaVantageVendor(VendorClient):
    """Thin adapter over src/alpha_vantage.AlphaVantageClient."""

    NAME = "alpha_vantage"
    KEY_ENV = "ALPHA_VANTAGE_KEY"
    DEFAULT_RPM = 5  # free tier: 5/min, 25/day

    def __init__(self, session=None):
        super().__init__(session)
        from src.alpha_vantage import AlphaVantageClient

        self._client = AlphaVantageClient()

    def get_fundamentals(self, symbol: str) -> Optional[FundamentalsData]:
        raw = self.timed_call(lambda: self._client.get_fundamentals(symbol))
        if raw.error:
            return None
        return FundamentalsData(
            symbol=symbol,
            pe_ratio=raw.pe_ratio,
            forward_pe=raw.forward_pe,
            eps=raw.eps,
            beta=raw.beta,
            week_52_high=raw.week_52_high,
            week_52_low=raw.week_52_low,
            dividend_yield=raw.dividend_yield,
            profit_margin=raw.profit_margin,
            # The ratio surface OVERVIEW already returned. Alpha Vantage and
            # Finnhub compute several of these differently, which is exactly
            # why they are kept per-vendor and reconciled by the fabric's
            # union rather than averaged into one number.
            price_to_sales=raw.price_to_sales_ttm,
            price_to_book=raw.price_to_book,
            ev_to_ebitda=raw.ev_to_ebitda,
            ev_to_revenue=raw.ev_to_revenue,
            operating_margin_ttm=raw.operating_margin_ttm,
            net_margin_ttm=raw.profit_margin,
            roe_ttm=raw.return_on_equity_ttm,
            roa_ttm=raw.return_on_assets_ttm,
            revenue_growth_ttm_yoy=raw.quarterly_revenue_growth_yoy,
            eps_growth_ttm_yoy=raw.quarterly_earnings_growth_yoy,
            vendor_metrics={
                k: v for k, v in {
                    "ebitda": raw.ebitda,
                    "revenue_ttm": raw.revenue_ttm,
                    "gross_profit_ttm": raw.gross_profit_ttm,
                    "diluted_eps_ttm": raw.diluted_eps_ttm,
                    "book_value": raw.book_value,
                    "shares_outstanding": raw.shares_outstanding,
                    "peg_ratio": raw.peg_ratio,
                    "dividend_per_share": raw.dividend_per_share,
                    "analyst_strong_buy": raw.analyst_strong_buy,
                    "analyst_buy": raw.analyst_buy,
                    "analyst_hold": raw.analyst_hold,
                    "analyst_sell": raw.analyst_sell,
                    "analyst_strong_sell": raw.analyst_strong_sell,
                }.items() if v is not None
            },
            profile=CompanyProfile(
                symbol=symbol,
                name=raw.name or "",
                sector=raw.sector or "",
                industry=raw.industry or "",
                market_cap=raw.market_cap,
                currency=raw.currency or "USD",
                exchange=raw.exchange or "",
                country=raw.country or "",
                description=raw.description or "",
                beta=raw.beta,
            ),
        )

    def get_analyst_targets(self, symbol: str) -> Optional[AnalystTargets]:
        raw = self.timed_call(lambda: self._client.get_fundamentals(symbol))
        if raw.error or raw.analyst_target is None:
            return None
        return AnalystTargets(symbol=symbol, target_mean=raw.analyst_target)

    # ── NEWS_SENTIMENT ───────────────────────────────────────────────────────
    # The one capability in this codebase that no other news vendor has: a
    # per-article, per-ticker sentiment score with a relevance weight and a
    # topic taxonomy, produced by the vendor rather than by us. It was
    # entirely unused — Alpha Vantage was wired only for fundamentals — so
    # every research run was paying for a key whose most distinctive endpoint
    # was never called.
    #
    # Deliberately exposed as its own capability rather than folded into
    # `get_news`: the fabric asks vendors only for what they implement, and a
    # vendor that returns headlines without sentiment must not be asked for
    # sentiment it cannot produce.

    def get_news_sentiment(self, symbol: str, limit: int = 20) -> Optional[list[NewsHeadline]]:
        """Scored articles for one ticker.

        The ticker-specific score is used, not the article-level one: an
        article about the whole semiconductor sector can be broadly positive
        while being specifically negative about one name in it, and the
        overall figure would attribute the sector's tone to the company.
        """
        data = self.timed_call(
            lambda: self._client.call(
                function="NEWS_SENTIMENT", tickers=symbol,
                limit=str(min(limit, 50)), sort="LATEST",
            ),
            operation="news_sentiment",
        )
        if not isinstance(data, dict):
            return None
        feed = data.get("feed")
        if not isinstance(feed, list):
            return None

        out: list[NewsHeadline] = []
        for item in feed:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue

            # Per-ticker sentiment, matched to the symbol we asked about.
            score = label = relevance = None
            for row in item.get("ticker_sentiment") or []:
                if not isinstance(row, dict):
                    continue
                if str(row.get("ticker") or "").upper() == symbol.upper():
                    score = _av_float(row.get("ticker_sentiment_score"))
                    label = str(row.get("ticker_sentiment_label") or "") or None
                    relevance = _av_float(row.get("relevance_score"))
                    break

            out.append(NewsHeadline(
                title=title,
                source=str(item.get("source") or "alpha_vantage"),
                url=str(item.get("url") or ""),
                published_at=_av_time(str(item.get("time_published") or "")),
                summary=str(item.get("summary") or "")[:400],
                tags=[
                    str(t.get("topic")) for t in (item.get("topics") or [])
                    if isinstance(t, dict) and t.get("topic")
                ][:6],
                tickers=[
                    str(t.get("ticker")).upper() for t in (item.get("ticker_sentiment") or [])
                    if isinstance(t, dict) and t.get("ticker")
                ][:8],
                image_url=str(item.get("banner_image") or ""),
                # Vendor-scored, and labelled as such — this is evidence about
                # tone, not a prediction, and nothing downstream may treat it
                # as a signal.
                sentiment_score=score,
                sentiment_label=label,
                sentiment_relevance=relevance,
                sentiment_source=self.NAME,
            ))
        return out or None


class FredVendor(VendorClient):
    """FRED macro series. Only vendor for macro — chain degrades to demo values."""

    NAME = "fred"
    KEY_ENV = "FRED_API_KEY"
    DEFAULT_RPM = 30
    COOLDOWN_SECONDS = 120.0

    YIELD_CURVE_SERIES = "T10Y2Y"
    CPI_SERIES = "CPIAUCNS"
    FED_FUNDS_SERIES = "FEDFUNDS"

    def __init__(self, session=None):
        super().__init__(session)
        self._fred = None

    def _client(self):
        if self._fred is None:
            from fredapi import Fred

            self._fred = Fred(api_key=self.api_key)
        return self._fred

    def get_observations(self, series_id: str, count: int = 8) -> Optional[list[tuple[str, float]]]:
        """Last `count` (date, value) observations of any FRED series."""
        if not self.available:
            raise VendorError("fred: FRED_API_KEY not configured", transient=False)

        def _fetch() -> list[tuple[str, float]]:
            series = self._client().get_series(series_id).dropna().tail(count)
            return [(index.strftime("%Y-%m-%d"), float(value)) for index, value in series.items()]

        observations = self.timed_call(_fetch)
        return observations or None

    def get_macro(self) -> Optional[MacroSnapshot]:
        def _fetch() -> MacroSnapshot:
            fred = self._client()
            spread_series = fred.get_series(self.YIELD_CURVE_SERIES).dropna()
            cpi = fred.get_series(self.CPI_SERIES).dropna()
            current, year_ago = float(cpi.iloc[-1]), float(cpi.iloc[-13])
            inflation = round(((current - year_ago) / year_ago) * 100, 2)
            try:
                fed_rate = float(fred.get_series(self.FED_FUNDS_SERIES).dropna().iloc[-1])
            except Exception:  # noqa: BLE001 — optional series
                fed_rate = None
            return MacroSnapshot(
                yield_spread=float(spread_series.iloc[-1]),
                inflation_rate=inflation,
                fed_funds_rate=fed_rate,
            )

        if not self.available:
            raise VendorError("fred: FRED_API_KEY not configured", transient=False)
        return self.timed_call(_fetch)
