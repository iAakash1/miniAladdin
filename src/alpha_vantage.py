"""
OmniSignal Alpha Vantage Integration
Fetches fundamental data and MACD signal to enrich technical analysis.

Free tier: 25 requests/day, 5/minute.
Strategy: 1 OVERVIEW call (fundamentals) + 1 MACD call per research request.
"""

from __future__ import annotations

import logging

import os
import time
from typing import Optional
from dataclasses import dataclass, field

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

BASE_URL = "https://www.alphavantage.co/query"


@dataclass
class FundamentalData:
    """Fundamental data from Alpha Vantage OVERVIEW endpoint."""
    ticker: str
    name: str = ""
    sector: str = ""
    market_cap: Optional[float] = None       # in USD
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    eps: Optional[float] = None
    analyst_target: Optional[float] = None   # consensus price target
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    beta: Optional[float] = None
    dividend_yield: Optional[float] = None   # as decimal e.g. 0.005
    profit_margin: Optional[float] = None

    # ── Additive (v5.3) ──────────────────────────────────────────────────────
    # OVERVIEW returns roughly sixty fields for one call against a free tier
    # that allows twenty-five calls a day. Keeping twelve of them meant most
    # of the day's most expensive request was discarded on arrival.
    #
    # Period is in the field name wherever the vendor's own key carries one,
    # for the same reason as elsewhere: a TTM figure and a quarterly figure
    # are different measurements and must not be namable as the same thing.
    industry: str = ""
    exchange: str = ""
    currency: str = ""
    country: str = ""
    description: str = ""
    fiscal_year_end: str = ""
    latest_quarter: str = ""

    ebitda: Optional[float] = None
    revenue_ttm: Optional[float] = None
    gross_profit_ttm: Optional[float] = None
    diluted_eps_ttm: Optional[float] = None
    revenue_per_share_ttm: Optional[float] = None
    book_value: Optional[float] = None
    shares_outstanding: Optional[float] = None

    peg_ratio: Optional[float] = None
    price_to_sales_ttm: Optional[float] = None
    price_to_book: Optional[float] = None
    ev_to_revenue: Optional[float] = None
    ev_to_ebitda: Optional[float] = None
    return_on_assets_ttm: Optional[float] = None
    return_on_equity_ttm: Optional[float] = None
    operating_margin_ttm: Optional[float] = None

    quarterly_revenue_growth_yoy: Optional[float] = None
    quarterly_earnings_growth_yoy: Optional[float] = None

    dividend_per_share: Optional[float] = None
    dividend_date: str = ""
    ex_dividend_date: str = ""

    #: Consensus analyst rating distribution, when the vendor supplies it.
    #: A distribution, never collapsed to a single "rating" — the spread
    #: between strong-buy and hold counts is the informative part.
    analyst_strong_buy: Optional[int] = None
    analyst_buy: Optional[int] = None
    analyst_hold: Optional[int] = None
    analyst_sell: Optional[int] = None
    analyst_strong_sell: Optional[int] = None

    error: Optional[str] = None


@dataclass
class MacdSignal:
    """MACD indicator values."""
    macd: Optional[float] = None
    signal: Optional[float] = None
    histogram: Optional[float] = None
    crossover: Optional[str] = None   # "bullish" | "bearish" | "neutral"
    error: Optional[str] = None


def _safe_float(value, default=None) -> Optional[float]:
    """Parse a value to float safely, returning default on failure."""
    if value is None or value == "None" or value == "-":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


class AlphaVantageClient:
    """
    Lightweight Alpha Vantage client.
    Gracefully returns empty data when the key is missing or rate-limited.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ALPHA_VANTAGE_KEY", "")
        self.available = bool(self.api_key and len(self.api_key) > 5)
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "OmniSignal/1.0"})

    def _get(self, params: dict, timeout: int = 10) -> Optional[dict]:
        """Make a GET request to Alpha Vantage. Returns None on any failure."""
        if not self.available:
            return None
        try:
            params["apikey"] = self.api_key
            r = self._session.get(BASE_URL, params=params, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            # AV returns {"Information": "..."} when rate limited
            if "Information" in data or "Note" in data:
                msg = data.get("Information") or data.get("Note", "Rate limited")
                logger.warning("Alpha Vantage rate-limited or informational response: %s", msg[:120])
                return None
            return data
        except Exception as e:
            logger.warning("Alpha Vantage request failed: %s", e)
            return None

    def call(self, **params) -> Optional[dict]:
        """Raw call for endpoints beyond the fundamentals overview.

        Public because the vendor adapter needs NEWS_SENTIMENT and it is the
        same key, same session, same rate-limit handling as everything else
        here — a second client would give the free tier's 25 daily calls two
        independent budgets that each believed they had the whole allowance.
        """
        return self._get(dict(params))

    def get_fundamentals(self, ticker: str) -> FundamentalData:
        """
        Fetch company overview. One call, lots of data.
        Returns FundamentalData with error set if unavailable.
        """
        result = FundamentalData(ticker=ticker.upper())

        if not self.available:
            result.error = "ALPHA_VANTAGE_KEY not configured"
            return result

        data = self._get({"function": "OVERVIEW", "symbol": ticker.upper()})

        if not data or "Symbol" not in data:
            result.error = "No fundamental data returned"
            return result

        result.name           = data.get("Name", "")
        result.sector         = data.get("Sector", "")
        result.pe_ratio       = _safe_float(data.get("PERatio"))
        result.forward_pe     = _safe_float(data.get("ForwardPE"))
        result.eps            = _safe_float(data.get("EPS"))
        result.analyst_target = _safe_float(data.get("AnalystTargetPrice"))
        result.week_52_high   = _safe_float(data.get("52WeekHigh"))
        result.week_52_low    = _safe_float(data.get("52WeekLow"))
        result.beta           = _safe_float(data.get("Beta"))
        result.profit_margin  = _safe_float(data.get("ProfitMargin"))
        result.dividend_yield = _safe_float(data.get("DividendYield"))

        # Market cap in billions
        mc = _safe_float(data.get("MarketCapitalization"))
        result.market_cap = mc  # raw USD

        # Everything below arrived in the same response and was previously
        # dropped. On a free tier of 25 calls/day this was the single most
        # wasteful discard in the codebase.
        result.industry        = data.get("Industry", "") or ""
        result.exchange        = data.get("Exchange", "") or ""
        result.currency        = data.get("Currency", "") or ""
        result.country         = data.get("Country", "") or ""
        result.description     = (data.get("Description", "") or "")[:1200]
        result.fiscal_year_end = data.get("FiscalYearEnd", "") or ""
        result.latest_quarter  = data.get("LatestQuarter", "") or ""

        result.ebitda                = _safe_float(data.get("EBITDA"))
        result.revenue_ttm           = _safe_float(data.get("RevenueTTM"))
        result.gross_profit_ttm      = _safe_float(data.get("GrossProfitTTM"))
        result.diluted_eps_ttm       = _safe_float(data.get("DilutedEPSTTM"))
        result.revenue_per_share_ttm = _safe_float(data.get("RevenuePerShareTTM"))
        result.book_value            = _safe_float(data.get("BookValue"))
        result.shares_outstanding    = _safe_float(data.get("SharesOutstanding"))

        result.peg_ratio            = _safe_float(data.get("PEGRatio"))
        result.price_to_sales_ttm   = _safe_float(data.get("PriceToSalesRatioTTM"))
        result.price_to_book        = _safe_float(data.get("PriceToBookRatio"))
        result.ev_to_revenue        = _safe_float(data.get("EVToRevenue"))
        result.ev_to_ebitda         = _safe_float(data.get("EVToEBITDA"))
        result.return_on_assets_ttm = _safe_float(data.get("ReturnOnAssetsTTM"))
        result.return_on_equity_ttm = _safe_float(data.get("ReturnOnEquityTTM"))
        result.operating_margin_ttm = _safe_float(data.get("OperatingMarginTTM"))

        result.quarterly_revenue_growth_yoy  = _safe_float(data.get("QuarterlyRevenueGrowthYOY"))
        result.quarterly_earnings_growth_yoy = _safe_float(data.get("QuarterlyEarningsGrowthYOY"))

        result.dividend_per_share = _safe_float(data.get("DividendPerShare"))
        result.dividend_date      = data.get("DividendDate", "") or ""
        result.ex_dividend_date   = data.get("ExDividendDate", "") or ""

        # A distribution, never collapsed into one "rating": the spread
        # between strong-buy and hold counts is the informative part, and a
        # single averaged score would erase it.
        def _int(key):
            value = _safe_float(data.get(key))
            return int(value) if value is not None else None

        result.analyst_strong_buy  = _int("AnalystRatingStrongBuy")
        result.analyst_buy         = _int("AnalystRatingBuy")
        result.analyst_hold        = _int("AnalystRatingHold")
        result.analyst_sell        = _int("AnalystRatingSell")
        result.analyst_strong_sell = _int("AnalystRatingStrongSell")

        return result

    def get_macd(self, ticker: str) -> MacdSignal:
        """
        Fetch MACD(12, 26, 9) daily signal.
        Returns MacdSignal with crossover direction.
        """
        result = MacdSignal()

        if not self.available:
            result.error = "ALPHA_VANTAGE_KEY not configured"
            return result

        data = self._get({
            "function": "MACD",
            "symbol": ticker.upper(),
            "interval": "daily",
            "series_type": "close",
        })

        if not data or "Technical Analysis: MACD" not in data:
            result.error = "No MACD data returned"
            return result

        try:
            latest_date = sorted(data["Technical Analysis: MACD"].keys())[-1]
            entry = data["Technical Analysis: MACD"][latest_date]
            result.macd      = _safe_float(entry.get("MACD"))
            result.signal    = _safe_float(entry.get("MACD_Signal"))
            result.histogram = _safe_float(entry.get("MACD_Hist"))

            # Crossover direction from histogram sign
            if result.histogram is not None:
                if result.histogram > 0.05:
                    result.crossover = "bullish"
                elif result.histogram < -0.05:
                    result.crossover = "bearish"
                else:
                    result.crossover = "neutral"

        except Exception as e:
            result.error = str(e)

        return result
