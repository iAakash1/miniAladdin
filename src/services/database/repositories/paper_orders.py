"""Local references to paper orders: who submitted what, and how to find it.

Not a ledger. The broker is the source of truth for an order's status, fills
and the positions they produce; `last_status` is only the latest status this
product has *seen* from the broker, kept so a page reload or a restart can
find an order whose submission timed out. Nothing here is ever shown in place
of what the broker currently reports.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


class PaperOrdersRepository:
    def __init__(self, client: Any) -> None:
        self._c = client

    def by_client_id(self, client_order_id: str) -> Optional[dict[str, Any]]:
        rows = (
            self._c.table("paper_orders").select("*").eq("client_order_id", client_order_id)
            .limit(1).execute().data
        )
        return rows[0] if rows else None

    def reserve(self, clerk_user_id: str, client_order_id: str, order: dict[str, Any], origin: Optional[str]) -> bool:
        """Claim a client order id before submitting. False if it is already taken.

        The unique constraint is what makes this safe under concurrency: two
        confirmations carrying the same id cannot both reserve it.
        """
        if self.by_client_id(client_order_id) is not None:
            return False
        try:
            self._c.table("paper_orders").insert({
                "clerk_user_id": clerk_user_id, "client_order_id": client_order_id,
                "symbol": order["symbol"], "side": order["side"], "order_type": order["order_type"],
                "time_in_force": order["time_in_force"], "qty": order.get("qty"),
                "notional": order.get("notional"), "limit_price": order.get("limit_price"),
                "origin": origin, "last_status": "submitting",
            }).execute()
        except Exception as exc:  # noqa: BLE001 — lost a race for the same id
            if "duplicate" in str(exc).lower() or "unique" in str(exc).lower() or "23505" in str(exc):
                return False
            raise
        return True

    def record(self, client_order_id: str, *, broker_order_id: Optional[str] = None,
               status: Optional[str] = None, error: Optional[str] = None) -> None:
        patch: dict[str, Any] = {
            "last_reconciled_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if broker_order_id:
            patch["broker_order_id"] = broker_order_id
        if status:
            patch["last_status"] = status
        if error is not None:
            patch["last_error"] = error[:300]
        self._c.table("paper_orders").update(patch).eq("client_order_id", client_order_id).execute()

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        """Recent references for the shared account, newest first."""
        return (
            self._c.table("paper_orders").select("*").order("submitted_at", desc=True)
            .limit(limit).execute().data
        )

    def unresolved(self, limit: int = 50) -> list[dict[str, Any]]:
        """Submissions whose broker outcome has not been confirmed yet."""
        rows = self._c.table("paper_orders").select("*").in_("last_status", ["submitting", "unknown"]).execute().data
        return sorted(rows, key=lambda r: r.get("submitted_at") or "")[:limit]
