"""Watchlists + items, scoped to the Clerk user on every query.

The response shape mirrors the frontend's existing `Watchlist` type
({id, name, tickers, createdAt}) so swapping localStorage for the API is a
pure persistence change, not a UI change.
"""

from __future__ import annotations

import re
from typing import Any, Optional

MAX_LISTS = 20
MAX_TICKERS = 25  # matches the /api/quotes batch cap
_TICKER_RE = re.compile(r"[^A-Z.^-]")


def normalize_ticker(raw: str) -> str:
    return _TICKER_RE.sub("", raw.strip().upper())[:10]


def _shape(row: dict[str, Any], tickers: list[str]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "tickers": tickers,
        "createdAt": row["created_at"],
    }


class WatchlistsRepository:
    def __init__(self, client: Any) -> None:
        self._c = client

    # ── reads ────────────────────────────────────────────────────────────────
    def list_with_items(self, clerk_user_id: str) -> list[dict[str, Any]]:
        lists = (
            self._c.table("watchlists")
            .select("*")
            .eq("clerk_user_id", clerk_user_id)
            .order("created_at")
            .execute()
            .data
        )
        if not lists:
            return []
        ids = [row["id"] for row in lists]
        items = (
            self._c.table("watchlist_items")
            .select("watchlist_id,ticker,added_at")
            .in_("watchlist_id", ids)
            .order("added_at")
            .execute()
            .data
        )
        by_list: dict[str, list[str]] = {list_id: [] for list_id in ids}
        for item in items:
            by_list.setdefault(item["watchlist_id"], []).append(item["ticker"])
        return [_shape(row, by_list.get(row["id"], [])) for row in lists]

    def _owned(self, clerk_user_id: str, watchlist_id: str) -> Optional[dict[str, Any]]:
        rows = (
            self._c.table("watchlists")
            .select("*")
            .eq("clerk_user_id", clerk_user_id)
            .eq("id", watchlist_id)
            .limit(1)
            .execute()
            .data
        )
        return rows[0] if rows else None

    # ── writes ───────────────────────────────────────────────────────────────
    def create(
        self, clerk_user_id: str, name: str, tickers: Optional[list[str]] = None
    ) -> Optional[dict[str, Any]]:
        existing = (
            self._c.table("watchlists")
            .select("id")
            .eq("clerk_user_id", clerk_user_id)
            .execute()
            .data
        )
        if len(existing) >= MAX_LISTS:
            return None
        clean_name = name.strip()[:40] or "Untitled"
        row = (
            self._c.table("watchlists")
            .insert({"clerk_user_id": clerk_user_id, "name": clean_name})
            .execute()
            .data[0]
        )
        seen: set[str] = set()
        clean_tickers: list[str] = []
        for raw in tickers or []:
            symbol = normalize_ticker(raw)
            if symbol and symbol not in seen:
                seen.add(symbol)
                clean_tickers.append(symbol)
        clean_tickers = clean_tickers[:MAX_TICKERS]
        if clean_tickers:
            self._c.table("watchlist_items").insert(
                [{"watchlist_id": row["id"], "ticker": t} for t in clean_tickers]
            ).execute()
        return _shape(row, clean_tickers)

    def rename(self, clerk_user_id: str, watchlist_id: str, name: str) -> bool:
        if self._owned(clerk_user_id, watchlist_id) is None:
            return False
        clean = name.strip()[:40]
        if not clean:
            return False
        # Mutations re-assert the user filter even after the ownership check —
        # every write is self-scoping, not dependent on a prior read.
        self._c.table("watchlists").update({"name": clean}).eq("id", watchlist_id).eq(
            "clerk_user_id", clerk_user_id
        ).execute()
        return True

    def delete(self, clerk_user_id: str, watchlist_id: str) -> bool:
        if self._owned(clerk_user_id, watchlist_id) is None:
            return False
        self._c.table("watchlists").delete().eq("id", watchlist_id).eq(
            "clerk_user_id", clerk_user_id
        ).execute()
        return True

    def add_ticker(self, clerk_user_id: str, watchlist_id: str, ticker: str) -> bool:
        if self._owned(clerk_user_id, watchlist_id) is None:
            return False
        symbol = normalize_ticker(ticker)
        if not symbol:
            return False
        current = (
            self._c.table("watchlist_items")
            .select("ticker")
            .eq("watchlist_id", watchlist_id)
            .execute()
            .data
        )
        if len(current) >= MAX_TICKERS or any(item["ticker"] == symbol for item in current):
            return True  # cap reached or already present — idempotent success
        self._c.table("watchlist_items").upsert(
            {"watchlist_id": watchlist_id, "ticker": symbol},
            on_conflict="watchlist_id,ticker",
        ).execute()
        return True

    def remove_ticker(self, clerk_user_id: str, watchlist_id: str, ticker: str) -> bool:
        if self._owned(clerk_user_id, watchlist_id) is None:
            return False
        symbol = normalize_ticker(ticker)
        self._c.table("watchlist_items").delete().eq("watchlist_id", watchlist_id).eq(
            "ticker", symbol
        ).execute()
        return True
