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

from src.services import database
from src.services.clerk_auth import require_clerk_user
from src.services.database.repositories import (
    AnalysisRepository,
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
