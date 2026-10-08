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

from src.services.cache_policy import put_ttl

from src import providers

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 600.0
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
MAX_CACHE_ENTRIES = 128
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


# A root and one share-class letter, however a person or a vendor spells it:
# "BRK B", "BRK/B", "BRK-B", "BRK.B".
_SHARE_CLASS_SPELLING = re.compile(r"^([A-Za-z]{1,5})([\s./-])([A-Za-z])$")


#: "BRKB" for BRK.B: the dotted anchor symbols with the dot removed. A symbol database matches the
#: concatenated form against fund names ("Direxion Daily BRKB Bull"), so without this the leveraged
#: fund outranks Berkshire for a query a person plainly meant as the share class.
_UNSEPARATED_SHARE_CLASSES = {symbol.replace(".", ""): symbol for symbol in WELL_KNOWN_SYMBOLS if "." in symbol}


def _share_class(query: str) -> Optional[tuple[str, str]]:
    """(root, class letter) when the query is one security's share class, however spelled."""
    typed = query.strip()
    match = _SHARE_CLASS_SPELLING.match(typed)
    if match:
        return match.group(1).upper(), match.group(3).upper()
    alias = _UNSEPARATED_SHARE_CLASSES.get(typed.upper())
    if alias:
        root, letter = alias.split(".")
        return root, letter
    return None


def _lookup_spellings(query: str) -> list[str]:
    """The strings to try, in order, for one query.

    Symbol databases do not agree on how a share class is written — Berkshire's
    B shares are BRK.B at one vendor and BRK-B at another — and people type a
    third form with a space. Passing "BRK B" through verbatim leaves the answer
    to each vendor's fuzziness, which is how a plain, unambiguous symbol came
    back as "nothing found".

    Spaced, slashed and concatenated forms are not symbols at any vendor, and
    "BRK-B" and "BRK.B" are the same security under two spellings, so for a
    share class the dotted spelling is always tried first, then the hyphenated
    one, then the query as typed. Which spelling answers decides which vendors
    serve the security afterwards, so leaving it to the order a person typed
    it gave one company two cache entries and two slightly different quotes.
    The hyphenated spelling stays as the fallback because some sources know
    only that form. Anything else is not a share class and is searched exactly
    as typed — this adds vendor calls only for queries of the one shape that
    needs them.
    """
    typed = query.strip()
    share = _share_class(typed)
    if not share:
        return [typed]
    root, letter = share
    spellings = [f"{root}.{letter}", f"{root}-{letter}"]
    if typed.upper() not in spellings:
        spellings.append(typed)
    return spellings


def _resolve_well_known(query: str) -> list[dict[str, Any]]:
    """Exact-symbol or name-substring hit against the static anchor table.
    Zero network calls — the last step of _resolve_direct's waterfall."""
    for spelling in _lookup_spellings(query):
        upper = spelling.upper()
        if upper in WELL_KNOWN_SYMBOLS:
            return [{
                "symbol": upper, "name": WELL_KNOWN_SYMBOLS[upper],
                "via": "known symbol", "snippet": None, "url": None,
            }]
    upper = query.upper()
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


#: Words that describe the kind of question rather than its subject.
_GENERIC_WORDS = frozenset({
    "stock", "stocks", "ticker", "tickers", "company", "companies", "share", "shares", "best", "top",
    "the", "and", "for", "with", "from", "that", "are", "how", "what", "which", "most", "largest",
    "biggest", "list", "of", "to", "in", "on", "by", "watch", "buy", "invest", "investing",
})


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]{2,}", text.lower())


def _subject_terms(query: str) -> list[str]:
    """The query's own terms, when it mixes them with words about the kind of question.

    "tesla stocks" has a subject (tesla) and a frame (stocks); "TSLA" and "best stocks" have
    only one of the two, and for those there is nothing to hold a vendor's answer against.
    """
    words = _words(query)
    subject = [w for w in words if w not in _GENERIC_WORDS]
    return subject if subject and len(subject) < len(words) else []


def _row_is_about(terms: list[str], row: dict[str, Any]) -> bool:
    """Whether a symbol-search row names any of the terms, as a word or the start of one.

    A symbol database matches the frame words of a description against fund names, so
    "qzxwqzxw stocks" returned the largest stock funds there are, none of which has
    anything to do with the first word. A row must carry one of the query's own terms
    in its symbol or its name ("tech" for "Technology Select Sector"; "dividend" for
    "Dividend Yield"), or it is not an answer to that query.
    """
    tokens = _words(f"{row.get('symbol') or ''} {row.get('name') or ''}")
    return any(
        term == token or (min(len(term), len(token)) >= 4 and (token.startswith(term) or term.startswith(token)))
        for term in terms for token in tokens
    )


def _tidy(rows: list[dict[str, Any]], share: Optional[tuple[str, str]]) -> list[dict[str, Any]]:
    """One row per symbol, and for a share class the exact listing alone.

    Vendors list one symbol more than once (a cross-listing under the same
    ticker, a name spelled two ways), so the same security appeared twice in
    the results. And a share class searched as "BRK-B" came back with a
    leveraged fund and a London product beneath it: when the security itself is
    in the answer, text-similar instruments are noise, so they are dropped.
    """
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            unique.append(row)
    if share:
        root, letter = share
        spellings = (f"{root}.{letter}", f"{root}-{letter}")
        exact = [row for row in unique if str(row["symbol"]).upper() in spellings]
        if exact:
            # Both spellings of the same security: keep the dotted one.
            exact.sort(key=lambda row: str(row["symbol"]).upper() != spellings[0])
            return exact[:1]
    return unique


def _resolve_direct(query: str) -> list[dict[str, Any]]:
    """Ticker or company-name lookup through the symbol-search chain."""
    share = _share_class(query)
    subject = _subject_terms(query)
    for spelling in _lookup_spellings(query):
        for vendor in (providers.fundamentals.finnhub, providers.fundamentals.fmp,
                       providers.market_data.yfinance):
            if not vendor.healthy:
                continue
            try:
                rows = vendor.search_symbols(spelling, limit=MAX_RESULTS)
            except Exception:  # noqa: BLE001 — chain semantics, next vendor
                logger.info("symbol search failed on %s", vendor.NAME)
                continue
            rows = _tidy(rows or [], share)
            if subject:
                rows = [row for row in rows if _row_is_about(subject, row)]
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


def _results_are_about(query: str, rows: list[Any]) -> bool:
    """Whether the pages a web search returned have anything to do with the query.

    A search engine asked for "qzxwqzxw stocks tickers" ignores the word it has
    never seen and answers with the best-ranked stock pages there are; every
    ticker extracted from those pages then looked like an answer to the query.
    The query's own distinctive terms must appear somewhere in what came back.
    A query made only of generic words has nothing to check.
    """
    terms = [t for t in _words(query) if t not in _GENERIC_WORDS]
    if not terms:
        return True
    text = " ".join(f"{row.title} {row.snippet} {row.url}" for row in rows).lower()
    return any(term in text for term in terms)


def _thematic(query: str) -> list[dict[str, Any]]:
    """Web search → ticker extraction → validation. Attribution preserved."""
    search_result = providers.search.search(f"{query} stocks tickers", limit=8)
    if not search_result.ok or not search_result.data:
        return []
    if not _results_are_about(query, search_result.data):
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
            put_ttl(_cache, key, now + CACHE_TTL_SECONDS, payload,
                    max_entries=MAX_CACHE_ENTRIES, now=now)
    return payload


def reset_for_tests() -> None:
    _cache.clear()
