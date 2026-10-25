"""Watchlists + items, scoped to the Clerk user on every query.

The response keeps the fields the frontend has always read ({id, name,
tickers, createdAt}) and adds what a tracker needs: each item's note, tags and
position, the list's position, whether it is the default, and its preferred
sort. Ordering is applied here in Python from (position, created/added time),
so a list reads correctly whether or not a row has ever been reordered.

Every mutation re-asserts the user filter even after an ownership check, so a
write is self-scoping and never depends on a prior read having been right.
"""

from __future__ import annotations

import re
from typing import Any, Optional

MAX_LISTS = 30
#: Per list. The tracker reads quotes in batches of 25, so a long list is
#: paged by the client, not fetched in one request.
MAX_TICKERS = 200
MAX_TAGS = 8
SORT_KEYS = ("manual", "symbol", "change", "change_pct", "perf_1m", "perf_1y", "updated", "alerts")
_TICKER_RE = re.compile(r"[^A-Z.^-]")
_TAG_RE = re.compile(r"[^a-z0-9 _-]")


def normalize_ticker(raw: str) -> str:
    return _TICKER_RE.sub("", (raw or "").strip().upper())[:10]


def _clean_tags(tags: Optional[list[str]]) -> list[str]:
    out: list[str] = []
    for raw in tags or []:
        tag = _TAG_RE.sub("", str(raw).strip().lower())[:24].strip()
        if tag and tag not in out:
            out.append(tag)
    return out[:MAX_TAGS]


def _item_order(item: dict[str, Any]) -> tuple:
    return (item.get("position") or 0, item.get("added_at") or "")


def _shape(row: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(items, key=_item_order)
    return {
        "id": row["id"],
        "name": row["name"],
        "tickers": [i["ticker"] for i in ordered],
        "items": [
            {
                "ticker": i["ticker"],
                "note": i.get("note"),
                "tags": list(i.get("tags") or []),
                "position": i.get("position") or 0,
                "addedAt": i.get("added_at"),
            }
            for i in ordered
        ],
        "position": row.get("position") or 0,
        "isDefault": bool(row.get("is_default")),
        "sortKey": row.get("sort_key") or "manual",
        "createdAt": row["created_at"],
        "updatedAt": row.get("updated_at") or row["created_at"],
    }


class WatchlistsRepository:
    def __init__(self, client: Any) -> None:
        self._c = client

    # ── reads ────────────────────────────────────────────────────────────────
    def _lists(self, clerk_user_id: str) -> list[dict[str, Any]]:
        rows = (
            self._c.table("watchlists")
            .select("*")
            .eq("clerk_user_id", clerk_user_id)
            .order("created_at")
            .execute()
            .data
        )
        return sorted(rows, key=lambda r: (r.get("position") or 0, r.get("created_at") or ""))

    def _items(self, watchlist_ids: list[str]) -> list[dict[str, Any]]:
        if not watchlist_ids:
            return []
        return (
            self._c.table("watchlist_items")
            .select("*")
            .in_("watchlist_id", watchlist_ids)
            .order("added_at")
            .execute()
            .data
        )

    def list_with_items(self, clerk_user_id: str) -> list[dict[str, Any]]:
        lists = self._lists(clerk_user_id)
        items = self._items([row["id"] for row in lists])
        by_list: dict[str, list[dict[str, Any]]] = {row["id"]: [] for row in lists}
        for item in items:
            by_list.setdefault(item["watchlist_id"], []).append(item)
        return [_shape(row, by_list.get(row["id"], [])) for row in lists]

    def get(self, clerk_user_id: str, watchlist_id: str) -> Optional[dict[str, Any]]:
        row = self._owned(clerk_user_id, watchlist_id)
        if row is None:
            return None
        return _shape(row, self._items([watchlist_id]))

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

    def tracked_tickers(self, clerk_user_id: str) -> set[str]:
        """Every symbol in any of the user's lists."""
        lists = self._lists(clerk_user_id)
        return {i["ticker"] for i in self._items([row["id"] for row in lists])}

    # ── list writes ──────────────────────────────────────────────────────────
    def create(
        self, clerk_user_id: str, name: str, tickers: Optional[list[str]] = None
    ) -> Optional[dict[str, Any]]:
        existing = self._lists(clerk_user_id)
        if len(existing) >= MAX_LISTS:
            return None
        clean_name = name.strip()[:40] or "Untitled"
        position = max((r.get("position") or 0 for r in existing), default=-1) + 1
        row = (
            self._c.table("watchlists")
            .insert({
                "clerk_user_id": clerk_user_id, "name": clean_name, "position": position,
                # The first list a user makes is their default.
                "is_default": not existing,
            })
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
        items: list[dict[str, Any]] = []
        if clean_tickers:
            items = self._c.table("watchlist_items").insert(
                [{"watchlist_id": row["id"], "ticker": t, "position": i} for i, t in enumerate(clean_tickers)]
            ).execute().data
        return _shape(row, items)

    def rename(self, clerk_user_id: str, watchlist_id: str, name: str) -> bool:
        return self.update(clerk_user_id, watchlist_id, name=name)

    def update(
        self, clerk_user_id: str, watchlist_id: str, *,
        name: Optional[str] = None, is_default: Optional[bool] = None, sort_key: Optional[str] = None,
    ) -> bool:
        if self._owned(clerk_user_id, watchlist_id) is None:
            return False
        patch: dict[str, Any] = {}
        if name is not None:
            clean = name.strip()[:40]
            if not clean:
                return False
            patch["name"] = clean
        if sort_key is not None:
            if sort_key not in SORT_KEYS:
                return False
            patch["sort_key"] = sort_key
        if is_default:
            # One default per user: clear the others first, so the partial
            # unique index never sees two.
            self._c.table("watchlists").update({"is_default": False}).eq(
                "clerk_user_id", clerk_user_id
            ).execute()
            patch["is_default"] = True
        elif is_default is False:
            patch["is_default"] = False
        if patch:
            self._c.table("watchlists").update(patch).eq("id", watchlist_id).eq(
                "clerk_user_id", clerk_user_id
            ).execute()
        return True

    def reorder_lists(self, clerk_user_id: str, ordered_ids: list[str]) -> bool:
        """Set list positions from an ordering that names exactly the user's lists."""
        owned = {row["id"] for row in self._lists(clerk_user_id)}
        if set(ordered_ids) != owned or len(ordered_ids) != len(owned):
            return False
        for position, list_id in enumerate(ordered_ids):
            self._c.table("watchlists").update({"position": position}).eq("id", list_id).eq(
                "clerk_user_id", clerk_user_id
            ).execute()
        return True

    def delete(self, clerk_user_id: str, watchlist_id: str) -> bool:
        if self._owned(clerk_user_id, watchlist_id) is None:
            return False
        # Items go with the list (ON DELETE CASCADE), so nothing is orphaned.
        self._c.table("watchlists").delete().eq("id", watchlist_id).eq(
            "clerk_user_id", clerk_user_id
        ).execute()
        return True

    # ── item writes ──────────────────────────────────────────────────────────
    def add_ticker(self, clerk_user_id: str, watchlist_id: str, ticker: str) -> bool:
        return self.add(clerk_user_id, watchlist_id, ticker) in ("added", "exists")

    def add(self, clerk_user_id: str, watchlist_id: str, ticker: str) -> str:
        """added | exists | full | invalid | not_found."""
        if self._owned(clerk_user_id, watchlist_id) is None:
            return "not_found"
        symbol = normalize_ticker(ticker)
        if not symbol:
            return "invalid"
        current = self._items([watchlist_id])
        if any(item["ticker"] == symbol for item in current):
            return "exists"
        if len(current) >= MAX_TICKERS:
            return "full"
        position = max((i.get("position") or 0 for i in current), default=-1) + 1
        self._c.table("watchlist_items").upsert(
            {"watchlist_id": watchlist_id, "ticker": symbol, "position": position},
            on_conflict="watchlist_id,ticker",
        ).execute()
        return "added"

    def remove_ticker(self, clerk_user_id: str, watchlist_id: str, ticker: str) -> bool:
        if self._owned(clerk_user_id, watchlist_id) is None:
            return False
        symbol = normalize_ticker(ticker)
        self._c.table("watchlist_items").delete().eq("watchlist_id", watchlist_id).eq(
            "ticker", symbol
        ).execute()
        return True

    def update_item(
        self, clerk_user_id: str, watchlist_id: str, ticker: str, *,
        note: Optional[str] = None, tags: Optional[list[str]] = None, clear_note: bool = False,
    ) -> bool:
        if self._owned(clerk_user_id, watchlist_id) is None:
            return False
        symbol = normalize_ticker(ticker)
        if not any(i["ticker"] == symbol for i in self._items([watchlist_id])):
            return False
        patch: dict[str, Any] = {}
        if clear_note:
            patch["note"] = None
        elif note is not None:
            patch["note"] = note.strip()[:500] or None
        if tags is not None:
            patch["tags"] = _clean_tags(tags)
        if patch:
            self._c.table("watchlist_items").update(patch).eq("watchlist_id", watchlist_id).eq(
                "ticker", symbol
            ).execute()
        return True

    def reorder_items(self, clerk_user_id: str, watchlist_id: str, ordered: list[str]) -> bool:
        """Set item positions from an ordering that names exactly the list's symbols."""
        if self._owned(clerk_user_id, watchlist_id) is None:
            return False
        current = {i["ticker"] for i in self._items([watchlist_id])}
        symbols = [normalize_ticker(t) for t in ordered]
        if set(symbols) != current or len(symbols) != len(current):
            return False
        for position, symbol in enumerate(symbols):
            self._c.table("watchlist_items").update({"position": position}).eq(
                "watchlist_id", watchlist_id
            ).eq("ticker", symbol).execute()
        return True

    def move_item(self, clerk_user_id: str, from_id: str, to_id: str, ticker: str) -> str:
        """moved | exists | full | not_found — the note and tags travel with it."""
        if from_id == to_id:
            return "exists"
        if self._owned(clerk_user_id, from_id) is None or self._owned(clerk_user_id, to_id) is None:
            return "not_found"
        symbol = normalize_ticker(ticker)
        source = next((i for i in self._items([from_id]) if i["ticker"] == symbol), None)
        if source is None:
            return "not_found"
        target = self._items([to_id])
        if not any(i["ticker"] == symbol for i in target):
            if len(target) >= MAX_TICKERS:
                return "full"
            position = max((i.get("position") or 0 for i in target), default=-1) + 1
            self._c.table("watchlist_items").upsert(
                {"watchlist_id": to_id, "ticker": symbol, "position": position,
                 "note": source.get("note"), "tags": list(source.get("tags") or [])},
                on_conflict="watchlist_id,ticker",
            ).execute()
        self._c.table("watchlist_items").delete().eq("watchlist_id", from_id).eq("ticker", symbol).execute()
        return "moved"
