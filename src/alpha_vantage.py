"""
OmniSignal Alpha Vantage Integration
Fetches fundamental data and MACD signal to enrich technical analysis.

Free tier: 25 requests/day, 5/minute.
Strategy: 1 OVERVIEW call (fundamentals) + 1 MACD call per research request.
"""

from __future__ import annotations

import os
import time
from typing import Optional
from dataclasses import dataclass, field

import requests
from dotenv import load_dotenv

load_dotenv()

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
                print(f"[AlphaVantage] {msg[:80]}")
                return None
            return data
        except Exception as e:
            print(f"[AlphaVantage] Request failed: {e}")
            return None

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
