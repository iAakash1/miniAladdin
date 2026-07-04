"""
Natural-language screening — Phase 7.

One query box that accepts anything:
  * "NVDA" / "nvidia"            → direct symbol resolution (Finnhub → FMP)
  * "AI companies", "largest banks", "stocks benefiting from lower rates"
                                  → thematic web search (Tavily → Exa) with
                                    ticker extraction from result text,
                                    validated through symbol search

Every result carries where it came from (resolver vs. which evidence
snippet mentioned it) — no black-box ranking. Cached 10 minutes.
"""

from __future__ import annotations

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


def _resolve_direct(query: str) -> list[dict[str, Any]]:
    """Ticker or company-name lookup through the symbol-search chain."""
    for vendor in (providers.fundamentals.finnhub, providers.fundamentals.fmp):
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
    return []


def _extract_candidates(text: str) -> list[str]:
    explicit = TICKER_PATTERN.findall(text)
    if explicit:
        return explicit
    return [
        token for token in BARE_TICKER.findall(text)
        if token not in COMMON_WORDS
    ]


def _validate_symbol(symbol: str) -> Optional[str]:
    """A candidate counts only if a symbol-search vendor knows it."""
    for vendor in (providers.fundamentals.finnhub, providers.fundamentals.fmp):
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
    return None


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
    """Never raises. Returns {query, mode, results[], note}."""
    normalized = query.strip()
    key = normalized.lower()
    now = time.time()
    with _lock:
        entry = _cache.get(key)
        if entry and entry[0] > now:
            return {**entry[1], "cached": True}

    results: list[dict[str, Any]]
    if LOOKS_LIKE_SYMBOL.match(normalized) or len(normalized.split()) <= 2:
        mode = "lookup"
        results = _resolve_direct(normalized)
        if not results and len(normalized.split()) >= 1 and not LOOKS_LIKE_SYMBOL.match(normalized):
            mode = "thematic"
            results = _thematic(normalized)
    else:
        mode = "thematic"
        results = _thematic(normalized)
        if not results:
            mode = "lookup"
            results = _resolve_direct(normalized)

    payload = {
        "query": normalized,
        "mode": mode,
        "results": results,
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
