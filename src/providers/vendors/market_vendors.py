"""
Market-data vendor adapters: Polygon, Finnhub, TwelveData, FMP, MarketStack,
yfinance (keyless anchor of every chain).

Each returns normalized schemas or None (no data); infrastructure failures
raise VendorError and are handled by the chain.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from src.providers.base import VendorClient, VendorError
from src.providers.schemas import (
    AnalystTargets,
    CompanyProfile,
    FundamentalsData,
    OHLCVBar,
    PriceQuote,
    PriceSeries,
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
        close = _safe_float(results[0].get("c"))
        if close is None:
            return None
        return PriceQuote(symbol=symbol, price=close)

    def get_series(self, symbol: str, period: str) -> Optional[PriceSeries]:
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=_period_to_days(period))
        data = self._get_json(
            f"{self.BASE}/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}",
            params={"adjusted": "true", "sort": "asc", "limit": 5000, "apiKey": self.api_key},
        )
        bars = [
            OHLCVBar(
                date=datetime.fromtimestamp(item["t"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
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
        return PriceQuote(symbol=symbol, price=price)

    def get_company(self, symbol: str) -> Optional[CompanyProfile]:
        data = self._get_json(f"{self.BASE}/stock/profile2", params=self._params(symbol=symbol))
        if not data or not data.get("name"):
            return None
        market_cap = _safe_float(data.get("marketCapitalization"))
        return CompanyProfile(
            symbol=symbol,
            name=data.get("name", ""),
            sector=data.get("finnhubIndustry", ""),
            industry=data.get("finnhubIndustry", ""),
            market_cap=market_cap * 1e6 if market_cap else None,  # reported in millions
            currency=data.get("currency", "USD"),
            exchange=data.get("exchange", ""),
        )

    def get_fundamentals(self, symbol: str) -> Optional[FundamentalsData]:
        data = self._get_json(
            f"{self.BASE}/stock/metric", params=self._params(symbol=symbol, metric="all")
        )
        metric = data.get("metric") or {}
        if not metric:
            return None
        return FundamentalsData(
            symbol=symbol,
            pe_ratio=_safe_float(metric.get("peTTM")),
            eps=_safe_float(metric.get("epsTTM")),
            beta=_safe_float(metric.get("beta")),
            week_52_high=_safe_float(metric.get("52WeekHigh")),
            week_52_low=_safe_float(metric.get("52WeekLow")),
            dividend_yield=_safe_float(metric.get("currentDividendYieldTTM")),
            profit_margin=_safe_float(metric.get("netProfitMarginTTM")),
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


# ── TwelveData ────────────────────────────────────────────────────────────────

class TwelveDataVendor(VendorClient):
    NAME = "twelvedata"
    KEY_ENV = "TWELVEDATA_API_KEY"
    DEFAULT_RPM = 8  # free tier

    BASE = "https://api.twelvedata.com"

    def get_price(self, symbol: str) -> Optional[PriceQuote]:
        data = self._get_json(f"{self.BASE}/price", params={"symbol": symbol, "apikey": self.api_key})
        price = _safe_float(data.get("price"))
        return PriceQuote(symbol=symbol, price=price) if price else None

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
        price = _safe_float(data[0].get("price"))
        return PriceQuote(symbol=symbol, price=price) if price else None

    def get_series(self, symbol: str, period: str) -> Optional[PriceSeries]:
        data = self._get_json(
            f"{self.BASE}/historical-price-full/{symbol}",
            params={"timeseries": _period_to_days(period), "apikey": self.api_key},
        )
        history = data.get("historical") or []
        bars = [
            OHLCVBar(
                date=item.get("date", ""),
                open=_safe_float(item.get("open")), high=_safe_float(item.get("high")),
                low=_safe_float(item.get("low")), close=_safe_float(item.get("close")) or 0.0,
                volume=int(item["volume"]) if item.get("volume") else None,
            )
            for item in reversed(history)  # FMP returns newest first
            if _safe_float(item.get("close")) is not None
        ]
        return PriceSeries(symbol=symbol, bars=bars) if bars else None

    def get_company(self, symbol: str) -> Optional[CompanyProfile]:
        data = self._get_json(f"{self.BASE}/profile/{symbol}", params={"apikey": self.api_key})
        if not isinstance(data, list) or not data:
            return None
        item = data[0]
        return CompanyProfile(
            symbol=symbol,
            name=item.get("companyName", ""),
            sector=item.get("sector", ""),
            industry=item.get("industry", ""),
            market_cap=_safe_float(item.get("mktCap")),
            currency=item.get("currency", "USD"),
            exchange=item.get("exchangeShortName", ""),
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
        bars = [
            OHLCVBar(
                date=str(item.get("date", ""))[:10],
                open=_safe_float(item.get("open")), high=_safe_float(item.get("high")),
                low=_safe_float(item.get("low")), close=_safe_float(item.get("close")) or 0.0,
                volume=int(item["volume"]) if item.get("volume") else None,
            )
            for item in rows
            if _safe_float(item.get("close")) is not None
        ]
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
