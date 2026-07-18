"""
Supabase client factory — the single place the backend touches the database.

The client is created lazily from SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY.
When either is missing (local dev without persistence, CI, an outage) the
factory returns None and every caller degrades gracefully: persistence
endpoints answer 503, and /api/research simply skips history recording.
The scoring pipeline never depends on the database.

The service-role key bypasses RLS by design; per-user scoping is enforced in
the repositories (every query filters on the Clerk-verified clerk_user_id).
RLS + revoked grants on the anon/authenticated roles make the PostgREST
surface inert for anyone who is not this backend.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger("omnisignal.db")

_client: Optional[Any] = None
_client_failed = False
_test_client: Optional[Any] = None


def is_configured() -> bool:
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"))


def get_client() -> Optional[Any]:
    """The shared Supabase client, or None when persistence is unavailable."""
    global _client, _client_failed
    if _test_client is not None:
        return _test_client
    if _client is not None:
        return _client
    if _client_failed or not is_configured():
        return None
    try:
        from supabase import create_client

        _client = create_client(
            os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        )
        logger.info("supabase client initialised")
    except Exception:  # noqa: BLE001 — persistence must never take the API down
        logger.exception("supabase client initialisation failed; persistence disabled")
        _client_failed = True
        return None
    return _client


def set_client_for_testing(client: Optional[Any]) -> None:
    """Inject a fake client in tests (None restores normal behaviour)."""
    global _test_client, _client, _client_failed
    _test_client = client
    _client = None
    _client_failed = False
