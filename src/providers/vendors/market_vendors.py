"""
Market-data vendor adapters: Polygon, Finnhub, TwelveData, FMP, MarketStack,
yfinance (keyless anchor of every chain).

Each returns normalized schemas or None (no data); infrastructure failures
raise VendorError and are handled by the chain.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from src.quant.pit.calendar import session_date_from_epoch
from src.providers.base import VendorClient, VendorError
from src.providers.schemas import (
    AnalystTargets,
    CompanyProfile,
    EarningsSurprise,
    FundamentalsData,
    OHLCVBar,
    PriceQuote,
    PriceSeries,
    RecommendationMonth,
    StreetData,
    AnalystConsensus,
    OwnershipData,
)

PERIOD_DAYS = {"1mo": 31, "3mo": 92, "6mo": 184, "1y": 366, "5y": 1830}


def _period_to_days(period: str) -> int:
    return PERIOD_DAYS.get(period, 92)


def _safe_float(value) -> Optional[float]:
    try:
        result = float(value)
        return result if result == result else None  # NaN guard
    except (TypeError, ValueError):
        return None


# ── Polygon ───────────────────────────────────────────────────────────────────

def _registrable_domain(website: str) -> str:
    """The bare domain a logo provider can be keyed on.

    Vendors return "https://www.apple.com/", "apple.com" and
    "http://investor.apple.com" for the same company. Only the host matters,
    and `www.` is never part of a brand's identity — leaving it in would make
    two spellings of one company miss each other in the logo cache.
    """
    if not website:
        return ""
    host = website.strip().lower()
    for prefix in ("https://", "http://"):
        if host.startswith(prefix):
            host = host[len(prefix):]
    host = host.split("/")[0].split("?")[0].strip()
    if host.startswith("www."):
        host = host[4:]
    return host if "." in host else ""


class PolygonVendor(VendorClient):
    NAME = "polygon"
    KEY_ENV = "POLYGON_API_KEY"
    DEFAULT_RPM = 5  # free tier

    BASE = "https://api.polygon.io"

    def get_price(self, symbol: str) -> Optional[PriceQuote]:
        data = self._get_json(
            f"{self.BASE}/v2/aggs/ticker/{symbol}/prev",
            params={"adjusted": "true", "apiKey": self.api_key},
        )
        results = data.get("results") or []
        if not results:
            return None
        row = results[0]
        close = _safe_float(row.get("c"))
        if close is None:
            return None
        # The aggregate already carried the whole session — open, high, low,
        # volume, VWAP and the trade count — and the adapter kept the close.
        # `vw` in particular is a statistic nothing else here supplies: the
        # average a share actually traded at, as opposed to the last print.
        stamp = _safe_float(row.get("t"))
        return PriceQuote(
            symbol=symbol,
            price=close,
            day_open=_safe_float(row.get("o")),
            day_high=_safe_float(row.get("h")),
            day_low=_safe_float(row.get("l")),
            volume=_safe_float(row.get("v")),
            vwap=_safe_float(row.get("vw")),
            trade_count=int(row["n"]) if isinstance(row.get("n"), (int, float)) else None,
            # Polygon stamps in epoch milliseconds.
            as_of=(
                datetime.fromtimestamp(stamp / 1000, tz=timezone.utc).isoformat()
                if stamp else None
            ),
            # This endpoint is the *previous* session's aggregate, not a live
            # tick. Saying so keeps a consumer from reading it as current.
            price_basis="previous session close",
        )

    def get_company(self, symbol: str) -> Optional[CompanyProfile]:
        """Reference data for a ticker.

        Polygon was wired only for prices, but its reference endpoint carries
        a full business description, the company homepage, headcount and the
        listing exchange — a company-identity source the fabric had no idea
        existed. The homepage is what yields a registrable domain, which is
        what the logo provider is keyed on.
        """
        data = self._get_json(
            f"{self.BASE}/v3/reference/tickers/{symbol}",
            params={"apiKey": self.api_key}, operation="company",
        )
        result = (data or {}).get("results")
        if not isinstance(result, dict) or not result.get("name"):
            return None
        website = str(result.get("homepage_url") or "")
        employees = result.get("total_employees")
        return CompanyProfile(
            symbol=symbol,
            name=str(result.get("name") or ""),
            # Polygon classifies by SIC, which is a description rather than a
            # GICS sector; it lands in `industry` because that is what it is.
            industry=str(result.get("sic_description") or ""),
            market_cap=_safe_float(result.get("market_cap")),
            currency=str(result.get("currency_name") or "USD").upper(),
            exchange=str(result.get("primary_exchange") or ""),
            website=website,
            domain=_registrable_domain(website),
            description=str(result.get("description") or "")[:1200],
            employees=int(employees) if isinstance(employees, (int, float)) else None,
            country=str(result.get("locale") or "").upper(),
            ipo_date=str(result.get("list_date") or ""),
        )

    def get_series(self, symbol: str, period: str) -> Optional[PriceSeries]:
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=_period_to_days(period))
        data = self._get_json(
            f"{self.BASE}/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}",
            params={"adjusted": "true", "sort": "asc", "limit": 5000, "apiKey": self.api_key},
        )
        bars = [
            OHLCVBar(
                # Resolved in the exchange timezone, not UTC. See
                # pit.calendar.session_date_from_epoch — the UTC reading is
                # right for US bars only by the sign of the offset.
                date=session_date_from_epoch(item["t"] / 1000),
                open=_safe_float(item.get("o")), high=_safe_float(item.get("h")),
                low=_safe_float(item.get("l")), close=_safe_float(item.get("c")) or 0.0,
                volume=int(item["v"]) if item.get("v") else None,
            )
            for item in (data.get("results") or [])
            if _safe_float(item.get("c")) is not None
        ]
        return PriceSeries(symbol=symbol, bars=bars) if bars else None


# ── Finnhub ───────────────────────────────────────────────────────────────────

class FinnhubVendor(VendorClient):
    NAME = "finnhub"
    KEY_ENV = "FINNHUB_API_KEY"
    DEFAULT_RPM = 50  # free tier is 60/min; stay under

    BASE = "https://finnhub.io/api/v1"

    def _params(self, **kwargs) -> dict:
        return {**kwargs, "token": self.api_key}

    def get_price(self, symbol: str) -> Optional[PriceQuote]:
        data = self._get_json(f"{self.BASE}/quote", params=self._params(symbol=symbol))
        price = _safe_float(data.get("c"))
        if not price:  # Finnhub returns 0 for unknown symbols
            return None
        # The session move and the previous close were both in this response.
        # The vendor's own `d`/`dp` are kept rather than derived from
        # `price - previous_close`: a vendor computing against its own
        # official close is more authoritative than our subtraction.
        stamp = _safe_float(data.get("t"))
        return PriceQuote(
            symbol=symbol,
            price=price,
            change=_safe_float(data.get("d")),
            change_pct=_safe_float(data.get("dp")),
            day_open=_safe_float(data.get("o")),
            day_high=_safe_float(data.get("h")),
            day_low=_safe_float(data.get("l")),
            previous_close=_safe_float(data.get("pc")),
            as_of=(
                datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat()
                if stamp else None
            ),
            price_basis="last sale",
        )

    def get_company(self, symbol: str) -> Optional[CompanyProfile]:
        """Company profile.

        `weburl`, `ipo` and `logo` were all in this response and all dropped.
        The URL is the one that mattered most: it is the only source of a
        registrable domain on this key, and the logo provider is keyed on
        domain when a ticker lookup misses.
        """
        data = self._get_json(f"{self.BASE}/stock/profile2", params=self._params(symbol=symbol))
        if not data or not data.get("name"):
            return None
        market_cap = _safe_float(data.get("marketCapitalization"))
        website = str(data.get("weburl") or "")
        return CompanyProfile(
            symbol=symbol,
            name=data.get("name", ""),
            sector=data.get("finnhubIndustry", ""),
            industry=data.get("finnhubIndustry", ""),
            market_cap=market_cap * 1e6 if market_cap else None,  # reported in millions
            currency=data.get("currency", "USD"),
            exchange=data.get("exchange", ""),
            website=website,
            domain=_registrable_domain(website),
            ipo_date=str(data.get("ipo") or ""),
            vendor_image=str(data.get("logo") or ""),
            country=str(data.get("country") or ""),
        )

    def search_symbols(self, query: str, limit: int = 8) -> Optional[list[dict]]:
        """Symbol lookup: [{symbol, name}] for a company-name/ticker query."""
        data = self._get_json(f"{self.BASE}/search", params=self._params(q=query))
        rows = (data.get("result") or [])[: limit * 2]
        out = [
            {"symbol": row.get("symbol", ""), "name": row.get("description", "")}
            for row in rows
            if row.get("symbol") and "." not in row.get("symbol", "")  # US listings first
        ]
        return out[:limit] or None

    def get_fundamentals(self, symbol: str) -> Optional[FundamentalsData]:
        data = self._get_json(
            f"{self.BASE}/stock/metric", params=self._params(symbol=symbol, metric="all")
        )
        metric = data.get("metric") or {}
        if not metric:
            return None
        # 133 figures come back for this one request; the adapter kept seven.
        # Period is encoded in the destination field name because that is what
        # makes these comparable at all — a TTM margin and a 5-year average
        # are different measurements, and flattening both to "margin" would
        # invite a reconciler to average them.
        return FundamentalsData(
            symbol=symbol,
            pe_ratio=_safe_float(metric.get("peTTM")),
            eps=_safe_float(metric.get("epsTTM")),
            beta=_safe_float(metric.get("beta")),
            week_52_high=_safe_float(metric.get("52WeekHigh")),
            week_52_low=_safe_float(metric.get("52WeekLow")),
            dividend_yield=_safe_float(metric.get("currentDividendYieldTTM")),
            profit_margin=_safe_float(metric.get("netProfitMarginTTM")),

            price_to_sales=_safe_float(metric.get("psTTM")),
            price_to_book=_safe_float(metric.get("pbQuarterly") or metric.get("pb")),
            ev_to_ebitda=_safe_float(metric.get("evEbitdaTTM")),
            ev_to_revenue=_safe_float(metric.get("evRevenueTTM")),

            gross_margin_ttm=_safe_float(metric.get("grossMarginTTM")),
            operating_margin_ttm=_safe_float(metric.get("operatingMarginTTM")),
            net_margin_ttm=_safe_float(metric.get("netProfitMarginTTM")),
            net_margin_5y=_safe_float(metric.get("netProfitMargin5Y")),

            roe_ttm=_safe_float(metric.get("roeTTM")),
            roa_ttm=_safe_float(metric.get("roaTTM")),
            roi_ttm=_safe_float(metric.get("roiTTM")),

            revenue_growth_ttm_yoy=_safe_float(metric.get("revenueGrowthTTMYoy")),
            revenue_growth_3y=_safe_float(metric.get("revenueGrowth3Y")),
            eps_growth_ttm_yoy=_safe_float(metric.get("epsGrowthTTMYoy")),
            eps_growth_3y=_safe_float(metric.get("epsGrowth3Y")),

            current_ratio=_safe_float(metric.get("currentRatioQuarterly")),
            quick_ratio=_safe_float(metric.get("quickRatioQuarterly")),
            debt_to_equity=_safe_float(metric.get("totalDebt/totalEquityQuarterly")),
            long_term_debt_to_equity=_safe_float(metric.get("longTermDebt/equityQuarterly")),

            payout_ratio_ttm=_safe_float(metric.get("payoutRatioTTM")),
            # Whatever else the vendor sent. Kept so a later feature can use a
            # figure this response already contained without a new round trip.
            vendor_metrics={
                k: v for k, v in metric.items()
                if isinstance(v, (int, float)) and v == v
            },
        )

    def get_analyst_targets(self, symbol: str) -> Optional[AnalystTargets]:
        # Premium on some plans — a 403 surfaces as VendorError and the chain moves on.
        data = self._get_json(f"{self.BASE}/stock/price-target", params=self._params(symbol=symbol))
        mean = _safe_float(data.get("targetMean"))
        if mean is None:
            return None
        return AnalystTargets(
            symbol=symbol,
            target_mean=mean,
            target_high=_safe_float(data.get("targetHigh")),
            target_low=_safe_float(data.get("targetLow")),
            analyst_count=int(data["numberOfAnalysts"]) if data.get("numberOfAnalysts") else None,
        )

    def get_street(self, symbol: str) -> Optional[StreetData]:
        """v4.5: recommendation trends + EPS surprises + insider sentiment —
        three free-tier endpoints combined into one normalized read. Each
        sub-fetch is independent; a partial answer is still an answer."""
        recs: list[RecommendationMonth] = []
        try:
            rows = self._get_json(f"{self.BASE}/stock/recommendation", params=self._params(symbol=symbol))
            for row in (rows or [])[:4]:
                recs.append(RecommendationMonth(
                    period=str(row.get("period", "")),
                    strong_buy=int(row.get("strongBuy") or 0),
                    buy=int(row.get("buy") or 0),
                    hold=int(row.get("hold") or 0),
                    sell=int(row.get("sell") or 0),
                    strong_sell=int(row.get("strongSell") or 0),
                ))
        except Exception:  # noqa: BLE001 — partial street data is acceptable
            pass

        surprises: list[EarningsSurprise] = []
        try:
            rows = self._get_json(f"{self.BASE}/stock/earnings", params=self._params(symbol=symbol))
            for row in (rows or [])[:4]:
                actual, estimate = _safe_float(row.get("actual")), _safe_float(row.get("estimate"))
                pct = None
                if actual is not None and estimate not in (None, 0):
                    pct = round(100 * (actual - estimate) / abs(estimate), 2)
                surprises.append(EarningsSurprise(
                    period=str(row.get("period", "")), actual=actual, estimate=estimate, surprise_pct=pct,
                ))
        except Exception:  # noqa: BLE001
            pass

        mspr = net = None
        try:
            from datetime import date, timedelta
            end = date.today()
            start = end - timedelta(days=183)
            data = self._get_json(
                f"{self.BASE}/stock/insider-sentiment",
                params=self._params(symbol=symbol, **{"from": start.isoformat(), "to": end.isoformat()}),
            )
            months = (data or {}).get("data") or []
            if months:
                latest = months[-1]
                mspr = _safe_float(latest.get("mspr"))
                net = _safe_float(latest.get("change"))
        except Exception:  # noqa: BLE001
            pass

        if not recs and not surprises and mspr is None:
            return None
        return StreetData(
            symbol=symbol, recommendations=recs, surprises=surprises,
            insider_mspr=mspr, insider_net_shares=net,
        )


# ── TwelveData ────────────────────────────────────────────────────────────────

class TwelveDataVendor(VendorClient):
    NAME = "twelvedata"
    KEY_ENV = "TWELVEDATA_API_KEY"
    DEFAULT_RPM = 8  # free tier

    BASE = "https://api.twelvedata.com"

    def get_price(self, symbol: str) -> Optional[PriceQuote]:
        """Full quote, not the bare `/price` endpoint.

        `/price` returns one number. `/quote` costs the same one request
        against the same 8/minute budget and returns the session's open,
        high, low, previous close, volume and 52-week range as well — so the
        old call was paying full price for a tenth of the payload.
        """
        data = self._get_json(
            f"{self.BASE}/quote", params={"symbol": symbol, "apikey": self.api_key},
        )
        if not isinstance(data, dict) or data.get("status") == "error":
            return None
        price = _safe_float(data.get("close")) or _safe_float(data.get("price"))
        if not price:
            return None
        fifty_two = data.get("fifty_two_week") if isinstance(data.get("fifty_two_week"), dict) else {}
        return PriceQuote(
            symbol=symbol,
            price=price,
            as_of=str(data.get("datetime") or "") or None,
            day_open=_safe_float(data.get("open")),
            day_high=_safe_float(data.get("high")),
            day_low=_safe_float(data.get("low")),
            previous_close=_safe_float(data.get("previous_close")),
            volume=_safe_float(data.get("volume")),
            price_basis="last sale",
            week_52_high=_safe_float(fifty_two.get("high")),
            week_52_low=_safe_float(fifty_two.get("low")),
        )

    def get_series(self, symbol: str, period: str) -> Optional[PriceSeries]:
        data = self._get_json(
            f"{self.BASE}/time_series",
            params={
                "symbol": symbol, "interval": "1day",
                "outputsize": min(_period_to_days(period), 5000),
                "order": "asc", "apikey": self.api_key,
            },
        )
        if data.get("status") == "error":
            raise VendorError(f"twelvedata: {data.get('message', 'error')}", transient=False)
        values = data.get("values") or []
        bars = [
            OHLCVBar(
                date=item.get("datetime", "")[:10],
                open=_safe_float(item.get("open")), high=_safe_float(item.get("high")),
                low=_safe_float(item.get("low")), close=_safe_float(item.get("close")) or 0.0,
                volume=int(float(item["volume"])) if item.get("volume") else None,
            )
            for item in values
            if _safe_float(item.get("close")) is not None
        ]
        return PriceSeries(symbol=symbol, bars=bars) if bars else None


# ── Financial Modeling Prep ───────────────────────────────────────────────────

class FMPVendor(VendorClient):
    NAME = "fmp"
    KEY_ENV = "FMP_API_KEY"
    DEFAULT_RPM = 10  # free tier is 250/day — keep bursts polite

    BASE = "https://financialmodelingprep.com/api/v3"

    def get_price(self, symbol: str) -> Optional[PriceQuote]:
        data = self._get_json(f"{self.BASE}/quote/{symbol}", params={"apikey": self.api_key})
        if not isinstance(data, list) or not data:
            return None
        row = data[0]
        price = _safe_float(row.get("price"))
        if not price:
            return None
        # FMP's quote is the richest in the set — roughly twenty-five fields,
        # of which one was being kept. The moving averages are the vendor's
        # own; recomputing them from our series would be cheap but would use
        # our adjustment conventions rather than theirs, so both can differ
        # legitimately and the vendor's value is what belongs on its quote.
        stamp = _safe_float(row.get("timestamp"))
        return PriceQuote(
            symbol=symbol,
            price=price,
            change=_safe_float(row.get("change")),
            change_pct=_safe_float(row.get("changesPercentage")),
            day_open=_safe_float(row.get("open")),
            day_high=_safe_float(row.get("dayHigh")),
            day_low=_safe_float(row.get("dayLow")),
            previous_close=_safe_float(row.get("previousClose")),
            volume=_safe_float(row.get("volume")),
            avg_volume=_safe_float(row.get("avgVolume")),
            week_52_high=_safe_float(row.get("yearHigh")),
            week_52_low=_safe_float(row.get("yearLow")),
            ma_50=_safe_float(row.get("priceAvg50")),
            ma_200=_safe_float(row.get("priceAvg200")),
            market_cap=_safe_float(row.get("marketCap")),
            exchange=str(row.get("exchange") or ""),
            as_of=(
                datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat()
                if stamp else None
            ),
            price_basis="last sale",
        )

    def get_series(self, symbol: str, period: str) -> Optional[PriceSeries]:
        data = self._get_json(
            f"{self.BASE}/historical-price-full/{symbol}",
            params={"timeseries": _period_to_days(period), "apikey": self.api_key},
        )
        history = data.get("historical") or []
        bars = []
        for item in reversed(history):  # FMP returns newest first
            # `adjClose` over `close`. This was using the raw close, which
            # renders a 4-for-1 split as a 75% single-day crash — and every
            # other series vendor here already returns adjusted values, so an
            # unadjusted FMP series would manufacture a cross-vendor conflict
            # at each historical split and put a false drawdown into any
            # portfolio curve drawn from it.
            close = _safe_float(item.get("adjClose")) or _safe_float(item.get("close"))
            if close is None:
                continue
            bars.append(OHLCVBar(
                date=item.get("date", ""),
                open=_safe_float(item.get("open")), high=_safe_float(item.get("high")),
                low=_safe_float(item.get("low")), close=close,
                volume=int(item["volume"]) if item.get("volume") else None,
            ))
        return PriceSeries(symbol=symbol, bars=bars) if bars else None

    def search_symbols(self, query: str, limit: int = 8) -> Optional[list[dict]]:
        """Symbol lookup: [{symbol, name}] for a company-name/ticker query."""
        data = self._get_json(
            f"{self.BASE}/search",
            params={"query": query, "limit": limit, "exchange": "NASDAQ,NYSE,AMEX",
                    "apikey": self.api_key},
        )
        if not isinstance(data, list):
            return None
        out = [
            {"symbol": row.get("symbol", ""), "name": row.get("name", "")}
            for row in data
            if row.get("symbol")
        ]
        return out[:limit] or None

    def get_company(self, symbol: str) -> Optional[CompanyProfile]:
        """Full company profile.

        The response already carried description, website, CEO, headcount,
        country, IPO date and beta on every call — the adapter kept six fields
        and dropped the rest, so the product had no business description and
        no domain to key a logo on while paying for a request that contained
        both.
        """
        data = self._get_json(f"{self.BASE}/profile/{symbol}", params={"apikey": self.api_key})
        if not isinstance(data, list) or not data:
            return None
        item = data[0]
        website = str(item.get("website") or "")
        employees = item.get("fullTimeEmployees")
        try:
            headcount = int(str(employees).replace(",", "")) if employees else None
        except (TypeError, ValueError):
            headcount = None
        return CompanyProfile(
            symbol=symbol,
            name=item.get("companyName", ""),
            sector=item.get("sector", ""),
            industry=item.get("industry", ""),
            market_cap=_safe_float(item.get("mktCap")),
            currency=item.get("currency", "USD"),
            exchange=item.get("exchangeShortName", ""),
            website=website,
            domain=_registrable_domain(website),
            description=str(item.get("description") or "")[:1200],
            ceo=str(item.get("ceo") or ""),
            employees=headcount,
            country=str(item.get("country") or ""),
            ipo_date=str(item.get("ipoDate") or ""),
            beta=_safe_float(item.get("beta")),
            vendor_image=str(item.get("image") or ""),
        )

    def get_fundamentals(self, symbol: str) -> Optional[FundamentalsData]:
        data = self._get_json(f"{self.BASE}/quote/{symbol}", params={"apikey": self.api_key})
        if not isinstance(data, list) or not data:
            return None
        item = data[0]
        return FundamentalsData(
            symbol=symbol,
            pe_ratio=_safe_float(item.get("pe")),
            eps=_safe_float(item.get("eps")),
            week_52_high=_safe_float(item.get("yearHigh")),
            week_52_low=_safe_float(item.get("yearLow")),
        )


# ── MarketStack ───────────────────────────────────────────────────────────────



class MarketStackVendor(VendorClient):
    NAME = "marketstack"
    KEY_ENV = "MARKETSTACK_API_KEY"
    DEFAULT_RPM = 5  # tiny free quota (requests/month) — last resort only

    BASE = "https://api.marketstack.com/v1"

    def get_series(self, symbol: str, period: str) -> Optional[PriceSeries]:
        data = self._get_json(
            f"{self.BASE}/eod",
            params={
                "access_key": self.api_key, "symbols": symbol,
                "limit": min(_period_to_days(period), 1000), "sort": "ASC",
            },
        )
        rows = data.get("data") or []
        bars = []
        for item in rows:
            # Adjusted values where the vendor supplies them, raw otherwise.
            # This is not cosmetic: an unadjusted series renders a 4-for-1
            # split as a 75% single-day crash, and a portfolio value curve
            # built on one reports a loss that never happened. Every other
            # series vendor here already returns adjusted closes, so mixing
            # an unadjusted Marketstack series into the same consensus would
            # manufacture disagreement at every historical split.
            close = _safe_float(item.get("adj_close")) or _safe_float(item.get("close"))
            if close is None:
                continue
            volume = _safe_float(item.get("adj_volume")) or _safe_float(item.get("volume"))
            bars.append(OHLCVBar(
                date=str(item.get("date", ""))[:10],
                open=_safe_float(item.get("adj_open")) or _safe_float(item.get("open")),
                high=_safe_float(item.get("adj_high")) or _safe_float(item.get("high")),
                low=_safe_float(item.get("adj_low")) or _safe_float(item.get("low")),
                close=close,
                volume=int(volume) if volume else None,
            ))
        return PriceSeries(symbol=symbol, bars=bars) if bars else None

    def get_price(self, symbol: str) -> Optional[PriceQuote]:
        series = self.get_series(symbol, "1mo")
        if series and series.bars:
            return PriceQuote(symbol=symbol, price=series.bars[-1].close)
        return None


# ── yfinance (keyless anchor) ─────────────────────────────────────────────────

class YFinanceVendor(VendorClient):
    NAME = "yfinance"
    KEY_ENV = None       # keyless — always configured
    DEFAULT_RPM = 30

    def get_series(self, symbol: str, period: str) -> Optional[PriceSeries]:
        import yfinance as yf

        def _fetch():
            return yf.Ticker(symbol).history(period=period)

        history = self.timed_call(_fetch)
        if history is None or history.empty:
            return None
        bars = []
        for index, row in history.iterrows():
            date_str = index.strftime("%Y-%m-%d") if hasattr(index, "strftime") else str(index)[:10]
            close = _safe_float(row.get("Close"))
            if close is None:
                continue
            bars.append(OHLCVBar(
                date=date_str,
                open=_safe_float(row.get("Open")), high=_safe_float(row.get("High")),
                low=_safe_float(row.get("Low")), close=close,
                volume=int(row["Volume"]) if "Volume" in row and row["Volume"] == row["Volume"] else None,
            ))
        return PriceSeries(symbol=symbol, bars=bars) if bars else None

    def get_price(self, symbol: str) -> Optional[PriceQuote]:
        series = self.get_series(symbol, "1mo")
        if series and series.bars:
            return PriceQuote(symbol=symbol, price=series.bars[-1].close)
        return None

    def get_company(self, symbol: str) -> Optional[CompanyProfile]:
        """Company profile from Yahoo's info payload.

        Worth having despite yfinance being an unofficial scrape: it is the
        only *keyless* profile source in the system, so it answers for every
        symbol even when every authenticated vendor is rate-limited or
        unentitled — which is exactly the situation the free tiers produce.
        Its provenance names it, so a reader can weigh it accordingly.
        """
        import yfinance as yf

        info = self.timed_call(lambda: yf.Ticker(symbol).info, operation="company")
        if not isinstance(info, dict) or not info.get("longName") and not info.get("shortName"):
            return None
        website = str(info.get("website") or "")
        employees = info.get("fullTimeEmployees")
        return CompanyProfile(
            symbol=symbol,
            name=str(info.get("longName") or info.get("shortName") or ""),
            sector=str(info.get("sector") or ""),
            industry=str(info.get("industry") or ""),
            market_cap=_safe_float(info.get("marketCap")),
            currency=str(info.get("currency") or "USD").upper(),
            exchange=str(info.get("exchange") or ""),
            website=website,
            domain=_registrable_domain(website),
            description=str(info.get("longBusinessSummary") or "")[:1200],
            employees=int(employees) if isinstance(employees, (int, float)) else None,
            country=str(info.get("country") or ""),
            beta=_safe_float(info.get("beta")),
        )

    def get_fundamentals(self, symbol: str) -> Optional[FundamentalsData]:
        """Valuation, margins, returns and leverage from the info payload.

        `.info` returns roughly 185 fields; the adapter was using twelve of
        them for a profile and ignoring the rest. Because yfinance is
        **keyless**, this is the only fundamentals source in the system that
        answers in every environment — including local development and CI,
        where every authenticated vendor reports `not_configured`.

        Yahoo reports margins and returns as fractions (0.4865) where Finnhub
        reports percentages (48.65). They are converted here rather than at
        the edge, so a reconciler comparing the two vendors is comparing the
        same unit — mixing the conventions would show a 100x "disagreement"
        between two vendors that actually agree.
        """
        import yfinance as yf

        info = self.timed_call(lambda: yf.Ticker(symbol).info, operation="fundamentals")
        if not isinstance(info, dict) or not info:
            return None

        def pct(key):
            """Fraction → percent, preserving None."""
            value = _safe_float(info.get(key))
            return round(value * 100, 4) if value is not None else None

        data = FundamentalsData(
            symbol=symbol,
            pe_ratio=_safe_float(info.get("trailingPE")),
            forward_pe=_safe_float(info.get("forwardPE")),
            eps=_safe_float(info.get("trailingEps")),
            beta=_safe_float(info.get("beta")),
            week_52_high=_safe_float(info.get("fiftyTwoWeekHigh")),
            week_52_low=_safe_float(info.get("fiftyTwoWeekLow")),
            dividend_yield=pct("dividendYield"),
            profit_margin=pct("profitMargins"),

            price_to_sales=_safe_float(info.get("priceToSalesTrailing12Months")),
            price_to_book=_safe_float(info.get("priceToBook")),
            ev_to_ebitda=_safe_float(info.get("enterpriseToEbitda")),
            ev_to_revenue=_safe_float(info.get("enterpriseToRevenue")),

            gross_margin_ttm=pct("grossMargins"),
            operating_margin_ttm=pct("operatingMargins"),
            net_margin_ttm=pct("profitMargins"),

            roe_ttm=pct("returnOnEquity"),
            roa_ttm=pct("returnOnAssets"),

            revenue_growth_ttm_yoy=pct("revenueGrowth"),
            eps_growth_ttm_yoy=pct("earningsGrowth"),

            current_ratio=_safe_float(info.get("currentRatio")),
            quick_ratio=_safe_float(info.get("quickRatio")),
            # Yahoo reports debt/equity as a percentage (78.4), Finnhub as a
            # ratio (0.784). Normalised to the ratio so the two are comparable.
            debt_to_equity=(
                round(_safe_float(info.get("debtToEquity")) / 100, 4)
                if _safe_float(info.get("debtToEquity")) is not None else None
            ),
            vendor_metrics={
                k: v for k, v in {
                    "enterprise_value": _safe_float(info.get("enterpriseValue")),
                    "total_revenue": _safe_float(info.get("totalRevenue")),
                    "ebitda": _safe_float(info.get("ebitda")),
                    "free_cash_flow": _safe_float(info.get("freeCashflow")),
                    "operating_cash_flow": _safe_float(info.get("operatingCashflow")),
                    "total_cash": _safe_float(info.get("totalCash")),
                    "total_debt": _safe_float(info.get("totalDebt")),
                    "book_value": _safe_float(info.get("bookValue")),
                    "peg_ratio": _safe_float(info.get("trailingPegRatio")),
                    "ebitda_margins": pct("ebitdaMargins"),
                }.items() if v is not None
            },
        )
        # A payload with no usable figure at all is an absence, not a company
        # whose every ratio is zero.
        if data.pe_ratio is None and data.net_margin_ttm is None and not data.vendor_metrics:
            return None
        return data

    def get_ownership(self, symbol: str) -> Optional[OwnershipData]:
        """Share count, float, insider/institutional holdings and short interest.

        Keyless, and nothing else in the system supplies it. Short interest in
        particular carries its own settlement date because exchanges publish
        it twice a month — a short figure without that date is close to
        meaningless, so the date travels with it or the figure is not shown.
        """
        import yfinance as yf
        from datetime import datetime, timezone as _tz

        info = self.timed_call(lambda: yf.Ticker(symbol).info, operation="ownership")
        if not isinstance(info, dict):
            return None

        short_date = None
        stamp = _safe_float(info.get("dateShortInterest"))
        if stamp:
            try:
                short_date = session_date_from_epoch(stamp)
            except (OSError, ValueError, OverflowError):
                short_date = None

        data = OwnershipData(
            symbol=symbol,
            shares_outstanding=_safe_float(info.get("sharesOutstanding")),
            float_shares=_safe_float(info.get("floatShares")),
            held_percent_insiders=_safe_float(info.get("heldPercentInsiders")),
            held_percent_institutions=_safe_float(info.get("heldPercentInstitutions")),
            shares_short=_safe_float(info.get("sharesShort")),
            short_percent_of_float=_safe_float(info.get("shortPercentOfFloat")),
            short_ratio=_safe_float(info.get("shortRatio")),
            short_interest_date=short_date,
            source=self.NAME,
        )
        if all(getattr(data, f) is None for f in (
            "shares_outstanding", "float_shares", "held_percent_institutions", "shares_short",
        )):
            return None
        return data

    def get_analyst_consensus(self, symbol: str) -> Optional[AnalystConsensus]:
        """Price targets and the rating distribution, kept as a distribution."""
        import yfinance as yf

        info = self.timed_call(lambda: yf.Ticker(symbol).info, operation="analyst")
        if not isinstance(info, dict):
            return None
        target = _safe_float(info.get("targetMeanPrice"))
        if target is None:
            return None
        return AnalystConsensus(
            symbol=symbol,
            target_mean=target,
            target_high=_safe_float(info.get("targetHighPrice")),
            target_low=_safe_float(info.get("targetLowPrice")),
            analyst_count=(
                int(_safe_float(info.get("numberOfAnalystOpinions")))
                if _safe_float(info.get("numberOfAnalystOpinions")) else None
            ),
            recommendation=str(info.get("recommendationKey") or "") or None,
            recommendation_mean=_safe_float(info.get("recommendationMean")),
            source=self.NAME,
        )

    def search_symbols(self, query: str, limit: int = 8) -> Optional[list[dict]]:
        """Yahoo's own autocomplete search — keyless and fuzzy-tolerant, so
        it anchors the symbol-resolver chain the same way it already
        anchors prices/series when Finnhub/FMP are unconfigured, rate
        limited, or cooling down after failures."""
        import yfinance as yf

        def _fetch():
            return yf.Search(query, max_results=limit, enable_fuzzy_query=True).quotes

        quotes = self.timed_call(_fetch)
        out = [
            {"symbol": row["symbol"], "name": row.get("shortname") or row.get("longname") or row["symbol"]}
            for row in (quotes or [])
            if row.get("symbol")
        ]
        return out[:limit] or None
