"""
Market Intelligence Dashboard — "what is happening in the market?"

Every number is real and sourced through the provider layer:
  * Macro board: FRED series (current / previous / change / trend / updated /
    one-line explanation per indicator).
  * Breadth: index + VIX quotes, and a computable breadth score — the share
    of the 11 SPDR sector ETFs trading above their 50-day average. (True
    advance/decline counts and put/call ratios have no free source; rather
    than fake them, we substitute a documented, computable proxy.)
  * Sectors: 11 SPDR ETFs — strength (21d), momentum (63d), volatility,
    verdict from the v2 scoring cut points. Constituent winners/losers need
    membership data with no free source — omitted, not invented.
  * Events: static public calendars (FOMC — Fed; CPI/PPI/Jobs — BLS release
    schedule) with countdowns and *measured* historical SPY volatility around
    each event type. ISM/PMI are proprietary (ISM) and therefore absent.

Assembled response is cached for 15 minutes.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timezone
from typing import Any, Optional

from src import providers
from src.scoring.engine import map_verdict
from src.scoring.fomc_calendar import FOMC_DECISION_DATES

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 900.0
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()

# ── FRED macro board (id, label, unit, explanation) ──────────────────────────

MACRO_SERIES: list[dict[str, str]] = [
    {"id": "FEDFUNDS", "label": "Federal Funds Rate", "unit": "%",
     "explain": "The Fed's policy rate — the anchor for all US borrowing costs."},
    {"id": "DGS10", "label": "10-Year Treasury", "unit": "%",
     "explain": "Long-end yield: growth and inflation expectations plus term premium."},
    {"id": "DGS2", "label": "2-Year Treasury", "unit": "%",
     "explain": "Short-end yield: the market's read on Fed policy over two years."},
    {"id": "T10Y2Y", "label": "10Y–2Y Spread", "unit": "%",
     "explain": "Yield-curve slope. Inversion (below zero) has preceded recessions."},
    {"id": "DFII10", "label": "10-Year Real Yield", "unit": "%",
     "explain": "Inflation-adjusted yield (TIPS). The true cost of capital."},
    {"id": "DTWEXBGS", "label": "Dollar Index (Broad)", "unit": "",
     "explain": "Trade-weighted dollar. Strength tightens global financial conditions."},
    {"id": "CPIAUCSL", "label": "CPI", "unit": "index", "yoy": "true",
     "explain": "Headline consumer inflation, shown year-over-year."},
    {"id": "CPILFESL", "label": "Core CPI", "unit": "index", "yoy": "true",
     "explain": "Inflation excluding food and energy — the Fed's cleaner read."},
    {"id": "PPIACO", "label": "PPI", "unit": "index", "yoy": "true",
     "explain": "Producer prices — pipeline pressure that reaches consumers later."},
    {"id": "UNRATE", "label": "Unemployment", "unit": "%",
     "explain": "Labor-market slack. Rising unemployment usually precedes easing."},
    {"id": "A191RL1Q225SBEA", "label": "GDP Growth (q/q ann.)", "unit": "%",
     "explain": "Output growth, quarterly annualized."},
    {"id": "RSAFS", "label": "Retail Sales", "unit": "index", "yoy": "true",
     "explain": "Consumer spending pulse, shown year-over-year."},
    {"id": "UMCSENT", "label": "Consumer Sentiment", "unit": "",
     "explain": "University of Michigan survey — households' mood about the economy."},
    {"id": "HOUST", "label": "Housing Starts", "unit": "k",
     "explain": "New residential construction — the most rate-sensitive activity gauge."},
]

SECTOR_ETFS: list[tuple[str, str]] = [
    ("XLK", "Technology"), ("XLV", "Healthcare"), ("XLE", "Energy"),
    ("XLF", "Financials"), ("XLU", "Utilities"), ("XLI", "Industrials"),
    ("XLP", "Consumer Defensive"), ("XLY", "Consumer Cyclical"),
    ("XLC", "Communication"), ("XLB", "Materials"), ("XLRE", "Real Estate"),
]

INDEX_TICKERS = ["SPY", "QQQ", "DIA", "IWM", "^VIX"]

# BLS 2026 release schedule (public: bls.gov/schedule/news_release) — H2 2026.
# Static like the FOMC calendar; refresh annually.
BLS_EVENTS_2026: list[tuple[str, str, str]] = [
    ("2026-07-14", "CPI", "June CPI release"),
    ("2026-07-16", "PPI", "June PPI release"),
    ("2026-08-07", "Jobs Report", "July employment situation"),
    ("2026-08-12", "CPI", "July CPI release"),
    ("2026-08-14", "PPI", "July PPI release"),
    ("2026-09-04", "Jobs Report", "August employment situation"),
    ("2026-09-11", "CPI", "August CPI release"),
    ("2026-09-16", "PPI", "August PPI release"),
    ("2026-10-02", "Jobs Report", "September employment situation"),
    ("2026-10-14", "CPI", "September CPI release"),
    ("2026-10-16", "PPI", "September PPI release"),
    ("2026-11-06", "Jobs Report", "October employment situation"),
    ("2026-11-12", "CPI", "October CPI release"),
    ("2026-11-17", "PPI", "October PPI release"),
    ("2026-12-04", "Jobs Report", "November employment situation"),
    ("2026-12-10", "CPI", "November CPI release"),
    ("2026-12-15", "PPI", "November PPI release"),
]

EVENT_IMPORTANCE = {"FOMC": "high", "CPI": "high", "Jobs Report": "high", "PPI": "medium", "GDP": "medium"}


# ── Macro board ───────────────────────────────────────────────────────────────

def _macro_card(meta: dict[str, str]) -> Optional[dict[str, Any]]:
    result = providers.macro.get_series_snapshot(meta["id"], count=15)
    if not result.ok or not result.data:
        return None
    observations = result.data

    yoy = meta.get("yoy") == "true"
    if yoy and len(observations) >= 14:
        # Year-over-year % change for monthly index series
        def yoy_at(offset: int) -> Optional[float]:
            if len(observations) < 13 + offset:
                return None
            newest = observations[-1 - offset][1]
            year_ago = observations[-13 - offset][1]
            return round((newest / year_ago - 1) * 100, 2) if year_ago else None

        current, previous = yoy_at(0), yoy_at(1)
        unit = "% y/y"
        trend = [yoy_at(i) for i in range(5, -1, -1)]
        trend = [value for value in trend if value is not None]
    else:
        current = round(observations[-1][1], 2)
        previous = round(observations[-2][1], 2) if len(observations) >= 2 else None
        unit = meta["unit"]
        trend = [round(value, 2) for _, value in observations[-6:]]

    if current is None:
        return None
    change = round(current - previous, 2) if previous is not None else None
    return {
        "id": meta["id"],
        "label": meta["label"],
        "value": current,
        "previous": previous,
        "change": change,
        "direction": ("up" if change > 0 else "down" if change < 0 else "flat") if change is not None else "flat",
        "unit": unit,
        "trend": trend,
        "updated": observations[-1][0],
        "explain": meta["explain"],
        "source": result.source,
    }


def _macro_board() -> dict[str, Any]:
    cards = []
    for meta in MACRO_SERIES:
        try:
            card = _macro_card(meta)
            if card:
                cards.append(card)
        except Exception:  # noqa: BLE001 — one bad series never kills the board
            logger.exception("macro card failed: %s", meta["id"])

    macro_result = providers.macro.get_macro()
    regime: dict[str, Any] = {"available": macro_result.ok}
    if macro_result.ok:
        snapshot = macro_result.data
        from src.models import MacroIndicators
        from src.risk_analysis import OmniSignalRiskEngine

        assessment = OmniSignalRiskEngine().calculate_multiplier(MacroIndicators(
            yield_spread=snapshot.yield_spread or 0.0,
            inflation_rate=snapshot.inflation_rate or 0.0,
            fed_funds_rate=snapshot.fed_funds_rate,
        ))
        regime.update({
            "risk_multiplier": assessment.risk_multiplier,
            "status": assessment.status.value,
            "yield_curve": "inverted" if assessment.yield_curve_inverted else "normal",
            "recession_warning": assessment.recession_warning,
            "explain": "SRM composes curve inversion (+0.3), CPI above 4% (+0.2) and "
                       "Fed funds above 5% (+0.1) into one dampening multiplier.",
        })
    return {"cards": cards, "regime": regime, "note": "ISM/PMI are proprietary surveys with no free source and are intentionally absent."}


# ── Breadth & sectors ─────────────────────────────────────────────────────────

def _pct_change(bars: list, days: int) -> Optional[float]:
    closes = [bar.close for bar in bars]
    if len(closes) <= days:
        return None
    base = closes[-1 - days]
    return round((closes[-1] / base - 1) * 100, 2) if base else None


def _sector_row(symbol: str, name: str) -> Optional[dict[str, Any]]:
    result = providers.market_data.get_series(symbol, "1y")
    if not result.ok or len(result.data.bars) < 70:
        return None
    bars = result.data.bars
    closes = [bar.close for bar in bars]
    price = closes[-1]
    ma50 = sum(closes[-50:]) / 50
    daily = [(closes[i] / closes[i - 1] - 1) for i in range(max(1, len(closes) - 63), len(closes))]
    mean = sum(daily) / len(daily)
    volatility = (sum((r - mean) ** 2 for r in daily) / max(1, len(daily) - 1)) ** 0.5 * (252 ** 0.5)
    strength = _pct_change(bars, 21)
    momentum = _pct_change(bars, 63)
    composite = ((strength or 0) / 100 * 2 + (momentum or 0) / 100) / 2  # simple, documented blend
    return {
        "symbol": symbol,
        "name": name,
        "price": round(price, 2),
        "strength_21d": strength,
        "momentum_63d": momentum,
        "volatility": round(volatility * 100, 1),
        "above_50d": price > ma50,
        "verdict": map_verdict(max(-0.99, min(0.99, composite))).value,
        "source": result.source,
    }


def _breadth_and_sectors() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    sectors = []
    for symbol, name in SECTOR_ETFS:
        try:
            row = _sector_row(symbol, name)
            if row:
                sectors.append(row)
        except Exception:  # noqa: BLE001
            logger.exception("sector row failed: %s", symbol)
    sectors.sort(key=lambda row: row.get("strength_21d") or -999, reverse=True)

    indexes = []
    for symbol in INDEX_TICKERS:
        try:
            series = providers.market_data.get_series(symbol, "3mo")
            if series.ok and len(series.data.bars) >= 6:
                bars = series.data.bars
                indexes.append({
                    "symbol": symbol.replace("^", ""),
                    "price": round(bars[-1].close, 2),
                    "change_1d": _pct_change(bars, 1),
                    "change_1w": _pct_change(bars, 5),
                    "source": series.source,
                })
        except Exception:  # noqa: BLE001
            logger.exception("index quote failed: %s", symbol)

    above = sum(1 for row in sectors if row["above_50d"])
    breadth_score = round(above / len(sectors) * 100) if sectors else None
    breadth = {
        "indexes": indexes,
        "sectors_above_50d": above,
        "sector_count": len(sectors),
        "breadth_score": breadth_score,
        "explain": "Breadth score = share of the 11 SPDR sector ETFs above their 50-day "
                   "average. Advance/decline counts and put/call ratios have no free "
                   "data source, so this computable proxy is used instead of fake numbers.",
        "leadership": sectors[0]["name"] if sectors else None,
        "laggard": sectors[-1]["name"] if sectors else None,
    }
    return breadth, sectors


# ── Events ────────────────────────────────────────────────────────────────────

def _event_volatility(spy_bars: list, event_dates: list[date], window: int = 1) -> Optional[float]:
    """Mean absolute SPY move (%) on historical event days — measured, not asserted."""
    if not spy_bars:
        return None
    by_date = {bar.date: index for index, bar in enumerate(spy_bars)}
    moves = []
    for event_day in event_dates:
        index = by_date.get(event_day.isoformat())
        if index and index >= window:
            prev_close = spy_bars[index - window].close
            if prev_close:
                moves.append(abs(spy_bars[index].close / prev_close - 1) * 100)
    return round(sum(moves) / len(moves), 2) if moves else None


def _events(today: date) -> list[dict[str, Any]]:
    spy = providers.market_data.get_series("SPY", "1y")
    spy_bars = spy.data.bars if spy.ok else []

    past_fomc = [d for d in FOMC_DECISION_DATES if d < today]
    fomc_vol = _event_volatility(spy_bars, past_fomc)

    events: list[dict[str, Any]] = []
    for decision in FOMC_DECISION_DATES:
        if decision >= today:
            events.append({
                "date": decision.isoformat(), "type": "FOMC",
                "title": "FOMC rate decision",
                "importance": EVENT_IMPORTANCE["FOMC"],
                "days_away": (decision - today).days,
                "historical_move": fomc_vol,
                "explain": "Historical move = mean absolute SPY change on past decision days this year.",
            })
    for date_str, kind, title in BLS_EVENTS_2026:
        event_day = date.fromisoformat(date_str)
        if event_day >= today:
            events.append({
                "date": date_str, "type": kind, "title": title,
                "importance": EVENT_IMPORTANCE.get(kind, "medium"),
                "days_away": (event_day - today).days,
                "historical_move": None,
                "explain": "BLS release schedule (bls.gov).",
            })
    events.sort(key=lambda event: event["date"])
    return events[:10]


# ── Assembly ──────────────────────────────────────────────────────────────────

def get_dashboard() -> dict[str, Any]:
    now = time.time()
    with _lock:
        entry = _cache.get("dashboard")
        if entry and entry[0] > now:
            return {**entry[1], "cached": True}

    started = time.time()
    breadth, sectors = _breadth_and_sectors()
    payload = {
        "macro": _macro_board(),
        "breadth": breadth,
        "sectors": sectors,
        "events": _events(datetime.now(timezone.utc).date()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cached": False,
    }
    logger.info("dashboard assembled in %.1fs", time.time() - started)
    with _lock:
        _cache["dashboard"] = (now + CACHE_TTL_SECONDS, payload)
    return payload


def reset_for_tests() -> None:
    _cache.clear()
