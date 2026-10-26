"""The paper-order workflow: validate, preview, submit once, reconcile.

The broker client (`src/broker/alpaca_paper.py`) only talks to the paper host
and reports what the broker said. This module is the workflow around it, and
it holds three rules:

**An order is submitted at most once.** Every submission carries a client
order id chosen *before* the request — at preview time, so the id the operator
reviewed is the id that is sent. Before sending, the broker is asked whether an
order with that id already exists; if it does, that order is returned and
nothing is sent. If the submission times out, or the broker answers 5xx, the
order may or may not exist, so it is looked up by the same id — never sent
again. If it still cannot be found, the outcome is reported as *unknown* and
left for reconciliation; it is not guessed.

**The broker is the source of truth.** A local `paper_orders` row records who
submitted what and the last status seen, for audit and for reconciling after a
reload or a restart. It is never shown in place of the broker's current word.

**Nothing here executes a research signal.** An order exists only because an
operator built a ticket, reviewed it and confirmed it.
"""

from __future__ import annotations

import logging
import math
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from src.broker.alpaca_paper import BrokerUnavailable

logger = logging.getLogger("omnisignal.paper")

SIDES = ("buy", "sell")
ORDER_TYPES = ("market", "limit")
TIME_IN_FORCE = ("day", "gtc", "ioc", "fok", "opg", "cls")
ORIGINS = ("ticket", "watchlist", "research", "position")
CLIENT_ORDER_ID = re.compile(r"^[A-Za-z0-9-]{8,128}$")
SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
#: How long to keep asking the broker about a submission that timed out.
RECONCILE_ATTEMPTS = 3
RECONCILE_DELAY_SECONDS = 0.8
#: Broker statuses after which an order can no longer change.
TERMINAL = ("filled", "canceled", "expired", "rejected", "replaced", "done_for_day", "stopped", "suspended")

HISTORY_PERIODS = ("1D", "1W", "1M", "3M", "6M", "1A")
HISTORY_TIMEFRAMES = ("5Min", "15Min", "1H", "1D")
_INTRADAY_PERIODS = ("1D", "1W")


def new_client_order_id() -> str:
    return f"omni-{uuid.uuid4().hex}"


def _num(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def normalize(req: Any) -> dict[str, Any]:
    """The order as plain data, with case and whitespace normalized."""
    return {
        "symbol": (getattr(req, "symbol", "") or "").strip().upper(),
        "side": (getattr(req, "side", "") or "").strip().lower(),
        "order_type": (getattr(req, "order_type", "") or "").strip().lower(),
        "time_in_force": (getattr(req, "time_in_force", "") or "").strip().lower(),
        "qty": getattr(req, "qty", None),
        "notional": getattr(req, "notional", None),
        "limit_price": getattr(req, "limit_price", None),
        "client_order_id": getattr(req, "client_order_id", None),
        "origin": getattr(req, "origin", None),
    }


def validate(order: dict[str, Any]) -> list[str]:
    """Everything wrong with the order, in words an operator can act on."""
    problems: list[str] = []
    if not SYMBOL.match(order["symbol"]):
        problems.append("Symbol is not a valid ticker.")
    if order["side"] not in SIDES:
        problems.append("Side must be buy or sell.")
    if order["order_type"] not in ORDER_TYPES:
        problems.append("Order type must be market or limit.")
    if order["time_in_force"] not in TIME_IN_FORCE:
        problems.append(f"Time in force must be one of: {', '.join(TIME_IN_FORCE)}.")

    qty, notional = order["qty"], order["notional"]
    if (qty is None) == (notional is None):
        problems.append("Give a share quantity or a dollar amount, not both.")
    if qty is not None:
        if not isinstance(qty, (int, float)) or not math.isfinite(qty):
            problems.append("Quantity is not a number.")
        elif qty <= 0:
            problems.append("Quantity must be greater than zero.")
        elif qty != int(qty) and not (order["order_type"] == "market" and order["time_in_force"] == "day"):
            problems.append("Fractional quantities are only accepted for market orders good for the day.")
    if notional is not None:
        if not isinstance(notional, (int, float)) or not math.isfinite(notional):
            problems.append("Dollar amount is not a number.")
        elif notional < 1:
            problems.append("A dollar-amount order must be at least $1.")
        if order["order_type"] != "market" or order["time_in_force"] != "day":
            problems.append("Dollar-amount orders must be market orders good for the day.")

    limit = order["limit_price"]
    if order["order_type"] == "limit":
        if limit is None:
            problems.append("A limit order needs a limit price.")
    elif limit is not None:
        problems.append("Only a limit order takes a limit price.")
    if limit is not None:
        # Said apart, as for quantity: "not a number" and "zero" have different fixes.
        if not isinstance(limit, (int, float)) or not math.isfinite(limit):
            problems.append("Limit price is not a number.")
        elif limit <= 0:
            problems.append("Limit price must be greater than zero.")

    cid = order["client_order_id"]
    if cid is not None and not CLIENT_ORDER_ID.match(cid):
        problems.append("The order reference is malformed; preview the order again.")
    if order["origin"] is not None and order["origin"] not in ORIGINS:
        problems.append("Unknown order origin.")
    return problems


# ── preview ──────────────────────────────────────────────────────────────────

def preview(client: Any, order: dict[str, Any], quote_fn: Callable[[str], Any], now: Optional[datetime] = None) -> dict[str, Any]:
    """Validate and price an order against the broker and the latest quote. Places nothing."""
    from src.services.alert_engine import freshness

    now = now or datetime.now(timezone.utc)
    problems = validate(order)
    warnings: list[str] = []
    symbol = order["symbol"]

    asset: Optional[dict[str, Any]] = None
    if not problems:
        try:
            asset = client.asset(symbol)
        except BrokerUnavailable as e:
            if e.kind == "not_found":
                problems.append(f"{symbol} is not an asset this paper account can trade.")
            else:
                raise
        if asset is not None:
            if not asset.get("tradable"):
                problems.append(f"{symbol} is not currently tradable.")
            fractional = (order["qty"] is not None and order["qty"] != int(order["qty"])) or order["notional"] is not None
            if fractional and not asset.get("fractionable"):
                problems.append(f"{symbol} cannot be traded in fractional shares or by dollar amount.")

    account = client.account()
    buying_power = _num(account.get("buying_power"))
    if account.get("trading_blocked") or account.get("account_blocked"):
        problems.append("The paper account is blocked from trading.")

    clock: Optional[dict[str, Any]] = None
    try:
        clock = client.clock()
    except BrokerUnavailable:
        warnings.append("The market clock could not be read; session status is unknown.")
    if clock is not None and not clock.get("is_open"):
        warnings.append(
            f"The market is closed. A {order['time_in_force']} order will wait for the next session"
            f"{' (' + str(clock.get('next_open')) + ')' if clock.get('next_open') else ''}."
        )

    quote = quote_fn(symbol) if symbol and SYMBOL.match(symbol) else None
    price = as_of = source = None
    fresh = "unavailable"
    if quote is not None and getattr(quote, "ok", False) and getattr(quote, "data", None) is not None:
        price, as_of, source = float(quote.data.price), quote.data.as_of, quote.source
        fresh = freshness(as_of, now)
    if price is None:
        warnings.append("No current price is available, so the order cannot be valued before it is placed.")
    elif fresh in ("stale", "undated"):
        warnings.append("The last known price is stale or undated; the estimate below may be far from the fill.")

    estimate_value = estimate_qty = None
    if price is not None:
        if order["qty"] is not None:
            estimate_value = price * order["qty"]
        elif order["notional"] is not None:
            estimate_value = order["notional"]
            estimate_qty = order["notional"] / price
    if order["order_type"] == "limit" and order["limit_price"] is not None and order["qty"] is not None:
        # A limit order cannot cost more than its limit, whatever the last price.
        estimate_value = order["limit_price"] * order["qty"]

    if (order["side"] == "buy" and estimate_value is not None and buying_power is not None
            and estimate_value > buying_power):
        problems.append(f"Estimated cost {estimate_value:,.2f} exceeds paper buying power {buying_power:,.2f}.")

    if order["side"] == "sell" and order["qty"] is not None:
        try:
            held = next((p for p in client.positions() if str(p.get("symbol", "")).upper() == symbol), None)
        except BrokerUnavailable:
            held = None
            warnings.append("Positions could not be read to check this sale against what is held.")
        held_qty = _num(held.get("qty")) if held else 0.0
        if held_qty is not None and order["qty"] > max(held_qty, 0.0):
            warnings.append(
                f"This sells more than the {held_qty:g} shares held, which would open or enlarge a short position "
                "if the account allows shorting."
            )

    return {
        "ok": not problems, "problems": problems, "warnings": warnings,
        "order": {k: order[k] for k in ("symbol", "side", "order_type", "time_in_force", "qty", "notional", "limit_price")},
        # The reference the confirmation must carry, so the reviewed order is
        # the one sent and a resend cannot become a second order.
        "client_order_id": order["client_order_id"] or new_client_order_id(),
        "quote": {"price": price, "as_of": as_of, "source": source, "freshness": fresh},
        "estimate": {
            "value": estimate_value, "qty": estimate_qty,
            "basis": ("limit price × quantity" if order["order_type"] == "limit" and order["qty"] is not None
                      else "last price known to this product — not a firm quote"),
        },
        "buying_power": buying_power,
        "market_open": None if clock is None else bool(clock.get("is_open")),
        "asset": None if asset is None else {
            k: asset.get(k) for k in ("tradable", "fractionable", "shortable", "exchange", "name")
        },
        "environment": "paper",
    }


# ── submit and reconcile ─────────────────────────────────────────────────────

def _record(repo: Any, cid: str, **kw: Any) -> None:
    if repo is None:
        return
    try:
        repo.record(cid, **kw)
    except Exception:  # noqa: BLE001 — the broker's answer stands even if the audit write fails
        logger.exception("could not record paper order %s", cid)


def _find(client: Any, cid: str, sleep: Callable[[float], None], attempts: int) -> Optional[dict[str, Any]]:
    for attempt in range(attempts):
        if attempt:
            sleep(RECONCILE_DELAY_SECONDS * attempt)
        try:
            found = client.order_by_client_id(cid)
        except BrokerUnavailable as e:
            if e.kind in ("credentials", "invalid"):
                raise
            continue
        if found:
            return found
    return None


def submit(
    client: Any, order: dict[str, Any], user: str, repo: Any = None,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[int, dict[str, Any]]:
    """Submit once, or report what the broker already has. Returns (http_status, body)."""
    problems = validate(order)
    if problems:
        return 422, {"detail": "; ".join(problems)}
    cid = order["client_order_id"] or new_client_order_id()

    if repo is not None:
        try:
            reserved = repo.reserve(user, cid, order, order.get("origin"))
        except Exception:  # noqa: BLE001 — no audit table: the broker lookup below still guards
            logger.exception("could not reserve paper order %s", cid)
            reserved = True
        if not reserved:
            existing = _find(client, cid, sleep, 1)
            if existing:
                return 200, {"order": existing, "client_order_id": cid, "replayed": True}
            return 202, {"outcome": "unknown", "client_order_id": cid,
                         "detail": "This order reference was already submitted and its outcome is being reconciled."}

    existing = _find(client, cid, sleep, 1)
    if existing:
        _record(repo, cid, broker_order_id=existing.get("id"), status=existing.get("status"))
        return 200, {"order": existing, "client_order_id": cid, "replayed": True}

    try:
        placed = client.submit_order(
            symbol=order["symbol"], side=order["side"], qty=order["qty"], notional=order["notional"],
            order_type=order["order_type"], time_in_force=order["time_in_force"],
            limit_price=order["limit_price"], client_order_id=cid,
        )
    except BrokerUnavailable as e:
        if e.ambiguous:
            found = _find(client, cid, sleep, RECONCILE_ATTEMPTS)
            if found:
                _record(repo, cid, broker_order_id=found.get("id"), status=found.get("status"))
                return 201, {"order": found, "client_order_id": cid, "reconciled_after": e.kind}
            _record(repo, cid, status="unknown", error=str(e))
            return 202, {
                "outcome": "unknown", "client_order_id": cid,
                "detail": "The broker did not confirm this order and it was not found yet. It was not resent; "
                          "check its status before placing another.",
            }
        _record(repo, cid, status="rejected" if e.kind in ("refused", "invalid") else "failed", error=str(e))
        if e.kind == "credentials":
            return 502, {"detail": "The paper credentials were rejected by the broker. Nothing was placed."}
        if e.kind == "rate_limited":
            return 503, {"detail": "The broker is rate limiting requests. Nothing was placed; try again shortly."}
        return 422, {"detail": f"The broker refused the order: {e}"}

    _record(repo, cid, broker_order_id=placed.get("id"), status=placed.get("status"))
    return 201, {"order": placed, "client_order_id": cid}


def reconcile(client: Any, cid: str, repo: Any = None) -> dict[str, Any]:
    """What the broker currently says about a client order id."""
    found = client.order_by_client_id(cid)
    if found:
        _record(repo, cid, broker_order_id=found.get("id"), status=found.get("status"))
        return {"found": True, "order": found, "client_order_id": cid}
    local = repo.by_client_id(cid) if repo is not None else None
    return {"found": False, "client_order_id": cid,
            "local_status": local.get("last_status") if local else None}


def reconcile_unresolved(client: Any, repo: Any) -> list[dict[str, Any]]:
    """Resolve submissions left `submitting` or `unknown` by a timeout, reload or restart."""
    out = []
    for row in repo.unresolved():
        try:
            out.append(reconcile(client, row["client_order_id"], repo))
        except BrokerUnavailable as e:
            out.append({"found": None, "client_order_id": row["client_order_id"], "error": e.kind})
    return out


def cancel(client: Any, order_id: str) -> tuple[int, dict[str, Any]]:
    """Request cancellation and report the broker's resulting state, whatever it is."""
    try:
        client.cancel_order(order_id)
    except BrokerUnavailable as e:
        if e.kind in ("invalid", "refused"):
            # Usually: already filled, already canceled, or pending replace.
            try:
                current = client.order(order_id)
            except BrokerUnavailable:
                current = None
            return 409, {"detail": f"The broker would not cancel this order: {e}", "order": current}
        if e.kind == "not_found":
            return 404, {"detail": "The broker has no order with that id."}
        raise
    try:
        current = client.order(order_id)
    except BrokerUnavailable:
        current = None
    # Cancellation is a request: the broker may still report pending_cancel,
    # or even filled if the fill won the race. Its word is what is shown.
    return 200, {"requested": True, "order": current}


# ── account views ────────────────────────────────────────────────────────────

def connection(build: Callable[[], Any]) -> dict[str, Any]:
    """Configured? Accepted? Allowed to trade? From a real account read."""
    from src.broker.alpaca_paper import BrokerMisconfigured

    try:
        client = build()
    except BrokerMisconfigured as e:
        return {"state": "not_configured", "detail": str(e)}
    try:
        account = client.account()
    except BrokerUnavailable as e:
        state = {"credentials": "credentials_rejected", "refused": "restricted",
                 "rate_limited": "rate_limited"}.get(e.kind, "unavailable")
        return {"state": state, "detail": str(e)}
    blocked = bool(account.get("trading_blocked") or account.get("account_blocked"))
    return {
        "state": "blocked" if blocked else "connected",
        "account_status": account.get("status"),
        "trading_blocked": bool(account.get("trading_blocked")),
        "account_blocked": bool(account.get("account_blocked")),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def history_params(period: str, timeframe: str) -> list[str]:
    problems = []
    if period not in HISTORY_PERIODS:
        problems.append(f"period must be one of: {', '.join(HISTORY_PERIODS)}")
    if timeframe not in HISTORY_TIMEFRAMES:
        problems.append(f"timeframe must be one of: {', '.join(HISTORY_TIMEFRAMES)}")
    if not problems and timeframe != "1D" and period not in _INTRADAY_PERIODS:
        problems.append("intraday timeframes cover at most a week here; use 1D for longer periods")
    return problems


def history_points(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """The broker's portfolio history as points, dropping windows with no equity."""
    stamps = raw.get("timestamp") or []
    equity = raw.get("equity") or []
    pl = raw.get("profit_loss") or []
    plp = raw.get("profit_loss_pct") or []
    points = []
    for i, t in enumerate(stamps):
        e = _num(equity[i]) if i < len(equity) else None
        if e is None:
            continue
        points.append({
            "t": t, "equity": e,
            "profit_loss": _num(pl[i]) if i < len(pl) else None,
            "profit_loss_pct": _num(plp[i]) if i < len(plp) else None,
        })
    return points


def analytics(account: dict[str, Any], positions: list[dict[str, Any]], orders: list[dict[str, Any]]) -> dict[str, Any]:
    """Account figures, separating what the broker reported from what is derived here.

    Conventions:
      * `reported` fields are the broker's own, unchanged.
      * `day_change` = equity − last_equity, both broker fields (last_equity is
        the previous session's closing equity).
      * position weights are market value over the sum of absolute market
        values, so a short counts as exposure, not as negative weight.
      * nothing is annualized, and no ratio (Sharpe, drawdown, win rate) is
        computed from an account history this short and irregular.
      * realized P&L is not reported by these endpoints and is left absent.
    """
    equity, last_equity = _num(account.get("equity")), _num(account.get("last_equity"))
    reported = {k: _num(account.get(k)) for k in (
        "equity", "last_equity", "cash", "buying_power", "long_market_value", "short_market_value", "portfolio_value",
    )}
    rows = []
    for p in positions:
        mv = _num(p.get("market_value"))
        rows.append({
            "symbol": p.get("symbol"), "market_value": mv, "unrealized_pl": _num(p.get("unrealized_pl")),
            "unrealized_plpc": _num(p.get("unrealized_plpc")), "side": p.get("side"),
        })
    gross = sum(abs(r["market_value"]) for r in rows if r["market_value"] is not None)
    for r in rows:
        r["weight"] = (abs(r["market_value"]) / gross) if gross and r["market_value"] is not None else None
    ranked = sorted((r for r in rows if r["unrealized_plpc"] is not None), key=lambda r: r["unrealized_plpc"])
    statuses: dict[str, int] = {}
    for o in orders:
        statuses[str(o.get("status"))] = statuses.get(str(o.get("status")), 0) + 1
    unrealized = [r["unrealized_pl"] for r in rows if r["unrealized_pl"] is not None]
    return {
        "reported": reported,
        "derived": {
            "day_change": (equity - last_equity) if equity is not None and last_equity is not None else None,
            "day_change_pct": ((equity / last_equity - 1) * 100) if equity is not None and last_equity else None,
            "unrealized_pl_total": sum(unrealized) if unrealized else (0.0 if not rows else None),
            "gross_exposure": gross if rows else 0.0,
            "cash_share": (reported["cash"] / equity) if equity and reported["cash"] is not None else None,
            "largest_weight": max((r["weight"] for r in rows if r["weight"] is not None), default=None),
            "positions": len(rows),
        },
        "weights": sorted(rows, key=lambda r: -(r["weight"] or 0)),
        "best": ranked[-1] if ranked else None,
        "worst": ranked[0] if ranked else None,
        "order_activity": statuses,
        "realized_pl": None,
        "label": "Simulated paper-trading results. Paper fills do not reproduce real execution.",
    }
