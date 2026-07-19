"""Research sessions + notebook — investigations that survive.

Every query is scoped by the Clerk-verified user id, and every mutation
re-asserts that filter in the write itself rather than trusting a prior
ownership read (the same discipline as the other repositories).

Workspace state is stored as one jsonb document with a `schema_version`,
so the workspace can grow new panels and settings without a migration;
older sessions are migrated forward in code by `_migrate_state`.
"""

from __future__ import annotations

from typing import Any, Optional

# Bump when the workspace-state shape changes incompatibly, and add a
# forward migration in _migrate_state.
WORKSPACE_SCHEMA_VERSION = 1

MAX_SESSIONS = 100
MAX_SNAPSHOTS = 40      # per session; snapshots are append-only
MAX_ACTIVITY = 200      # investigation timeline entries kept per session

SUMMARY_COLUMNS = (
    "id,title,description,tags,status,color,icon,created_at,updated_at,last_opened_at"
)


def empty_state() -> dict[str, Any]:
    """The workspace state of a brand-new session."""
    return {
        "schema_version": WORKSPACE_SCHEMA_VERSION,
        "symbols": [],
        "center": None,
        "selected": None,
        "pinned": [],
        "hidden": [],
        "expanded": [],
        "collections": [],
        "bookmarks": [],
        "filters": {"node_types": "", "edge_types": "", "min_confidence": 0, "hops": 2},
        "camera": {"zoom": 1, "x": 0, "y": 0},
        "panels": {"inspector": True, "timeline": True, "notebook": True},
        "search": "",
        "snapshots": [],
        "activity": [],
    }


def _migrate_state(state: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Forward-migrate a stored state to the current shape.

    Missing keys are filled from the empty template rather than failing,
    so a session saved by an older build always opens.
    """
    base = empty_state()
    if not isinstance(state, dict):
        return base
    merged = {**base, **state}
    # Nested dicts merge key-wise so new settings appear with defaults.
    for key in ("filters", "camera", "panels"):
        if isinstance(state.get(key), dict):
            merged[key] = {**base[key], **state[key]}
    merged["schema_version"] = WORKSPACE_SCHEMA_VERSION
    # Bound the append-only collections at read time too, in case an older
    # build wrote unbounded lists.
    merged["snapshots"] = list(merged.get("snapshots") or [])[-MAX_SNAPSHOTS:]
    merged["activity"] = list(merged.get("activity") or [])[-MAX_ACTIVITY:]
    return merged


class SessionsRepository:
    def __init__(self, client: Any) -> None:
        self._c = client

    # ── sessions ─────────────────────────────────────────────────────────────
    def list(self, clerk_user_id: str, status: Optional[str] = None) -> list[dict[str, Any]]:
        query = (
            self._c.table("research_sessions")
            .select(SUMMARY_COLUMNS)
            .eq("clerk_user_id", clerk_user_id)
        )
        if status:
            query = query.eq("status", status)
        return query.order("last_opened_at", desc=True).limit(MAX_SESSIONS).execute().data

    def get(self, clerk_user_id: str, session_id: str) -> Optional[dict[str, Any]]:
        rows = (
            self._c.table("research_sessions")
            .select("*")
            .eq("clerk_user_id", clerk_user_id)
            .eq("id", session_id)
            .limit(1)
            .execute()
            .data
        )
        if not rows:
            return None
        row = rows[0]
        row["workspace_state"] = _migrate_state(row.get("workspace_state"))
        return row

    def create(
        self,
        clerk_user_id: str,
        title: str,
        description: Optional[str] = None,
        tags: Optional[list[str]] = None,
        workspace_state: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        existing = (
            self._c.table("research_sessions")
            .select("id")
            .eq("clerk_user_id", clerk_user_id)
            .execute()
            .data
        )
        if len(existing) >= MAX_SESSIONS:
            return None
        row = {
            "clerk_user_id": clerk_user_id,
            "title": (title or "Untitled investigation").strip()[:120],
            "description": (description or None),
            "tags": [t.strip()[:40] for t in (tags or []) if t.strip()][:12],
            "workspace_state": _migrate_state(workspace_state),
        }
        data = self._c.table("research_sessions").insert(row).execute().data
        return data[0] if data else None

    def patch(
        self, clerk_user_id: str, session_id: str, fields: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Update metadata and/or workspace state. Only known fields apply."""
        if self.get(clerk_user_id, session_id) is None:
            return None
        clean: dict[str, Any] = {}
        for key in ("title", "description", "color", "icon"):
            if key in fields:
                value = fields[key]
                clean[key] = (str(value).strip()[:120] if value else None)
        if "tags" in fields and isinstance(fields["tags"], list):
            clean["tags"] = [str(t).strip()[:40] for t in fields["tags"] if str(t).strip()][:12]
        if fields.get("status") in {"active", "archived"}:
            clean["status"] = fields["status"]
        if isinstance(fields.get("workspace_state"), dict):
            clean["workspace_state"] = _migrate_state(fields["workspace_state"])
        if fields.get("touch"):
            clean["last_opened_at"] = "now()"
        if not clean:
            return self.get(clerk_user_id, session_id)
        rows = (
            self._c.table("research_sessions")
            .update(clean)
            .eq("id", session_id)
            .eq("clerk_user_id", clerk_user_id)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def touch(self, clerk_user_id: str, session_id: str) -> None:
        """Record that a session was opened — drives 'recent investigations'."""
        from datetime import datetime, timezone

        self._c.table("research_sessions").update(
            {"last_opened_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", session_id).eq("clerk_user_id", clerk_user_id).execute()

    def delete(self, clerk_user_id: str, session_id: str) -> bool:
        if self.get(clerk_user_id, session_id) is None:
            return False
        self._c.table("research_sessions").delete().eq("id", session_id).eq(
            "clerk_user_id", clerk_user_id
        ).execute()
        return True

    # ── notebook ─────────────────────────────────────────────────────────────
    def list_notes(self, clerk_user_id: str, session_id: str) -> list[dict[str, Any]]:
        return (
            self._c.table("session_notes")
            .select("*")
            .eq("clerk_user_id", clerk_user_id)
            .eq("session_id", session_id)
            .order("created_at", desc=True)
            .execute()
            .data
        )

    def add_note(
        self,
        clerk_user_id: str,
        session_id: str,
        body: str,
        refs: Optional[list[dict[str, Any]]] = None,
        tags: Optional[list[str]] = None,
    ) -> Optional[dict[str, Any]]:
        if self.get(clerk_user_id, session_id) is None:
            return None
        row = {
            "session_id": session_id,
            "clerk_user_id": clerk_user_id,
            "body": body[:20000],
            "refs": refs or [],
            "tags": [str(t).strip()[:40] for t in (tags or []) if str(t).strip()][:12],
        }
        data = self._c.table("session_notes").insert(row).execute().data
        return data[0] if data else None

    def patch_note(
        self, clerk_user_id: str, note_id: str, fields: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        clean: dict[str, Any] = {}
        if "body" in fields:
            clean["body"] = str(fields["body"])[:20000]
        if isinstance(fields.get("refs"), list):
            clean["refs"] = fields["refs"]
        if isinstance(fields.get("tags"), list):
            clean["tags"] = [str(t).strip()[:40] for t in fields["tags"] if str(t).strip()][:12]
        if isinstance(fields.get("pinned"), bool):
            clean["pinned"] = fields["pinned"]
        if not clean:
            return None
        rows = (
            self._c.table("session_notes")
            .update(clean)
            .eq("id", note_id)
            .eq("clerk_user_id", clerk_user_id)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def delete_note(self, clerk_user_id: str, note_id: str) -> bool:
        rows = (
            self._c.table("session_notes")
            .select("id")
            .eq("clerk_user_id", clerk_user_id)
            .eq("id", note_id)
            .limit(1)
            .execute()
            .data
        )
        if not rows:
            return False
        self._c.table("session_notes").delete().eq("id", note_id).eq(
            "clerk_user_id", clerk_user_id
        ).execute()
        return True

    # ── search across an investigation ───────────────────────────────────────
    def search(self, clerk_user_id: str, term: str) -> dict[str, Any]:
        """Search sessions and notes together — one answer for 'where did I
        write about export controls?'."""
        clean = term.strip()[:80]
        if not clean:
            return {"sessions": [], "notes": []}
        pattern = f"%{clean}%"
        sessions = (
            self._c.table("research_sessions")
            .select(SUMMARY_COLUMNS)
            .eq("clerk_user_id", clerk_user_id)
            .or_(f"title.ilike.{pattern},description.ilike.{pattern}")
            .limit(10)
            .execute()
            .data
        )
        notes = (
            self._c.table("session_notes")
            .select("id,session_id,body,tags,pinned,created_at")
            .eq("clerk_user_id", clerk_user_id)
            .ilike("body", pattern)
            .limit(20)
            .execute()
            .data
        )
        return {"sessions": sessions, "notes": notes}
