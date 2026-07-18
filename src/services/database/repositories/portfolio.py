"""Portfolio positions — ticker, shares, average cost per Clerk user."""

from __future__ import annotations

from typing import Any, Optional

from .watchlists import normalize_ticker


class PortfolioRepository:
    def __init__(self, client: Any) -> None:
        self._c = client

    def list(self, clerk_user_id: str) -> list[dict[str, Any]]:
        return (
            self._c.table("portfolio_positions")
            .select("*")
            .eq("clerk_user_id", clerk_user_id)
            .order("created_at")
            .execute()
            .data
        )

    def upsert(
        self, clerk_user_id: str, ticker: str, shares: float, average_price: float
    ) -> Optional[dict[str, Any]]:
        symbol = normalize_ticker(ticker)
        if not symbol or shares <= 0 or average_price < 0:
            return None
        rows = (
            self._c.table("portfolio_positions")
            .upsert(
                {
                    "clerk_user_id": clerk_user_id,
                    "ticker": symbol,
                    "shares": shares,
                    "average_price": average_price,
                },
                on_conflict="clerk_user_id,ticker",
            )
            .execute()
            .data
        )
        return rows[0] if rows else None

    def _owned(self, clerk_user_id: str, position_id: str) -> bool:
        rows = (
            self._c.table("portfolio_positions")
            .select("id")
            .eq("clerk_user_id", clerk_user_id)
            .eq("id", position_id)
            .limit(1)
            .execute()
            .data
        )
        return bool(rows)

    def update(
        self,
        clerk_user_id: str,
        position_id: str,
        *,
        shares: Optional[float] = None,
        average_price: Optional[float] = None,
    ) -> Optional[dict[str, Any]]:
        if not self._owned(clerk_user_id, position_id):
            return None
        patch: dict[str, Any] = {}
        if shares is not None and shares > 0:
            patch["shares"] = shares
        if average_price is not None and average_price >= 0:
            patch["average_price"] = average_price
        if not patch:
            return None
        rows = (
            self._c.table("portfolio_positions")
            .update(patch)
            .eq("id", position_id)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def delete(self, clerk_user_id: str, position_id: str) -> bool:
        if not self._owned(clerk_user_id, position_id):
            return False
        self._c.table("portfolio_positions").delete().eq("id", position_id).execute()
        return True
