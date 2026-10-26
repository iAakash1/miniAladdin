"""The alert evaluator: one bounded pass over every active alert.

Run by the scheduler (`POST /api/internal/alerts/evaluate`), not by a browser,
so an alert fires whether or not anyone has the page open. One pass:

1. reads the active alerts,
2. fetches one quote per distinct ticker (bounded concurrency, through the
   provider families' own caches and fallback chains), plus a daily series or
   the SEC filing index only for the alerts that need one,
3. decides each alert with `decide`, a pure function,
4. writes back what it observed, and records a trigger at most once.

**What it refuses to do.** It never triggers on a quote it cannot date, on a
quote that is stale for the current market session, or on an observation it
has already evaluated (the market is closed and nothing has moved). Such an
alert is recorded as *skipped* with the reason; `last_evaluated_at` is only
advanced when the condition was actually evaluated against a usable
observation, so the page never says "checked" for a check that did not happen.

**Crossing, not level.** "Crosses above 200" fires when the previous usable
observation was below 200 and the current one is at or above it. An alert
created while the price is already above waits for it to go below and come
back. The first observation after creation is a baseline, not a trigger.

**Repeats.** A one-shot alert becomes `triggered` and stops. A repeating alert
disarms when it fires and re-arms when its condition stops holding, so a price
sitting above the line produces one notification, not one per run. Move alerts
trigger at most once per trading session.

**Deduplication** is the database's job: each trigger carries an `event_key`
naming the alert and the observation, which is unique, so a retried or
overlapping run inserts it once (`AlertsRepository.record_trigger`).
"""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from src.services.database.repositories.alerts import AlertsRepository, NotificationsRepository, describe

logger = logging.getLogger("omnisignal.alerts")

NEW_YORK = ZoneInfo("America/New_York")
SESSION_OPEN, SESSION_CLOSE = time(9, 30), time(16, 0)
#: Inside regular hours a quote older than this is stale for an alert.
INTRADAY_STALE_AFTER = timedelta(minutes=20)
LIVE_WITHIN = timedelta(minutes=2)
QUOTE_WORKERS = 6

_RUN_LOCK = threading.Lock()


# ── market session ───────────────────────────────────────────────────────────

def market_open(now: datetime) -> bool:
    """Regular US equity hours, weekdays 09:30–16:00 New York time.

    Exchange holidays are not modelled. On a holiday the market reads as open,
    quotes read as stale, and alerts are skipped as stale — the conservative
    outcome, and the reason is recorded.
    """
    local = now.astimezone(NEW_YORK)
    return local.weekday() < 5 and SESSION_OPEN <= local.time() < SESSION_CLOSE


def last_session_close(now: datetime) -> datetime:
    """The most recent regular-session close at or before `now`."""
    local = now.astimezone(NEW_YORK)
    day = local.date()
    while True:
        close = datetime.combine(day, SESSION_CLOSE, tzinfo=NEW_YORK)
        if day.weekday() < 5 and close <= local:
            return close
        day -= timedelta(days=1)


def session_date(now: datetime) -> date:
    local = now.astimezone(NEW_YORK)
    if market_open(now):
        return local.date()
    return last_session_close(now).date()


def _parse_time(value: Any) -> tuple[Optional[datetime], bool]:
    """(timestamp, date_only) from a vendor's as-of value."""
    if not value:
        return None, False
    text = str(value).strip()
    try:
        if len(text) == 10:
            d = date.fromisoformat(text)
            return datetime.combine(d, SESSION_CLOSE, tzinfo=NEW_YORK), True
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp, False
    except ValueError:
        return None, False


def freshness(as_of: Any, now: datetime) -> str:
    """live | delayed | end_of_day | stale | undated, for an alert's purposes."""
    stamp, date_only = _parse_time(as_of)
    if stamp is None:
        return "undated"
    if market_open(now):
        if date_only:
            return "stale"
        age = now - stamp
        if age <= LIVE_WITHIN:
            return "live"
        return "delayed" if age <= INTRADAY_STALE_AFTER else "stale"
    # Market closed: the last session's close (or later) is as current as it gets.
    return "end_of_day" if stamp >= last_session_close(now) - timedelta(minutes=30) else "stale"


# ── decisions ────────────────────────────────────────────────────────────────

@dataclass
class Observation:
    value: Optional[float] = None
    at: Optional[str] = None
    source: Optional[str] = None
    freshness: str = "undated"
    text: Optional[str] = None
    session: Optional[str] = None
    detail: Optional[str] = None
    unavailable: Optional[str] = None


@dataclass
class Decision:
    result: str
    evaluated: bool
    trigger: bool = False
    event_key: Optional[str] = None
    patch: dict[str, Any] = field(default_factory=dict)


def _skip(reason: str) -> Decision:
    return Decision(result=f"skipped: {reason}", evaluated=False, patch={"last_result": f"skipped: {reason}"})


def decide(alert: dict[str, Any], obs: Observation) -> Decision:
    """What one observation means for one alert. Pure: no I/O."""
    kind = alert["kind"]
    if obs.unavailable:
        return _skip(obs.unavailable)

    if kind == "new_filing":
        if not obs.text:
            return _skip("no filing index")
        seen = alert.get("baseline_text")
        patch: dict[str, Any] = {
            "last_observed_at": obs.at, "last_source": obs.source, "baseline_text": obs.text,
        }
        if seen is None:
            return Decision("baseline set", True, patch={**patch, "last_result": "baseline set"})
        if obs.text == seen:
            return Decision("no new filing", True, patch={**patch, "last_result": "no new filing"})
        return _triggered(alert, obs, patch, key=f"{alert['id']}:filing:{obs.text}")

    if obs.value is None or not math.isfinite(obs.value):
        return _skip("no usable value")
    if obs.freshness in ("stale", "undated"):
        return _skip("quote has no timestamp" if obs.freshness == "undated" else "quote is stale")
    if _same_instant(obs.at, alert.get("last_observed_at")) and alert.get("last_observed_value") == obs.value:
        return _skip("no new observation")

    value = obs.value
    patch = {"last_observed_value": value, "last_observed_at": obs.at, "last_source": obs.source}
    previous = alert.get("last_observed_value")
    if previous is None:
        previous = alert.get("baseline_value")
    armed = alert.get("armed", True)
    t = alert.get("threshold")

    if kind in ("cross_above", "cross_below"):
        above = kind == "cross_above"
        holds = value >= t if above else value <= t
        if previous is None:
            return Decision("baseline set", True, patch={**patch, "last_result": "baseline set"})
        crossed = (previous < t <= value) if above else (previous > t >= value)
        if not holds and not armed:
            patch["armed"] = True          # condition released: a repeat may fire again
        if crossed and armed:
            return _triggered(alert, obs, patch, key=f"{alert['id']}:{kind}:{obs.at}")
        return Decision("condition met, already notified" if holds else "not crossed", True,
                        patch={**patch, "last_result": "holding" if holds else "not crossed"})

    if kind == "range_exit":
        low, high = t, alert.get("threshold_high")
        inside = low <= value <= high
        was_inside = previous is not None and low <= previous <= high
        if inside:
            patch["armed"] = True
            return Decision("inside range", True, patch={**patch, "last_result": "inside range"})
        if previous is None or not was_inside or not armed:
            return Decision("outside range", True, patch={**patch, "last_result": "outside range"})
        return _triggered(alert, obs, patch, key=f"{alert['id']}:range_exit:{obs.at}")

    if kind in ("day_move", "period_move"):
        if obs.detail is None:
            return _skip("no reference close")
        move = value  # already a percentage for move alerts
        direction = alert.get("direction") or "either"
        hit = (move >= t if direction == "up" else move <= -t if direction == "down" else abs(move) >= t)
        if not hit:
            return Decision("within threshold", True, patch={**patch, "last_result": "within threshold"})
        return _triggered(alert, obs, patch, key=f"{alert['id']}:{kind}:{obs.session}")

    return _skip(f"unsupported kind {kind}")


def _same_instant(a: Any, b: Any) -> bool:
    """Two timestamps naming the same moment, however each was formatted."""
    if not a or not b:
        return False
    first, _ = _parse_time(a)
    second, _ = _parse_time(b)
    return first is not None and first == second


def _triggered(alert: dict[str, Any], obs: Observation, patch: dict[str, Any], key: str) -> Decision:
    patch = {**patch, "last_result": "triggered", "last_triggered_at": datetime.now(timezone.utc).isoformat()}
    if alert.get("repeat"):
        patch["armed"] = False
    else:
        patch["status"] = "triggered"
    return Decision("triggered", True, trigger=True, event_key=key, patch=patch)


# ── observations ─────────────────────────────────────────────────────────────

QuoteFn = Callable[[str], Any]
SeriesFn = Callable[[str], Any]
FilingsFn = Callable[[str], Any]


def _default_quote(symbol: str):
    from src import providers
    return providers.market_data.get_price(symbol)


def _default_series(symbol: str):
    from src import providers
    return providers.market_data.get_series(symbol, "1y")


def _default_filings(symbol: str):
    from src import providers
    return providers.filings.sec.get_filings(symbol, limit=20)


def _quote_observation(result: Any, now: datetime) -> Observation:
    if result is None or not getattr(result, "ok", False) or getattr(result, "data", None) is None:
        reason = "no quote (provider outage)" if getattr(result, "outage", False) else "no quote"
        return Observation(unavailable=reason)
    q = result.data
    fresh = freshness(q.as_of, now)
    stamp, _ = _parse_time(q.as_of)
    return Observation(
        value=float(q.price), at=stamp.isoformat() if stamp else None, source=result.source,
        freshness=fresh, session=session_date(now).isoformat(),
    )


def _move_observation(alert: dict[str, Any], quote: Observation, quote_result: Any, series_result: Any) -> Observation:
    """A percentage move for day/period alerts, from the quote and a reference close."""
    if quote.unavailable or quote.value is None:
        return quote
    reference: Optional[float] = None
    if alert["kind"] == "day_move":
        prev = getattr(getattr(quote_result, "data", None), "previous_close", None)
        if prev and math.isfinite(prev) and prev > 0:
            reference = float(prev)
    if reference is None:
        bars = getattr(getattr(series_result, "data", None), "bars", None) or []
        today = quote.session
        # The reference is counted in sessions before the one the quote belongs to.
        prior = [b for b in bars if str(b.date)[:10] < (today or "9999")]
        n = 1 if alert["kind"] == "day_move" else int(alert.get("period_days") or 0)
        if n and len(prior) >= n:
            close = prior[-n].close
            if close and math.isfinite(close) and close > 0:
                reference = float(close)
    if reference is None:
        return Observation(unavailable="not enough history for the reference close")
    move = (quote.value / reference - 1) * 100
    return Observation(
        value=round(move, 4), at=quote.at, source=quote.source, freshness=quote.freshness,
        session=quote.session, detail=f"{quote.value:,.2f} vs {reference:,.2f}",
    )


def _filing_observation(filings: Any, forms: list[str], now: datetime) -> Observation:
    if not isinstance(filings, list):
        return Observation(unavailable="no filing index")
    wanted = [f for f in filings if not forms or str(f.get("form", "")).upper() in forms]
    if not wanted:
        return Observation(text="none", at=None, source="sec", freshness="end_of_day")
    latest = wanted[0]
    return Observation(
        text=latest.get("accession"), at=latest.get("filed_at"), source="sec", freshness="end_of_day",
        detail=f"{latest.get('form')} filed {latest.get('filed_at')}",
    )


# ── the pass ─────────────────────────────────────────────────────────────────

def run(
    client: Any, *, now: Optional[datetime] = None,
    quote_fn: QuoteFn = _default_quote, series_fn: SeriesFn = _default_series,
    filings_fn: FilingsFn = _default_filings, limit: int = 1000,
) -> dict[str, Any]:
    """Evaluate every active alert once. Safe to call repeatedly and concurrently."""
    if not _RUN_LOCK.acquire(blocking=False):
        return {"status": "already_running"}
    try:
        return _run(client, now or datetime.now(timezone.utc), quote_fn, series_fn, filings_fn, limit)
    finally:
        _RUN_LOCK.release()


def _run(client, now, quote_fn, series_fn, filings_fn, limit) -> dict[str, Any]:
    from src.providers.parallel import map_concurrent

    alerts_repo, inbox = AlertsRepository(client), NotificationsRepository(client)
    alerts = alerts_repo.active_for_evaluation(limit)
    price_tickers = sorted({a["ticker"] for a in alerts if a["kind"] != "new_filing"})
    series_tickers = sorted({a["ticker"] for a in alerts if a["kind"] in ("day_move", "period_move")})
    filing_tickers = sorted({a["ticker"] for a in alerts if a["kind"] == "new_filing"})

    def fetch(fn, tickers, label):
        outcomes = map_concurrent(fn, tickers, workers=QUOTE_WORKERS, label=label)
        return {t: (o.value if o.ok else None) for t, o in zip(tickers, outcomes)}

    quotes = fetch(quote_fn, price_tickers, "alerts.quotes")
    series = fetch(series_fn, series_tickers, "alerts.series")
    filings = fetch(filings_fn, filing_tickers, "alerts.filings")

    summary = {"status": "ok", "alerts": len(alerts), "evaluated": 0, "triggered": 0,
               "notifications": 0, "skipped": {}, "market_open": market_open(now)}
    for alert in alerts:
        try:
            if alert["kind"] == "new_filing":
                obs = _filing_observation(filings.get(alert["ticker"]), list(alert.get("form_types") or []), now)
            else:
                quote = _quote_observation(quotes.get(alert["ticker"]), now)
                obs = (_move_observation(alert, quote, quotes.get(alert["ticker"]), series.get(alert["ticker"]))
                       if alert["kind"] in ("day_move", "period_move") else quote)
            decision = decide(alert, obs)
        except Exception:  # noqa: BLE001 — one bad alert never stops the pass
            logger.exception("alert %s could not be evaluated", alert.get("id"))
            decision = _skip("evaluation error")

        if decision.evaluated:
            summary["evaluated"] += 1
        else:
            summary["skipped"][decision.result] = summary["skipped"].get(decision.result, 0) + 1
        alerts_repo.record_evaluation(alert["id"], alert["clerk_user_id"], decision.patch,
                                      evaluated=decision.evaluated)

        if decision.trigger and decision.event_key:
            event = alerts_repo.record_trigger({
                "event_key": decision.event_key, "alert_id": alert["id"],
                "clerk_user_id": alert["clerk_user_id"], "ticker": alert["ticker"], "kind": alert["kind"],
                "condition_text": describe(alert),
                "observed_value": obs.value if alert["kind"] != "new_filing" else None,
                "observed_text": obs.detail or obs.text, "threshold": alert.get("threshold"),
                "source": obs.source, "source_timestamp": obs.at,
                "freshness": obs.freshness if obs.freshness in ("live", "delayed", "end_of_day", "stale") else None,
            })
            if event is not None:
                summary["triggered"] += 1
                title = f"{describe(alert)}"
                body = _body(alert, obs)
                if inbox.create_for_event(event, title, body, f"/company/{alert['ticker']}") is not None:
                    summary["notifications"] += 1
    logger.info("alerts pass: %s", summary)
    return summary


def _when(at: Optional[str]) -> str:
    """The observation's own time, in UTC and to the minute, as every other
    timestamp in the product is shown. A date-only stamp is a session close."""
    if not at:
        return "unknown time"
    if len(at) == 10:
        return f"close of {at}"
    try:
        t = datetime.fromisoformat(at.replace("Z", "+00:00"))
    except ValueError:
        return at
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _body(alert: dict[str, Any], obs: Observation) -> str:
    when = _when(obs.at)
    if alert["kind"] == "new_filing":
        return f"{obs.detail or 'A new filing'} (SEC EDGAR)."
    if alert["kind"] in ("day_move", "period_move"):
        return f"Moved {obs.value:+.2f}% ({obs.detail}) — {obs.freshness.replace('_', ' ')} quote from {obs.source}, {when}."
    return f"Observed {obs.value:,.2f} — {obs.freshness.replace('_', ' ')} quote from {obs.source}, {when}."
