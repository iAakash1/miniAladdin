"""
Slow fundamental inputs for the quality sleeve and PEAD (engine v2.1).

Sources, in order: FMP statements when a key exists, yfinance statements
as the keyless anchor. Values move quarterly → 6h cache. Every accessor
returns None on any failure — the engine treats absent data as an absent
factor, never as zero.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

from src import providers

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 6 * 3600.0
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()


def _safe_ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    try:
        if numerator is None or denominator in (None, 0):
            return None
        return float(numerator) / float(denominator)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _yoy(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    try:
        if current is None or previous in (None, 0):
            return None
        return float(current) / float(previous) - 1.0
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _from_fmp(symbol: str) -> Optional[dict[str, Any]]:
    vendor = providers.fundamentals.fmp
    if not vendor.healthy:
        return None
    try:
        income = vendor._get_json(  # noqa: SLF001 — vendor-internal HTTP core, rate-limited
            f"{vendor.BASE}/income-statement/{symbol}",
            params={"limit": 2, "apikey": vendor.api_key},
        )
        balance = vendor._get_json(
            f"{vendor.BASE}/balance-sheet-statement/{symbol}",
            params={"limit": 2, "apikey": vendor.api_key},
        )
    except Exception:  # noqa: BLE001 — chain semantics: fall through to yfinance
        return None
    if not (isinstance(income, list) and income and isinstance(balance, list) and balance):
        return None
    income_now = income[0]
    balance_now, balance_prev = balance[0], (balance[1] if len(balance) > 1 else {})
    shares_now = income_now.get("weightedAverageShsOut")
    shares_prev = income[1].get("weightedAverageShsOut") if len(income) > 1 else None
    return {
        "gross_profit_over_assets": _safe_ratio(income_now.get("grossProfit"),
                                                balance_now.get("totalAssets")),
        "net_issuance_yoy": _yoy(shares_now, shares_prev),
        "asset_growth_yoy": _yoy(balance_now.get("totalAssets"), balance_prev.get("totalAssets")),
        "source": "fmp",
    }


def _row(frame, names: list[str]) -> Optional[float]:
    """First matching row's most recent value from a yfinance statement frame."""
    try:
        for name in names:
            if name in frame.index:
                series = frame.loc[name].dropna()
                if len(series):
                    return float(series.iloc[0])
    except Exception:  # noqa: BLE001
        return None
    return None


def _row_prev(frame, names: list[str]) -> Optional[float]:
    try:
        for name in names:
            if name in frame.index:
                series = frame.loc[name].dropna()
                if len(series) >= 2:
                    return float(series.iloc[1])
    except Exception:  # noqa: BLE001
        return None
    return None


def _from_yfinance(symbol: str) -> Optional[dict[str, Any]]:
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        income = ticker.income_stmt
        balance = ticker.balance_sheet
        if income is None or balance is None or income.empty or balance.empty:
            return None
        gross_profit = _row(income, ["Gross Profit"])
        total_assets = _row(balance, ["Total Assets"])
        total_assets_prev = _row_prev(balance, ["Total Assets"])
        shares = _row(balance, ["Share Issued", "Ordinary Shares Number"])
        shares_prev = _row_prev(balance, ["Share Issued", "Ordinary Shares Number"])
        return {
            "gross_profit_over_assets": _safe_ratio(gross_profit, total_assets),
            "net_issuance_yoy": _yoy(shares, shares_prev),
            "asset_growth_yoy": _yoy(total_assets, total_assets_prev),
            "source": "yfinance",
        }
    except Exception:  # noqa: BLE001 — quality inputs are strictly optional
        logger.info("yfinance statements unavailable for %s", symbol)
        return None


def get_quality_inputs(symbol: str) -> dict[str, Any]:
    """{gross_profit_over_assets, net_issuance_yoy, asset_growth_yoy, source} — Nones on failure."""
    symbol = symbol.upper()
    key = f"quality:{symbol}"
    now = time.time()
    with _lock:
        entry = _cache.get(key)
        if entry and entry[0] > now:
            return entry[1]
    data = _from_fmp(symbol) or _from_yfinance(symbol) or {
        "gross_profit_over_assets": None, "net_issuance_yoy": None,
        "asset_growth_yoy": None, "source": None,
    }
    with _lock:
        _cache[key] = (now + CACHE_TTL_SECONDS, data)
    return data


def get_pead_inputs(symbol: str) -> dict[str, Any]:
    """Most recent PAST earnings surprise: {surprise_pct, days_since} or Nones.
    Conservative by design — missing surprise data means no PEAD factor."""
    symbol = symbol.upper()
    key = f"pead:{symbol}"
    now = time.time()
    with _lock:
        entry = _cache.get(key)
        if entry and entry[0] > now:
            return entry[1]

    result: dict[str, Any] = {"surprise_pct": None, "days_since": None}
    try:
        import pandas as pd
        import yfinance as yf

        dates = yf.Ticker(symbol).earnings_dates
        if dates is not None and not dates.empty and "Surprise(%)" in dates.columns:
            past = dates[dates.index.tz_localize(None) <= pd.Timestamp.utcnow().tz_localize(None)]
            past = past.dropna(subset=["Surprise(%)"])
            if not past.empty:
                latest = past.index.max()
                result = {
                    "surprise_pct": float(past.loc[latest, "Surprise(%)"]),
                    "days_since": int((pd.Timestamp.utcnow().tz_localize(None)
                                       - latest.tz_localize(None)).days),
                }
    except Exception:  # noqa: BLE001
        logger.info("earnings surprise unavailable for %s", symbol)

    with _lock:
        _cache[key] = (now + CACHE_TTL_SECONDS, result)
    return result


def reset_for_tests() -> None:
    _cache.clear()
