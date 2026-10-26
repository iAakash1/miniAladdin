"""Price alerts, their trigger events, and the in-app notification inbox.

User-facing reads and writes are scoped to the Clerk user id on every query.
The evaluator (`src/services/alert_engine.py`) is the one caller that reads
across users, through `active_for_evaluation`, and it writes back only to the
alert it evaluated.

Deduplication lives in the database, not in the evaluator: an event's
`event_key` names the alert and the observation that triggered it and is
unique, and a notification's `event_id` is unique, so a retried or overlapping
scheduler run that sees the same observation records one trigger and one
notification.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.services.database.repositories.watchlists import normalize_ticker

MAX_ALERTS_PER_USER = 100
#: Notifications older than this are pruned when new ones arrive.
NOTIFICATION_RETENTION_DAYS = 90
MAX_NOTIFICATIONS_PER_USER = 500

KINDS = ("cross_above", "cross_below", "day_move", "period_move", "range_exit", "new_filing")
DIRECTIONS = ("up", "down", "either")
FILING_FORMS = ("10-K", "10-Q", "8-K", "S-1", "DEF 14A", "4", "13D", "13G", "10-K/A", "10-Q/A", "8-K/A")


class AlertValidationError(ValueError):
    """The definition cannot be evaluated as written."""


def _finite(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def validate_definition(body: dict[str, Any]) -> dict[str, Any]:
    """A clean alert definition, or AlertValidationError naming what is wrong."""
    kind = body.get("kind")
    if kind not in KINDS:
        raise AlertValidationError(f"kind must be one of: {', '.join(KINDS)}")
    ticker = normalize_ticker(body.get("ticker") or "")
    if not ticker:
        raise AlertValidationError("A valid ticker symbol is required.")
    out: dict[str, Any] = {"kind": kind, "ticker": ticker, "repeat": bool(body.get("repeat"))}
    threshold = _finite(body.get("threshold"))
    if kind in ("cross_above", "cross_below"):
        if threshold is None or threshold <= 0:
            raise AlertValidationError("A price threshold greater than zero is required.")
        out["threshold"] = threshold
    elif kind in ("day_move", "period_move"):
        if threshold is None or not 0 < threshold <= 100:
            raise AlertValidationError("The move threshold is a percentage between 0 and 100.")
        direction = body.get("direction") or "either"
        if direction not in DIRECTIONS:
            raise AlertValidationError("direction must be up, down or either.")
        out.update(threshold=threshold, direction=direction)
        if kind == "period_move":
            period = body.get("period_days")
            if not isinstance(period, int) or not 2 <= period <= 260:
                raise AlertValidationError("period_days must be a whole number of trading days from 2 to 260.")
            out["period_days"] = period
    elif kind == "range_exit":
        high = _finite(body.get("threshold_high"))
        if threshold is None or high is None or threshold <= 0 or high <= threshold:
            raise AlertValidationError("A range needs a low and a high price, with low below high.")
        out.update(threshold=threshold, threshold_high=high)
    elif kind == "new_filing":
        forms = [str(f).upper().strip() for f in body.get("form_types") or []]
        bad = [f for f in forms if f not in FILING_FORMS]
        if bad:
            raise AlertValidationError(f"Unsupported form types: {', '.join(bad)}.")
        out["form_types"] = forms
    note = body.get("note")
    if note is not None:
        out["note"] = str(note).strip()[:280] or None
    return out


def describe(alert: dict[str, Any]) -> str:
    """The condition in words, the same in the inbox as in the alert list."""
    kind, t = alert.get("kind"), alert.get("threshold")
    if kind == "cross_above":
        return f"{alert['ticker']} crosses above {t:,.2f}"
    if kind == "cross_below":
        return f"{alert['ticker']} crosses below {t:,.2f}"
    if kind == "day_move":
        return f"{alert['ticker']} moves {_dir(alert)}{t:g}% in a day"
    if kind == "period_move":
        return f"{alert['ticker']} moves {_dir(alert)}{t:g}% over {alert.get('period_days')} trading days"
    if kind == "range_exit":
        return f"{alert['ticker']} leaves {t:,.2f}–{alert.get('threshold_high'):,.2f}"
    if kind == "new_filing":
        forms = alert.get("form_types") or []
        return f"{alert['ticker']} files {'a ' + '/'.join(forms) if forms else 'anything'} with the SEC"
    return f"{alert.get('ticker')} {kind}"


def _dir(alert: dict[str, Any]) -> str:
    return {"up": "up ", "down": "down ", "either": "±"}.get(alert.get("direction") or "either", "±")


def _shape(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: row.get(k) for k in (
        "id", "ticker", "kind", "threshold", "threshold_high", "direction", "period_days", "status",
        "repeat", "armed", "note", "last_evaluated_at", "last_observed_value", "last_observed_at",
        "last_source", "last_result", "last_triggered_at", "created_at", "updated_at",
    )}
    out["form_types"] = list(row.get("form_types") or [])
    out["condition"] = describe(row)
    return out


class AlertsRepository:
    def __init__(self, client: Any) -> None:
        self._c = client

    # ── user-facing ──────────────────────────────────────────────────────────
    def list(self, clerk_user_id: str, ticker: Optional[str] = None) -> list[dict[str, Any]]:
        q = self._c.table("price_alerts").select("*").eq("clerk_user_id", clerk_user_id)
        if ticker:
            q = q.eq("ticker", normalize_ticker(ticker))
        return [_shape(r) for r in q.order("created_at", desc=True).execute().data]

    def _owned(self, clerk_user_id: str, alert_id: str) -> Optional[dict[str, Any]]:
        rows = (
            self._c.table("price_alerts").select("*")
            .eq("clerk_user_id", clerk_user_id).eq("id", alert_id).limit(1).execute().data
        )
        return rows[0] if rows else None

    def create(self, clerk_user_id: str, definition: dict[str, Any],
               baseline_value: Optional[float] = None, baseline_text: Optional[str] = None) -> Optional[dict[str, Any]]:
        count = len(self._c.table("price_alerts").select("id").eq("clerk_user_id", clerk_user_id).execute().data)
        if count >= MAX_ALERTS_PER_USER:
            return None
        row = self._c.table("price_alerts").insert({
            **definition, "clerk_user_id": clerk_user_id, "status": "active", "armed": True,
            "baseline_value": baseline_value, "baseline_text": baseline_text,
        }).execute().data[0]
        return _shape(row)

    def update(self, clerk_user_id: str, alert_id: str, definition: Optional[dict[str, Any]] = None,
               status: Optional[str] = None) -> Optional[dict[str, Any]]:
        current = self._owned(clerk_user_id, alert_id)
        if current is None:
            return None
        patch: dict[str, Any] = {}
        if definition is not None:
            # The symbol was checked against real data when the alert was
            # created; an edit is not, so it may change the condition only.
            if definition.get("ticker") != current.get("ticker"):
                raise AlertValidationError("An alert's security cannot be changed. Create a new alert for another security.")
            patch.update(definition)
            # A changed condition starts from scratch: the old observation and
            # arming belonged to a different question.
            patch.update(armed=True, baseline_value=None, baseline_text=None, last_result=None)
        if status is not None:
            if status not in ("active", "paused"):
                raise AlertValidationError("status can be set to active or paused.")
            patch["status"] = status
            if status == "active":
                patch["armed"] = True
                if current.get("status") != "active":
                    # Paused means not watching, and a triggered alert has
                    # already answered. Either one starts again from the next
                    # observation, so a move made while it was off is not
                    # reported as if it had just happened.
                    patch.update(baseline_value=None, baseline_text=None,
                                 last_observed_value=None, last_observed_at=None)
        if patch:
            patch["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._c.table("price_alerts").update(patch).eq("id", alert_id).eq("clerk_user_id", clerk_user_id).execute()
        return _shape(self._owned(clerk_user_id, alert_id) or current)

    def delete(self, clerk_user_id: str, alert_id: str) -> bool:
        if self._owned(clerk_user_id, alert_id) is None:
            return False
        self._c.table("price_alerts").delete().eq("id", alert_id).eq("clerk_user_id", clerk_user_id).execute()
        return True

    def events(self, clerk_user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return (
            self._c.table("alert_events").select("*").eq("clerk_user_id", clerk_user_id)
            .order("triggered_at", desc=True).limit(limit).execute().data
        )

    # ── evaluator ────────────────────────────────────────────────────────────
    def active_for_evaluation(self, limit: int = 1000) -> list[dict[str, Any]]:
        return (
            self._c.table("price_alerts").select("*").eq("status", "active")
            .order("created_at").limit(limit).execute().data
        )

    def record_evaluation(self, alert_id: str, clerk_user_id: str, patch: dict[str, Any],
                          *, evaluated: bool = True) -> None:
        """Write what a pass concluded. `last_evaluated_at` moves only when the
        condition was actually evaluated; a skip records its reason alone."""
        if evaluated:
            patch = {**patch, "last_evaluated_at": datetime.now(timezone.utc).isoformat()}
        self._c.table("price_alerts").update(patch).eq("id", alert_id).eq("clerk_user_id", clerk_user_id).execute()

    def record_trigger(self, event: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Insert the event and its notification once. None if already recorded."""
        existing = self._c.table("alert_events").select("id").eq("event_key", event["event_key"]).limit(1).execute().data
        if existing:
            return None
        try:
            row = self._c.table("alert_events").insert(event).execute().data[0]
        except Exception as exc:  # noqa: BLE001 — a unique-key race with another run
            if "duplicate" in str(exc).lower() or "unique" in str(exc).lower() or "23505" in str(exc):
                return None
            raise
        return row


class NotificationsRepository:
    def __init__(self, client: Any) -> None:
        self._c = client

    def create_for_event(self, event: dict[str, Any], title: str, body: str, link: str) -> Optional[dict[str, Any]]:
        existing = self._c.table("notifications").select("id").eq("event_id", event["id"]).limit(1).execute().data
        if existing:
            return None
        try:
            row = self._c.table("notifications").insert({
                "clerk_user_id": event["clerk_user_id"], "event_id": event["id"], "kind": "alert",
                "title": title, "body": body, "link": link,
                # Stated rather than left to the column default, so retention
                # is measured from the moment of delivery on every backend.
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute().data[0]
        except Exception as exc:  # noqa: BLE001 — duplicate delivery from a parallel run
            if "duplicate" in str(exc).lower() or "unique" in str(exc).lower() or "23505" in str(exc):
                return None
            raise
        self._prune(event["clerk_user_id"])
        return row

    def _prune(self, clerk_user_id: str) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=NOTIFICATION_RETENTION_DAYS)).isoformat()
        self._c.table("notifications").delete().eq("clerk_user_id", clerk_user_id).lte("created_at", cutoff).execute()
        rows = (
            self._c.table("notifications").select("id,created_at").eq("clerk_user_id", clerk_user_id)
            .order("created_at", desc=True).execute().data
        )
        for row in rows[MAX_NOTIFICATIONS_PER_USER:]:
            self._c.table("notifications").delete().eq("id", row["id"]).eq("clerk_user_id", clerk_user_id).execute()

    def list(self, clerk_user_id: str, unread_only: bool = False, limit: int = 50) -> dict[str, Any]:
        rows = (
            self._c.table("notifications").select("*").eq("clerk_user_id", clerk_user_id)
            .order("created_at", desc=True).execute().data
        )
        unread = sum(1 for r in rows if not r.get("read_at"))
        if unread_only:
            rows = [r for r in rows if not r.get("read_at")]
        events = {}
        event_ids = [r["event_id"] for r in rows[:limit] if r.get("event_id")]
        if event_ids:
            for e in self._c.table("alert_events").select("*").in_("id", event_ids).execute().data:
                events[e["id"]] = e
        items = []
        for r in rows[:limit]:
            e = events.get(r.get("event_id"))
            items.append({
                "id": r["id"], "kind": r.get("kind"), "title": r.get("title"), "body": r.get("body"),
                "link": r.get("link"), "read": bool(r.get("read_at")), "createdAt": r.get("created_at"),
                "event": None if e is None else {
                    k: e.get(k) for k in ("ticker", "kind", "condition_text", "observed_value", "observed_text",
                                          "threshold", "source", "source_timestamp", "freshness", "triggered_at")
                },
            })
        return {"notifications": items, "unread": unread}

    def mark_read(self, clerk_user_id: str, notification_id: Optional[str] = None) -> int:
        now = datetime.now(timezone.utc).isoformat()
        q = self._c.table("notifications").update({"read_at": now}).eq("clerk_user_id", clerk_user_id)
        if notification_id:
            q = q.eq("id", notification_id)
        return len(q.execute().data or [])
