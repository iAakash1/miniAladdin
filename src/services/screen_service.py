"""
Natural-language screening — Phase 7, hardened in the search-fix pass.

One query box that accepts anything:
  * "NVDA" / "nvidia"            → direct symbol resolution (Finnhub → FMP
                                    → Yahoo search → the keyless
                                    WELL_KNOWN_SYMBOLS anchor)
  * "AI companies", "largest banks", "stocks benefiting from lower rates"
                                  → thematic web search (Tavily → Exa) with
                                    ticker extraction from result text,
                                    validated through symbol search

A miss on one strategy always retries the other (see screen()) — a
symbol-shaped query that fails direct resolution still gets a thematic
attempt, not a dead end. That retry was previously one-directional, which
is the root cause behind a real production bug: "NVDA" returned nothing
while every keyed symbol-search vendor was unhealthy, even though NVDA is
about as unambiguous a ticker as exists. If nothing resolves at all,
_did_you_mean() offers fuzzy suggestions instead of leaving the user with
nothing.

Every result carries where it came from (resolver vs. which evidence
snippet mentioned it) — no black-box ranking. Cached 10 minutes.
"""

from __future__ import annotations

import difflib
import logging
import re
import threading
import time
from typing import Any, Optional

from src import providers

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 600.0
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()

MAX_RESULTS = 10

# $TSLA or (NASDAQ: TSLA) or (NYSE:BRK.B) style mentions in article text
TICKER_PATTERN = re.compile(
    r"(?:\$|\((?:NYSE|NASDAQ|AMEX)[:\s]+)([A-Z]{1,5}(?:\.[A-Z])?)\)?"
)
# Bare uppercase tokens that are plausibly tickers when set in list-like text
BARE_TICKER = re.compile(r"\b([A-Z]{2,5})\b")
COMMON_WORDS = {
    "AI", "CEO", "CFO", "IPO", "ETF", "GDP", "CPI", "PPI", "USA", "USD", "FED",
    "THE", "AND", "FOR", "NYSE", "NASDAQ", "AMEX", "SEC", "TOP", "BEST", "NEW",
    "PE", "EPS", "US", "UK", "EU", "Q1", "Q2", "Q3", "Q4", "YOY", "ATH",
}

LOOKS_LIKE_SYMBOL = re.compile(r"^[A-Za-z.^-]{1,6}$")

# Keyless, zero-latency anchor — the search-layer equivalent of the
# yfinance/Yahoo-RSS anchors that already guarantee every other provider
# chain resolves (README: "vendors without keys self-disable; the keyless
# yfinance/Yahoo RSS anchors guarantee every chain resolves"). Search had no
# such anchor: when every keyed symbol-search vendor was unhealthy, a query
# for a ticker as unambiguous as NVDA still came back empty. Deliberately
# small — liquid large caps + the most common ETFs — this exists to make an
# outage survivable, not to replace live vendor data.
WELL_KNOWN_SYMBOLS: dict[str, str] = {
    "AAPL": "Apple Inc.", "MSFT": "Microsoft Corporation", "GOOGL": "Alphabet Inc.",
    "GOOG": "Alphabet Inc.", "AMZN": "Amazon.com, Inc.", "NVDA": "NVIDIA Corporation",
    "META": "Meta Platforms, Inc.", "TSLA": "Tesla, Inc.", "BRK.B": "Berkshire Hathaway Inc.",
    "AVGO": "Broadcom Inc.", "JPM": "JPMorgan Chase & Co.", "V": "Visa Inc.",
    "MA": "Mastercard Incorporated", "UNH": "UnitedHealth Group Incorporated",
    "JNJ": "Johnson & Johnson", "WMT": "Walmart Inc.", "PG": "Procter & Gamble Company",
    "HD": "Home Depot, Inc.", "XOM": "Exxon Mobil Corporation", "CVX": "Chevron Corporation",
    "KO": "Coca-Cola Company", "PEP": "PepsiCo, Inc.", "ABBV": "AbbVie Inc.",
    "MRK": "Merck & Co., Inc.", "COST": "Costco Wholesale Corporation", "ADBE": "Adobe Inc.",
    "CRM": "Salesforce, Inc.", "AMD": "Advanced Micro Devices, Inc.", "INTC": "Intel Corporation",
    "ORCL": "Oracle Corporation", "CSCO": "Cisco Systems, Inc.", "NFLX": "Netflix, Inc.",
    "DIS": "Walt Disney Company", "BAC": "Bank of America Corporation",
    "WFC": "Wells Fargo & Company", "GS": "Goldman Sachs Group, Inc.", "MS": "Morgan Stanley",
    "IBM": "International Business Machines Corporation", "QCOM": "Qualcomm Incorporated",
    "TXN": "Texas Instruments Incorporated", "NKE": "Nike, Inc.", "MCD": "McDonald's Corporation",
    "SBUX": "Starbucks Corporation", "LOW": "Lowe's Companies, Inc.",
    "UPS": "United Parcel Service, Inc.", "BA": "Boeing Company", "CAT": "Caterpillar Inc.",
    "GE": "GE Aerospace", "F": "Ford Motor Company", "GM": "General Motors Company",
    "T": "AT&T Inc.", "VZ": "Verizon Communications Inc.", "PFE": "Pfizer Inc.",
    "LLY": "Eli Lilly and Company", "ABT": "Abbott Laboratories",
    "TMO": "Thermo Fisher Scientific Inc.", "ACN": "Accenture plc", "LIN": "Linde plc",
    "PM": "Philip Morris International Inc.", "UNP": "Union Pacific Corporation",
    "RTX": "RTX Corporation", "HON": "Honeywell International Inc.", "SPGI": "S&P Global Inc.",
    "BLK": "BlackRock, Inc.", "AXP": "American Express Company", "PYPL": "PayPal Holdings, Inc.",
    "SHOP": "Shopify Inc.", "UBER": "Uber Technologies, Inc.", "ABNB": "Airbnb, Inc.",
    "SNOW": "Snowflake Inc.", "PLTR": "Palantir Technologies Inc.", "SQ": "Block, Inc.",
    "COIN": "Coinbase Global, Inc.", "SMCI": "Super Micro Computer, Inc.",
    "ARM": "Arm Holdings plc", "MU": "Micron Technology, Inc.", "AMAT": "Applied Materials, Inc.",
    "LRCX": "Lam Research Corporation", "NOW": "ServiceNow, Inc.",
    "PANW": "Palo Alto Networks, Inc.", "CRWD": "CrowdStrike Holdings, Inc.",
    # ETFs
    "SPY": "SPDR S&P 500 ETF Trust", "QQQ": "Invesco QQQ Trust",
    "VOO": "Vanguard S&P 500 ETF", "VTI": "Vanguard Total Stock Market ETF",
    "IWM": "iShares Russell 2000 ETF", "DIA": "SPDR Dow Jones Industrial Average ETF Trust",
    "GLD": "SPDR Gold Shares", "SLV": "iShares Silver Trust", "ARKK": "ARK Innovation ETF",
    "XLF": "Financial Select Sector SPDR Fund", "XLK": "Technology Select Sector SPDR Fund",
    "XLE": "Energy Select Sector SPDR Fund", "XLV": "Health Care Select Sector SPDR Fund",
    "TLT": "iShares 20+ Year Treasury Bond ETF",
    "HYG": "iShares iBoxx $ High Yield Corporate Bond ETF",
    "EEM": "iShares MSCI Emerging Markets ETF", "VXUS": "Vanguard Total International Stock ETF",
    "VEA": "Vanguard FTSE Developed Markets ETF",
}


def _resolve_well_known(query: str) -> list[dict[str, Any]]:
    """Exact-symbol or name-substring hit against the static anchor table.
    Zero network calls — the last step of _resolve_direct's waterfall."""
    upper = query.upper()
    if upper in WELL_KNOWN_SYMBOLS:
        return [{
            "symbol": upper, "name": WELL_KNOWN_SYMBOLS[upper],
            "via": "known symbol", "snippet": None, "url": None,
        }]
    lowered = query.lower()
    hits = [
        {"symbol": symbol, "name": name, "via": "known symbol", "snippet": None, "url": None}
        for symbol, name in WELL_KNOWN_SYMBOLS.items()
        if lowered in name.lower()
    ]
    return hits[:MAX_RESULTS]


def _did_you_mean(query: str) -> list[dict[str, Any]]:
    """Fuzzy last resort so a query never fully dead-ends even when every
    live vendor is unhealthy and the thematic web search also comes up
    empty. Matches typos against the anchor table's symbols and names, so
    e.g. "NVDAA" or a misspelled company name still points somewhere
    instead of a flat dead end."""
    labels: dict[str, str] = {}
    for symbol, name in WELL_KNOWN_SYMBOLS.items():
        labels[symbol.lower()] = symbol
        labels[name.lower()] = symbol
    close = difflib.get_close_matches(query.lower(), labels.keys(), n=8, cutoff=0.6)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for label in close:
        symbol = labels[label]
        if symbol in seen:
            continue
        seen.add(symbol)
        out.append({
            "symbol": symbol, "name": WELL_KNOWN_SYMBOLS[symbol],
            "via": "did you mean", "snippet": None, "url": None,
        })
        if len(out) >= 5:
            break
    return out


def _resolve_direct(query: str) -> list[dict[str, Any]]:
    """Ticker or company-name lookup through the symbol-search chain."""
    for vendor in (providers.fundamentals.finnhub, providers.fundamentals.fmp,
                   providers.market_data.yfinance):
        if not vendor.healthy:
            continue
        try:
            rows = vendor.search_symbols(query, limit=MAX_RESULTS)
        except Exception:  # noqa: BLE001 — chain semantics, next vendor
            logger.info("symbol search failed on %s", vendor.NAME)
            continue
        if rows:
            return [
                {"symbol": row["symbol"], "name": row["name"],
                 "via": f"{vendor.NAME} symbol search", "snippet": None, "url": None}
                for row in rows
            ]
    # Every keyed/live vendor missed or is unhealthy — the keyless anchor
    # still resolves unambiguous large-cap tickers like NVDA. This is the
    # fix for "NVDA -> Nothing Found" while NVDA was already sitting in the
    # user's own portfolio.
    return _resolve_well_known(query)


def _extract_candidates(text: str) -> list[str]:
    explicit = TICKER_PATTERN.findall(text)
    if explicit:
        return explicit
    return [
        token for token in BARE_TICKER.findall(text)
        if token not in COMMON_WORDS
    ]


def _validate_symbol(symbol: str) -> Optional[str]:
    """A candidate counts only if a symbol-search vendor knows it (or the
    keyless well-known anchor does — see _resolve_direct for why that
    fallback exists)."""
    for vendor in (providers.fundamentals.finnhub, providers.fundamentals.fmp,
                   providers.market_data.yfinance):
        if not vendor.healthy:
            continue
        try:
            rows = vendor.search_symbols(symbol, limit=3)
        except Exception:  # noqa: BLE001
            continue
        if rows:
            for row in rows:
                if row["symbol"].upper() == symbol.upper():
                    return row["name"]
    return WELL_KNOWN_SYMBOLS.get(symbol.upper())


def _thematic(query: str) -> list[dict[str, Any]]:
    """Web search → ticker extraction → validation. Attribution preserved."""
    search_result = providers.search.search(f"{query} stocks tickers", limit=8)
    if not search_result.ok or not search_result.data:
        return []

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in search_result.data:
        text = f"{row.title} {row.snippet}"
        for candidate in _extract_candidates(text):
            symbol = candidate.upper()
            if symbol in seen or len(out) >= MAX_RESULTS * 2:
                continue
            seen.add(symbol)
            name = _validate_symbol(symbol)
            if name is None:
                continue
            out.append({
                "symbol": symbol,
                "name": name,
                "via": f"mentioned by {row.url.split('/')[2] if '://' in row.url else 'web'}",
                "snippet": (row.title or row.snippet)[:160],
                "url": row.url,
            })
            if len(out) >= MAX_RESULTS:
                return out
    return out


def screen(query: str) -> dict[str, Any]:
    """Never raises, never fully dead-ends. Returns
    {query, mode, results[], suggestions[], note, cached}."""
    normalized = query.strip()
    key = normalized.lower()
    now = time.time()
    with _lock:
        entry = _cache.get(key)
        if entry and entry[0] > now:
            return {**entry[1], "cached": True}

    symbol_shaped = bool(LOOKS_LIKE_SYMBOL.match(normalized))
    mode = "lookup" if (symbol_shaped or len(normalized.split()) <= 2) else "thematic"
    results = _resolve_direct(normalized) if mode == "lookup" else _thematic(normalized)

    # A miss on one strategy always gets the other retried — a symbol-shaped
    # query that fails direct resolution (e.g. every vendor unhealthy at
    # once) still deserves a thematic attempt, and a thematic miss still
    # deserves a direct lookup. The previous version only retried thematic
    # when the query did *not* look like a symbol, so a direct-resolution
    # miss on an unambiguous real ticker was final — that asymmetric guard
    # is the root cause behind "NVDA -> Nothing Found" and is gone now.
    if not results:
        mode = "thematic" if mode == "lookup" else "lookup"
        results = _thematic(normalized) if mode == "thematic" else _resolve_direct(normalized)

    suggestions = _did_you_mean(normalized) if not results else []

    payload = {
        "query": normalized,
        "mode": mode,
        "results": results,
        "suggestions": suggestions,
        "note": (
            "Thematic results are tickers mentioned in ranked web sources and "
            "validated against symbol databases — a research starting point, "
            "not a screened universe."
            if mode == "thematic" else
            "Direct symbol-database lookup."
        ),
        "cached": False,
    }
    if results:
        with _lock:
            _cache[key] = (now + CACHE_TTL_SECONDS, payload)
    return payload


def reset_for_tests() -> None:
    _cache.clear()
