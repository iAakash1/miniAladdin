"""Profiles — one row per Clerk user, auto-created on first login."""

from __future__ import annotations

from typing import Any, Optional


class ProfilesRepository:
    def __init__(self, client: Any) -> None:
        self._c = client

    def get(self, clerk_user_id: str) -> Optional[dict[str, Any]]:
        rows = (
            self._c.table("profiles")
            .select("*")
            .eq("clerk_user_id", clerk_user_id)
            .limit(1)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def sync(
        self,
        clerk_user_id: str,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create the profile on first sight; refresh mutable fields after."""
        payload: dict[str, Any] = {"clerk_user_id": clerk_user_id}
        if email is not None:
            payload["email"] = email
        if full_name is not None:
            payload["full_name"] = full_name
        if avatar_url is not None:
            payload["avatar_url"] = avatar_url
        rows = (
            self._c.table("profiles")
            .upsert(payload, on_conflict="clerk_user_id")
            .execute()
            .data
        )
        return rows[0]
