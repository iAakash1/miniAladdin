"""User preferences — one row per Clerk user, patch-style updates."""

from __future__ import annotations

from typing import Any, Optional

_ALLOWED_THEMES = {"light", "dark"}
#: Presentation only. This value must never be consulted for authorization or
#: entitlement — it decides how much of the same analysis is drawn, nothing
#: about what the caller may reach.
_ALLOWED_EXPERIENCE_MODES = {"beginner", "advanced"}
#: What a user may change about themselves. `role` is deliberately absent:
#: there is no client path that writes it.
_ALLOWED_FIELDS = {
    "theme", "default_watchlist", "default_analysis_horizon", "experience_mode",
}

#: Applied when a user has never chosen. Advanced, not beginner, because every
#: account that predates this column already works in the terminal and a
#: migration must not move them out of it.
DEFAULT_EXPERIENCE_MODE = "advanced"


class PreferencesRepository:
    def __init__(self, client: Any) -> None:
        self._c = client

    def get(self, clerk_user_id: str) -> Optional[dict[str, Any]]:
        rows = (
            self._c.table("user_preferences")
            .select("*")
            .eq("clerk_user_id", clerk_user_id)
            .limit(1)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def _owns_watchlist(self, clerk_user_id: str, watchlist_id: str) -> bool:
        rows = (
            self._c.table("watchlists")
            .select("id")
            .eq("clerk_user_id", clerk_user_id)
            .eq("id", watchlist_id)
            .limit(1)
            .execute()
            .data
        )
        return bool(rows)

    def patch(self, clerk_user_id: str, fields: dict[str, Any]) -> Optional[dict[str, Any]]:
        clean = {k: v for k, v in fields.items() if k in _ALLOWED_FIELDS}
        if "theme" in clean and clean["theme"] not in _ALLOWED_THEMES:
            clean.pop("theme")
        if (
            "experience_mode" in clean
            and clean["experience_mode"] not in _ALLOWED_EXPERIENCE_MODES
        ):
            clean.pop("experience_mode")
        # `default_watchlist` is a reference to another row, and it was written
        # with no check that the row belongs to this caller. Nothing leaked —
        # every watchlist read is scoped separately — but a user's preferences
        # could point at a stranger's object, which is the kind of unvalidated
        # id that becomes a real disclosure the moment some later reader
        # trusts it instead of re-scoping. Dropped rather than rejected, on
        # the same rule the invalid theme above follows.
        if clean.get("default_watchlist") is not None and not self._owns_watchlist(
            clerk_user_id, str(clean["default_watchlist"])
        ):
            clean.pop("default_watchlist")
        if not clean:
            return self.get(clerk_user_id)
        clean["clerk_user_id"] = clerk_user_id
        rows = (
            self._c.table("user_preferences")
            .upsert(clean, on_conflict="clerk_user_id")
            .execute()
            .data
        )
        return rows[0] if rows else None
