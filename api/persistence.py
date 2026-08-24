"""
Persistence REST API — watchlists, portfolio, analysis history, saved
reports, preferences, profile.

Every endpoint requires a verified Clerk session token and is scoped to that
user inside the repositories. When Supabase is not configured the endpoints
answer 503 — analysis itself never depends on this router.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src import providers
from src.providers.parallel import map_concurrent
from src.services import database
from src.services import portfolio_intelligence
from src.services.clerk_auth import require_clerk_user
from src.services.database.repositories import (
    AnalysisRepository,
    SessionsRepository,
    PortfolioRepository,
    PreferencesRepository,
    ProfilesRepository,
    WatchlistsRepository,
)

logger = logging.getLogger("omnisignal.persistence")

router = APIRouter(prefix="/api", tags=["persistence"])


def _client() -> Any:
    client = database.get_client()
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Persistence is not configured on this server — analysis still works.",
        )
    return client


# ── request bodies ───────────────────────────────────────────────────────────

class ProfileSyncBody(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None


class WatchlistCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    tickers: list[str] = Field(default_factory=list, max_length=25)


class WatchlistRenameBody(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class TickerBody(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)


class PositionCreateBody(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)
    shares: float = Field(gt=0)
    average_price: float = Field(ge=0)


class PositionPatchBody(BaseModel):
    shares: Optional[float] = Field(default=None, gt=0)
    average_price: Optional[float] = Field(default=None, ge=0)


class SavedReportCreateBody(BaseModel):
    analysis_history_id: str
    custom_title: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=4000)


class SavedReportPatchBody(BaseModel):
    custom_title: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=4000)


class PreferencesPatchBody(BaseModel):
    theme: Optional[str] = None
    default_watchlist: Optional[str] = None
    default_analysis_horizon: Optional[str] = Field(default=None, max_length=60)


# ── profile ──────────────────────────────────────────────────────────────────

@router.post("/profile/sync")
def sync_profile(body: ProfileSyncBody, user: str = Depends(require_clerk_user)):
    """Create-or-refresh the caller's profile (first successful login creates it)."""
    return ProfilesRepository(_client()).sync(
        user, email=body.email, full_name=body.full_name, avatar_url=body.avatar_url
    )


@router.get("/profile")
def get_profile(user: str = Depends(require_clerk_user)):
    profile = ProfilesRepository(_client()).get(user)
    if profile is None:
        raise HTTPException(status_code=404, detail="No profile yet — sync one first.")
    return profile


# ── watchlists ───────────────────────────────────────────────────────────────

@router.get("/watchlists")
def list_watchlists(user: str = Depends(require_clerk_user)):
    return {"watchlists": WatchlistsRepository(_client()).list_with_items(user)}


@router.post("/watchlists", status_code=201)
def create_watchlist(body: WatchlistCreateBody, user: str = Depends(require_clerk_user)):
    created = WatchlistsRepository(_client()).create(user, body.name, body.tickers)
    if created is None:
        raise HTTPException(status_code=409, detail="Watchlist limit reached (20).")
    return created


@router.patch("/watchlists/{watchlist_id}")
def rename_watchlist(
    watchlist_id: str, body: WatchlistRenameBody, user: str = Depends(require_clerk_user)
):
    if not WatchlistsRepository(_client()).rename(user, watchlist_id, body.name):
        raise HTTPException(status_code=404, detail="Watchlist not found.")
    return {"ok": True}


@router.delete("/watchlists/{watchlist_id}")
def delete_watchlist(watchlist_id: str, user: str = Depends(require_clerk_user)):
    if not WatchlistsRepository(_client()).delete(user, watchlist_id):
        raise HTTPException(status_code=404, detail="Watchlist not found.")
    return {"ok": True}


@router.post("/watchlists/{watchlist_id}/tickers", status_code=201)
def add_watchlist_ticker(
    watchlist_id: str, body: TickerBody, user: str = Depends(require_clerk_user)
):
    if not WatchlistsRepository(_client()).add_ticker(user, watchlist_id, body.ticker):
        raise HTTPException(status_code=404, detail="Watchlist not found.")
    return {"ok": True}


@router.delete("/watchlists/{watchlist_id}/tickers/{ticker}")
def remove_watchlist_ticker(
    watchlist_id: str, ticker: str, user: str = Depends(require_clerk_user)
):
    if not WatchlistsRepository(_client()).remove_ticker(user, watchlist_id, ticker):
        raise HTTPException(status_code=404, detail="Watchlist not found.")
    return {"ok": True}


# ── portfolio positions ──────────────────────────────────────────────────────

@router.get("/portfolio")
def list_positions(user: str = Depends(require_clerk_user)):
    return {"positions": PortfolioRepository(_client()).list(user)}


@router.post("/portfolio", status_code=201)
def upsert_position(body: PositionCreateBody, user: str = Depends(require_clerk_user)):
    position = PortfolioRepository(_client()).upsert(
        user, body.ticker, body.shares, body.average_price
    )
    if position is None:
        raise HTTPException(status_code=422, detail="Invalid ticker, shares, or price.")
    return position


@router.patch("/portfolio/{position_id}")
def patch_position(
    position_id: str, body: PositionPatchBody, user: str = Depends(require_clerk_user)
):
    position = PortfolioRepository(_client()).update(
        user, position_id, shares=body.shares, average_price=body.average_price
    )
    if position is None:
        raise HTTPException(status_code=404, detail="Position not found.")
    return position


@router.delete("/portfolio/{position_id}")
def delete_position(position_id: str, user: str = Depends(require_clerk_user)):
    if not PortfolioRepository(_client()).delete(user, position_id):
        raise HTTPException(status_code=404, detail="Position not found.")
    return {"ok": True}


# ── analysis history ─────────────────────────────────────────────────────────

@router.get("/history")
def list_history(
    user: str = Depends(require_clerk_user),
    ticker: Optional[str] = Query(default=None, max_length=10),
    verdict: Optional[str] = Query(default=None, max_length=20),
    date_from: Optional[str] = Query(default=None, alias="from"),
    date_to: Optional[str] = Query(default=None, alias="to"),
    q: Optional[str] = Query(default=None, max_length=60),
    sort: str = Query(default="newest", pattern="^(newest|oldest|confidence)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    return AnalysisRepository(_client()).list(
        user,
        ticker=ticker,
        verdict=verdict,
        date_from=date_from,
        date_to=date_to,
        search=q,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.get("/history/compare")
def compare_history(
    a: str = Query(...),
    b: str = Query(...),
    user: str = Depends(require_clerk_user),
):
    """Deterministic factor-level comparison of two stored runs (backend math only)."""
    result = AnalysisRepository(_client()).compare(user, a, b)
    if result is None:
        raise HTTPException(status_code=404, detail="One or both analyses were not found.")
    return result


@router.get("/history/{history_id}")
def get_history(history_id: str, user: str = Depends(require_clerk_user)):
    row = AnalysisRepository(_client()).get(user, history_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return row


@router.delete("/history/{history_id}")
def delete_history(history_id: str, user: str = Depends(require_clerk_user)):
    if not AnalysisRepository(_client()).delete(user, history_id):
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return {"ok": True}


# ── saved reports ────────────────────────────────────────────────────────────

@router.get("/saved-reports")
def list_saved_reports(user: str = Depends(require_clerk_user)):
    return {"saved": AnalysisRepository(_client()).list_saved(user)}


@router.post("/saved-reports", status_code=201)
def create_saved_report(
    body: SavedReportCreateBody, user: str = Depends(require_clerk_user)
):
    saved = AnalysisRepository(_client()).save_report(
        user, body.analysis_history_id, body.custom_title, body.notes
    )
    if saved is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return saved


@router.patch("/saved-reports/{saved_id}")
def patch_saved_report(
    saved_id: str, body: SavedReportPatchBody, user: str = Depends(require_clerk_user)
):
    saved = AnalysisRepository(_client()).update_saved(
        user, saved_id, custom_title=body.custom_title, notes=body.notes
    )
    if saved is None:
        raise HTTPException(status_code=404, detail="Saved report not found.")
    return saved


@router.delete("/saved-reports/{saved_id}")
def delete_saved_report(saved_id: str, user: str = Depends(require_clerk_user)):
    if not AnalysisRepository(_client()).delete_saved(user, saved_id):
        raise HTTPException(status_code=404, detail="Saved report not found.")
    return {"ok": True}


# ── preferences ──────────────────────────────────────────────────────────────

@router.get("/preferences")
def get_preferences(user: str = Depends(require_clerk_user)):
    return PreferencesRepository(_client()).get(user) or {}


@router.patch("/preferences")
def patch_preferences(
    body: PreferencesPatchBody, user: str = Depends(require_clerk_user)
):
    return PreferencesRepository(_client()).patch(
        user, body.model_dump(exclude_unset=True)
    ) or {}


# ── research sessions ────────────────────────────────────────────────────────
# An investigation that survives: workspace state, notebook and activity,
# all scoped to the signed-in user.

class SessionCreateBody(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=12)
    workspace_state: Optional[dict[str, Any]] = None


class SessionPatchBody(BaseModel):
    title: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = Field(default=None, max_length=2000)
    tags: Optional[list[str]] = Field(default=None, max_length=12)
    status: Optional[str] = None
    color: Optional[str] = Field(default=None, max_length=32)
    icon: Optional[str] = Field(default=None, max_length=32)
    workspace_state: Optional[dict[str, Any]] = None
    touch: bool = False


class NoteBody(BaseModel):
    body: str = Field(default="", max_length=20000)
    refs: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list, max_length=12)
    pinned: Optional[bool] = None


@router.get("/sessions")
def list_sessions(user: str = Depends(require_clerk_user), status: Optional[str] = None):
    return {"sessions": SessionsRepository(_client()).list(user, status)}


@router.post("/sessions", status_code=201)
def create_session(body: SessionCreateBody, user: str = Depends(require_clerk_user)):
    created = SessionsRepository(_client()).create(
        user, body.title, body.description, body.tags, body.workspace_state
    )
    if created is None:
        raise HTTPException(status_code=409, detail="Session limit reached (100).")
    return created


@router.get("/sessions/search")
def search_sessions(q: str = Query(..., max_length=80), user: str = Depends(require_clerk_user)):
    return SessionsRepository(_client()).search(user, q)


@router.get("/sessions/{session_id}")
def get_session(session_id: str, user: str = Depends(require_clerk_user)):
    repo = SessionsRepository(_client())
    session = repo.get(user, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    repo.touch(user, session_id)
    session["notes"] = repo.list_notes(user, session_id)
    return session


@router.patch("/sessions/{session_id}")
def patch_session(session_id: str, body: SessionPatchBody, user: str = Depends(require_clerk_user)):
    updated = SessionsRepository(_client()).patch(
        user, session_id, body.model_dump(exclude_unset=True)
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return updated


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, user: str = Depends(require_clerk_user)):
    if not SessionsRepository(_client()).delete(user, session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"ok": True}


@router.post("/sessions/{session_id}/notes", status_code=201)
def add_note(session_id: str, body: NoteBody, user: str = Depends(require_clerk_user)):
    note = SessionsRepository(_client()).add_note(
        user, session_id, body.body, body.refs, body.tags
    )
    if note is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return note


@router.patch("/notes/{note_id}")
def patch_note(note_id: str, body: NoteBody, user: str = Depends(require_clerk_user)):
    note = SessionsRepository(_client()).patch_note(
        user, note_id, body.model_dump(exclude_unset=True)
    )
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found.")
    return note


@router.delete("/notes/{note_id}")
def delete_note(note_id: str, user: str = Depends(require_clerk_user)):
    if not SessionsRepository(_client()).delete_note(user, note_id):
        raise HTTPException(status_code=404, detail="Note not found.")
    return {"ok": True}


# Benchmarks a portfolio can be measured against. Symbols rather than
# hardcoded UI logic, so adding one is a line here and nothing in the client.
BENCHMARKS: dict[str, str] = {
    "SPY": "S&P 500",
    "QQQ": "Nasdaq 100",
    "IWM": "Russell 2000",
}
DEFAULT_BENCHMARK = "SPY"

# How much history each range needs. `max` asks for five years and takes
# whatever the vendors actually have — the curve reports its own span.
RANGE_PERIODS: dict[str, str] = {
    "1W": "1mo", "1M": "3mo", "3M": "3mo",
    "6M": "6mo", "1Y": "1y", "MAX": "5y",
}
# Trading sessions to keep for a range, after fetching a period wide enough
# to cover it. Trimming client-side beats a second vendor call per range.
RANGE_SESSIONS: dict[str, Optional[int]] = {
    "1W": 5, "1M": 22, "3M": 64, "6M": 128, "1Y": 253, "MAX": None,
}


def _price_history(
    tickers: list[str], period: str = "3mo",
) -> tuple[dict[str, Any], dict[str, list]]:
    """Current quotes and daily closes for every held ticker, fetched in parallel.

    Two things this does not do. It does not open a second market-data path:
    the call is `market_data.get_series`, the same one `/api/quotes` makes,
    out of the same cache — so a portfolio page opened after a watchlist page
    costs nothing. And it no longer walks the symbols in sequence: a
    twenty-name book was twenty round trips end to end, which on a cold cache
    was the whole page load. `map_concurrent` bounds the fan-out so vendor
    token buckets are paced rather than burst through.

    Per-symbol failures stay per-symbol: one unreachable ticker returns an
    error entry and the rest of the book still values.
    """
    symbols = tickers[:25]
    if not symbols:
        return {}, {}

    def fetch(symbol: str) -> tuple[str, dict[str, Any], Optional[list]]:
        try:
            result = providers.market_data.get_series(symbol, period)
            if not result.ok or len(result.data.bars) < 2:
                return symbol, {"error": "no market data"}, None
            series = [(str(bar.date), float(bar.close)) for bar in result.data.bars if bar.close]
            if len(series) < 2:
                return symbol, {"error": "no market data"}, None
            last, prev = series[-1][1], series[-2][1]
            return symbol, {
                "price": round(last, 2),
                "change_1d": round((last / prev - 1) * 100, 2) if prev else None,
                "source": result.source,
                "stale": result.stale,
            }, series
        except Exception as exc:  # noqa: BLE001 — one bad symbol never fails the book
            logger.warning("portfolio quote failed for %s: %s", symbol, exc)
            return symbol, {"error": "unavailable"}, None

    quotes: dict[str, Any] = {}
    closes: dict[str, list] = {}
    for outcome in map_concurrent(fetch, symbols, timeout=25.0, label="portfolio.prices"):
        if not outcome.ok or outcome.value is None:
            continue
        symbol, quote, series = outcome.value
        quotes[symbol] = quote
        if series:
            closes[symbol] = series
    # A symbol the fan-out lost entirely still needs an entry, or the holding
    # would silently vanish from the coverage count.
    for symbol in symbols:
        quotes.setdefault(symbol, {"error": "unavailable"})
    return quotes, closes


def _trim(series: list[tuple[str, float]], sessions: Optional[int]) -> list[tuple[str, float]]:
    return series[-sessions:] if sessions and len(series) > sessions else series


@router.get("/portfolio/intelligence")
def portfolio_intelligence_report(
    user: str = Depends(require_clerk_user),
    range: str = Query("3M", description="1W · 1M · 3M · 6M · 1Y · MAX"),
    benchmark: str = Query(DEFAULT_BENCHMARK, description="Benchmark symbol"),
):
    """Valuation, concentration, exposure and risk over the caller's book.

    Three things are assembled here, all from data the product already has:

    * **Valuation** — shares × current price against shares × average cost,
      per holding and in total. Prices come through the existing market-data
      provider chain; a holding whose price is unreachable is reported as
      unpriced and excluded from the totals rather than valued at its own
      cost, which would report it as exactly break-even.
    * **A historical value curve** — today's share counts marked against the
      real daily closes the same provider call already returned. Not a track
      record, and the payload says so.
    * **Concentration, exposure and risk** — the arithmetic in
      ``src.services.portfolio_intelligence``, now weighted by current market
      value when prices are available and by cost basis when they are not.
    """
    client = _client()
    positions = PortfolioRepository(client).list(user)
    tickers = sorted({str(p.get("ticker") or "").upper() for p in positions if p.get("ticker")})

    window = range.upper() if range.upper() in RANGE_PERIODS else "3M"
    period = RANGE_PERIODS[window]
    bench_symbol = benchmark.upper() if benchmark.upper() in BENCHMARKS else DEFAULT_BENCHMARK

    # The benchmark rides the same fan-out as the holdings rather than being
    # a separate sequential call after them — it is one more symbol, and
    # fetching it apart would add a full round trip to every page load.
    quotes, closes = _price_history(tickers + [bench_symbol], period) if tickers else ({}, {})
    bench_series = closes.pop(bench_symbol, None) if bench_symbol not in tickers else closes.get(bench_symbol)
    quotes.pop(bench_symbol, None) if bench_symbol not in tickers else None

    trimmed = {t: _trim(series, RANGE_SESSIONS[window]) for t, series in closes.items()}
    valuation = portfolio_intelligence.value_positions(positions, quotes)
    curve = portfolio_intelligence.value_curve(positions, trimmed)

    market_values = {
        row["ticker"]: row["current_value"]
        for row in valuation["rows"]
        if row.get("priced") and row.get("current_value")
    }

    analyses = AnalysisRepository(client).latest_by_ticker(user, tickers) if tickers else {}
    report = portfolio_intelligence.analyse(positions, analyses, market_values or None)
    report["headlines"] = portfolio_intelligence.headlines(report)
    report["analysed"] = analyses
    report["valuation"] = valuation
    report["curve"] = curve

    # ── analytics over the same history the curve is drawn from ─────────────
    # All descriptive, all named for what they are: no Sharpe (no defensible
    # risk-free series exists here), no portfolio volatility from per-name
    # scores, and the benchmark difference is a return difference and says so.
    values = [p["value"] for p in curve["points"]] if curve else []
    report["risk"]["volatility_pct"] = portfolio_intelligence.volatility(values)
    report["risk"]["max_drawdown"] = portfolio_intelligence.max_drawdown(values)
    report["risk"]["holding_drawdowns"] = sorted(
        (
            {"ticker": t, **(portfolio_intelligence.max_drawdown([c for _, c in series]) or {})}
            for t, series in trimmed.items() if len(series) > 1
        ),
        key=lambda r: r.get("pct", 0.0),
    )[:5]
    report["correlation"] = portfolio_intelligence.correlation_matrix(trimmed)
    report["contributions"] = portfolio_intelligence.contributions(valuation["rows"])
    report["benchmark"] = (
        portfolio_intelligence.benchmark_comparison(
            curve["points"], _trim(bench_series, RANGE_SESSIONS[window]),
            symbol=bench_symbol, label=BENCHMARKS[bench_symbol],
        )
        if curve and bench_series else None
    )
    report["range"] = window
    report["ranges"] = list(RANGE_PERIODS)
    report["benchmarks"] = [{"symbol": s, "label": l} for s, l in BENCHMARKS.items()]
    # The product prices US equities through USD-denominated vendors; stating
    # it lets the UI format without guessing, and makes the assumption
    # visible if a non-USD venue is ever added.
    report["currency"] = "USD"
    return report
