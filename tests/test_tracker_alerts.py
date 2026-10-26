"""Watchlists, alerts, the evaluator and the notification inbox.

Run against the same in-memory database double as the persistence tests, and
through the real FastAPI app where the HTTP contract matters. Quotes come from
controlled fixtures handed to the evaluator; no test reaches a vendor.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.index as api_module
from src.providers.schemas import PriceQuote
from src.services import alert_engine, database
from src.services.alert_engine import Observation, decide, freshness, market_open
from src.services.clerk_auth import require_clerk_user
from src.services.database.repositories import AlertsRepository, NotificationsRepository, WatchlistsRepository
from src.services.database.repositories.alerts import AlertValidationError, validate_definition
from test_persistence import USER_A, USER_B, FakeSupabase

# A Tuesday, mid-session in New York (14:30 UTC = 10:30 EDT).
OPEN = datetime(2026, 10, 20, 14, 30, tzinfo=timezone.utc)
# The same Tuesday after the close.
CLOSED = datetime(2026, 10, 20, 22, 0, tzinfo=timezone.utc)


@pytest.fixture()
def fake() -> FakeSupabase:
    return FakeSupabase()


@pytest.fixture()
def client(fake):
    api_module.app.dependency_overrides[require_clerk_user] = lambda: USER_A
    database.set_client_for_testing(fake)
    try:
        yield TestClient(api_module.app)
    finally:
        api_module.app.dependency_overrides.pop(require_clerk_user, None)
        database.set_client_for_testing(None)


def _quote(price, as_of, prev=None, source="massive", outage=False):
    if price is None:
        return SimpleNamespace(ok=False, data=None, source="", outage=outage, stale=False, cached=False)
    return SimpleNamespace(ok=True, data=PriceQuote(symbol="AAPL", price=price, as_of=as_of, previous_close=prev),
                           source=source, outage=False, stale=False, cached=False)


# ── watchlists ───────────────────────────────────────────────────────────────

class TestWatchlists:
    def test_lists_order_default_notes_tags_and_moves(self, fake):
        repo = WatchlistsRepository(fake)
        core = repo.create(USER_A, "Core Holdings", ["aapl", "msft", "AAPL"])
        assert core["tickers"] == ["AAPL", "MSFT"] and core["isDefault"] is True
        risk = repo.create(USER_A, "High-Risk Ideas")
        assert risk["isDefault"] is False

        assert repo.add(USER_A, core["id"], "nvda") == "added"
        assert repo.add(USER_A, core["id"], "NVDA") == "exists"
        assert repo.add(USER_A, core["id"], "$$$") == "invalid"
        assert repo.reorder_items(USER_A, core["id"], ["NVDA", "AAPL", "MSFT"])
        assert not repo.reorder_items(USER_A, core["id"], ["NVDA", "AAPL"]), "an order must name every symbol"
        assert repo.update_item(USER_A, core["id"], "aapl", note="core position", tags=["Mega Cap", "mega cap", "tech!"])

        assert repo.move_item(USER_A, core["id"], risk["id"], "AAPL") == "moved"
        lists = {w["name"]: w for w in repo.list_with_items(USER_A)}
        assert lists["Core Holdings"]["tickers"] == ["NVDA", "MSFT"]
        moved = lists["High-Risk Ideas"]["items"][0]
        assert moved["ticker"] == "AAPL" and moved["note"] == "core position" and moved["tags"] == ["mega cap", "tech"]

        assert repo.update(USER_A, risk["id"], is_default=True, sort_key="change_pct")
        lists = {w["name"]: w for w in repo.list_with_items(USER_A)}
        assert lists["High-Risk Ideas"]["isDefault"] and not lists["Core Holdings"]["isDefault"]
        assert lists["High-Risk Ideas"]["sortKey"] == "change_pct"
        assert not repo.update(USER_A, risk["id"], sort_key="by-vibes")

        order = [lists["High-Risk Ideas"]["id"], lists["Core Holdings"]["id"]]
        assert repo.reorder_lists(USER_A, order)
        assert [w["name"] for w in repo.list_with_items(USER_A)] == ["High-Risk Ideas", "Core Holdings"]

    def test_another_user_cannot_read_or_change_a_list(self, fake):
        repo = WatchlistsRepository(fake)
        mine = repo.create(USER_A, "Mine", ["AAPL"])
        assert repo.get(USER_B, mine["id"]) is None
        assert repo.add(USER_B, mine["id"], "TSLA") == "not_found"
        assert not repo.update(USER_B, mine["id"], name="stolen")
        assert not repo.delete(USER_B, mine["id"])
        assert repo.move_item(USER_B, mine["id"], mine["id"], "AAPL") in ("not_found", "exists")
        assert repo.get(USER_A, mine["id"])["tickers"] == ["AAPL"]

    def test_deleting_a_list_leaves_no_orphaned_items(self, fake):
        repo = WatchlistsRepository(fake)
        wl = repo.create(USER_A, "Temp", ["AAPL", "MSFT"])
        assert repo.delete(USER_A, wl["id"])
        assert [i for i in fake.store.get("watchlist_items", []) if i["watchlist_id"] == wl["id"]] == []

    def test_the_tracker_workflow_survives_a_reload(self, client):
        """Create a list, add a symbol, read it back as a new page load would, remove it."""
        wl = client.post("/api/watchlists", json={"name": "Earnings Watch"}).json()
        assert client.post(f"/api/watchlists/{wl['id']}/tickers", json={"ticker": "aapl"}).json()["outcome"] == "added"
        assert client.post(f"/api/watchlists/{wl['id']}/tickers", json={"ticker": "AAPL"}).json()["outcome"] == "exists"
        assert client.patch(f"/api/watchlists/{wl['id']}/tickers/AAPL", json={"note": "reports Thursday"}).status_code == 200

        reloaded = client.get(f"/api/watchlists/{wl['id']}").json()
        assert reloaded["tickers"] == ["AAPL"] and reloaded["items"][0]["note"] == "reports Thursday"

        assert client.delete(f"/api/watchlists/{wl['id']}/tickers/AAPL").status_code == 200
        assert client.get(f"/api/watchlists/{wl['id']}").json()["tickers"] == []
        assert client.post(f"/api/watchlists/{wl['id']}/tickers", json={"ticker": "!!"}).status_code == 422
        assert client.get("/api/watchlists/not-mine").status_code == 404


# ── alert definitions ────────────────────────────────────────────────────────

class TestAlertDefinitions:
    @pytest.mark.parametrize("body, message", [
        ({"kind": "cross_above", "ticker": "AAPL"}, "threshold"),
        ({"kind": "cross_above", "ticker": "AAPL", "threshold": -5}, "threshold"),
        ({"kind": "cross_above", "ticker": "AAPL", "threshold": float("inf")}, "threshold"),
        ({"kind": "range_exit", "ticker": "AAPL", "threshold": 200, "threshold_high": 190}, "low below high"),
        ({"kind": "period_move", "ticker": "AAPL", "threshold": 5, "period_days": 1}, "period_days"),
        ({"kind": "day_move", "ticker": "AAPL", "threshold": 5, "direction": "sideways"}, "direction"),
        ({"kind": "new_filing", "ticker": "AAPL", "form_types": ["XYZ"]}, "Unsupported"),
        ({"kind": "volume_spike", "ticker": "AAPL"}, "kind"),
        ({"kind": "cross_above", "ticker": "###", "threshold": 1}, "ticker"),
    ])
    def test_invalid_definitions_are_refused_with_the_reason(self, body, message):
        with pytest.raises(AlertValidationError, match=message):
            validate_definition(body)

    def test_alert_crud_is_owner_scoped(self, fake):
        repo = AlertsRepository(fake)
        alert = repo.create(USER_A, validate_definition({"kind": "cross_above", "ticker": "aapl", "threshold": 200}), 190.0)
        assert alert["condition"] == "AAPL crosses above 200.00"
        assert repo.list(USER_B) == []
        assert repo.update(USER_B, alert["id"], status="paused") is None
        assert not repo.delete(USER_B, alert["id"])
        assert repo.update(USER_A, alert["id"], status="paused")["status"] == "paused"
        assert repo.update(USER_A, alert["id"], status="active")["status"] == "active"
        with pytest.raises(AlertValidationError):
            repo.update(USER_A, alert["id"], status="triggered")


# ── session and freshness ────────────────────────────────────────────────────

class TestAlertEdits:
    def test_an_edit_changes_the_condition_and_starts_it_from_scratch(self, fake):
        alerts = AlertsRepository(fake)
        a = alerts.create(USER_A, validate_definition({"kind": "cross_above", "ticker": "AAPL", "threshold": 200}), 195.0)
        edited = alerts.update(USER_A, a["id"], validate_definition({"kind": "cross_above", "ticker": "AAPL", "threshold": 210}))
        assert edited["threshold"] == 210 and edited["armed"] is True
        assert fake.store["price_alerts"][0]["baseline_value"] is None, "the old baseline belonged to another question"
        assert edited["last_result"] is None

    def test_an_edit_cannot_move_an_alert_to_another_security(self, fake):
        alerts = AlertsRepository(fake)
        a = alerts.create(USER_A, validate_definition({"kind": "cross_above", "ticker": "AAPL", "threshold": 200}), 195.0)
        with pytest.raises(AlertValidationError):
            alerts.update(USER_A, a["id"], validate_definition({"kind": "cross_above", "ticker": "MSFT", "threshold": 200}))
        assert fake.store["price_alerts"][0]["ticker"] == "AAPL"

    def test_a_resumed_alert_does_not_report_a_move_made_while_it_was_paused(self, fake):
        alerts = AlertsRepository(fake)
        a = alerts.create(USER_A, validate_definition({"kind": "cross_above", "ticker": "AAPL", "threshold": 200}), 195.0)
        at = (OPEN - timedelta(minutes=1)).isoformat()
        alert_engine.run(fake, now=OPEN, quote_fn=lambda t: _quote(196.0, at))
        alerts.update(USER_A, a["id"], status="paused")
        crossed = (OPEN - timedelta(seconds=30)).isoformat()
        assert alert_engine.run(fake, now=OPEN, quote_fn=lambda t: _quote(205.0, crossed))["evaluated"] == 0
        alerts.update(USER_A, a["id"], status="active")
        first = alert_engine.run(fake, now=OPEN, quote_fn=lambda t: _quote(205.0, crossed))
        assert first["triggered"] == 0 and alerts.list(USER_A)[0]["last_result"] == "baseline set"
        later = (OPEN + timedelta(minutes=5)).isoformat()
        alert_engine.run(fake, now=OPEN + timedelta(minutes=5), quote_fn=lambda t: _quote(199.0, later))
        again = (OPEN + timedelta(minutes=9)).isoformat()
        assert alert_engine.run(fake, now=OPEN + timedelta(minutes=10), quote_fn=lambda t: _quote(201.0, again))["triggered"] == 1

    def test_another_user_cannot_edit_it(self, fake):
        alerts = AlertsRepository(fake)
        a = alerts.create(USER_A, validate_definition({"kind": "cross_above", "ticker": "AAPL", "threshold": 200}), 195.0)
        assert alerts.update(USER_B, a["id"], validate_definition({"kind": "cross_above", "ticker": "AAPL", "threshold": 1})) is None
        assert fake.store["price_alerts"][0]["threshold"] == 200


class TestFreshness:
    def test_market_hours(self):
        assert market_open(OPEN)
        assert not market_open(CLOSED)
        assert not market_open(datetime(2026, 10, 24, 15, 0, tzinfo=timezone.utc)), "Saturday"

    def test_quote_freshness_against_the_session(self):
        assert freshness((OPEN - timedelta(seconds=30)).isoformat(), OPEN) == "live"
        assert freshness((OPEN - timedelta(minutes=10)).isoformat(), OPEN) == "delayed"
        assert freshness((OPEN - timedelta(minutes=45)).isoformat(), OPEN) == "stale"
        assert freshness("2026-10-20T20:00:00+00:00", CLOSED) == "end_of_day"
        assert freshness("2026-10-16T20:00:00+00:00", CLOSED) == "stale", "last Friday's close on Tuesday night"
        assert freshness(None, OPEN) == "undated"
        assert freshness("2026-10-19", OPEN) == "stale", "a date-only quote mid-session is yesterday's"


# ── decisions ────────────────────────────────────────────────────────────────

def _alert(**kw):
    base = {"id": "a1", "ticker": "AAPL", "repeat": False, "armed": True, "threshold": 200.0,
            "last_observed_value": None, "last_observed_at": None, "baseline_value": None}
    return {**base, **kw}


def _obs(value, minute=0, fresh="delayed", **kw):
    at = (OPEN + timedelta(minutes=minute)).isoformat()
    return Observation(value=value, at=at, source="massive", freshness=fresh, session="2026-10-20", **kw)


class TestDecisions:
    def test_crossing_above_needs_a_prior_observation_below(self):
        assert decide(_alert(kind="cross_above"), _obs(205)).result == "baseline set"
        assert not decide(_alert(kind="cross_above", last_observed_value=205.0), _obs(206)).trigger
        d = decide(_alert(kind="cross_above", last_observed_value=199.0), _obs(200.0))
        assert d.trigger and d.patch["status"] == "triggered", "the boundary itself counts as crossing"

    def test_crossing_below_and_its_boundary(self):
        assert decide(_alert(kind="cross_below", last_observed_value=201.0), _obs(200.0)).trigger
        assert not decide(_alert(kind="cross_below", last_observed_value=199.0), _obs(198.0)).trigger

    def test_a_repeating_alert_disarms_and_rearms(self):
        fired = decide(_alert(kind="cross_above", repeat=True, last_observed_value=190.0), _obs(210))
        assert fired.trigger and fired.patch["armed"] is False and "status" not in fired.patch
        held = decide(_alert(kind="cross_above", repeat=True, armed=False, last_observed_value=210.0), _obs(215, 5))
        assert not held.trigger
        released = decide(_alert(kind="cross_above", repeat=True, armed=False, last_observed_value=215.0), _obs(195, 10))
        assert released.patch["armed"] is True and not released.trigger

    @pytest.mark.parametrize("obs, reason", [
        (Observation(unavailable="no quote (provider outage)"), "provider outage"),
        (_obs(210, fresh="stale"), "stale"),
        (_obs(210, fresh="undated"), "no timestamp"),
        (_obs(float("nan")), "no usable value"),
    ])
    def test_missing_or_stale_data_is_skipped_not_evaluated(self, obs, reason):
        d = decide(_alert(kind="cross_above", last_observed_value=190.0), obs)
        assert not d.evaluated and not d.trigger and reason in d.result

    def test_the_same_observation_is_not_evaluated_twice(self):
        at = (OPEN + timedelta(minutes=3)).isoformat()
        alert = _alert(kind="cross_above", last_observed_value=190.0, last_observed_at=at.replace("+00:00", "Z"))
        d = decide(alert, Observation(value=190.0, at=at, source="m", freshness="delayed"))
        assert d.result == "skipped: no new observation"

    def test_range_exit_needs_to_have_been_inside(self):
        alert = _alert(kind="range_exit", threshold=100.0, threshold_high=120.0)
        assert not decide({**alert, "last_observed_value": 130.0}, _obs(131)).trigger, "created outside"
        assert decide({**alert, "last_observed_value": 110.0}, _obs(121)).trigger
        assert decide({**alert, "last_observed_value": 110.0}, _obs(120)).result == "inside range", "edges are inside"

    def test_moves_respect_direction_and_fire_once_per_session(self):
        up = _alert(kind="day_move", threshold=3.0, direction="up")
        hit = decide(up, _obs(3.5, detail="x"))
        assert hit.trigger and hit.event_key.endswith(":2026-10-20")
        assert not decide(up, _obs(-4.0, detail="x")).trigger
        assert decide(_alert(kind="day_move", threshold=3.0, direction="either"), _obs(-4.0, detail="x")).trigger
        assert "reference" in decide(up, _obs(5.0)).result, "no reference close, no evaluation"

    def test_a_new_filing_fires_once_per_accession(self):
        alert = _alert(kind="new_filing", baseline_text="0000320193-26-000001")
        same = Observation(text="0000320193-26-000001", at="2026-10-01", source="sec", freshness="end_of_day")
        assert not decide(alert, same).trigger
        new = Observation(text="0000320193-26-000077", at="2026-10-20", source="sec", freshness="end_of_day")
        d = decide(alert, new)
        assert d.trigger and d.event_key == "a1:filing:0000320193-26-000077"


# ── the evaluator, end to end on a controlled quote ──────────────────────────

class TestEvaluator:
    def test_an_observed_quote_triggers_once_and_lands_in_the_inbox(self, fake):
        alerts = AlertsRepository(fake)
        alert = alerts.create(USER_A, validate_definition({"kind": "cross_above", "ticker": "AAPL", "threshold": 200}), 195.0)
        quotes = {"AAPL": _quote(201.5, (OPEN - timedelta(minutes=5)).isoformat())}

        summary = alert_engine.run(fake, now=OPEN, quote_fn=lambda t: quotes[t])
        assert summary["evaluated"] == 1 and summary["triggered"] == 1 and summary["notifications"] == 1

        inbox = NotificationsRepository(fake).list(USER_A)
        assert inbox["unread"] == 1
        note = inbox["notifications"][0]
        assert note["title"] == "AAPL crosses above 200.00"
        assert note["event"]["observed_value"] == 201.5
        assert note["event"]["freshness"] == "delayed" and note["event"]["source"] == "massive"
        assert note["link"] == "/company/AAPL"
        # The observation's own time, in UTC to the minute, not a raw ISO string.
        assert note["body"] == "Observed 201.50 — delayed quote from massive, 2026-10-20 14:25 UTC."
        assert NotificationsRepository(fake).list(USER_B)["notifications"] == []

        stored = alerts.list(USER_A)[0]
        assert stored["status"] == "triggered" and stored["last_result"] == "triggered"

        # A retried run sees nothing active, and re-recording the same trigger is refused.
        again = alert_engine.run(fake, now=OPEN, quote_fn=lambda t: quotes[t])
        assert again["triggered"] == 0
        event = fake.store["alert_events"][0]
        assert alerts.record_trigger({k: event[k] for k in ("event_key", "clerk_user_id", "ticker", "kind", "condition_text")}) is None
        assert len(fake.store["notifications"]) == 1

    def test_a_skipped_alert_is_not_reported_as_evaluated(self, fake):
        alerts = AlertsRepository(fake)
        alerts.create(USER_A, validate_definition({"kind": "cross_above", "ticker": "AAPL", "threshold": 200}), 195.0)
        summary = alert_engine.run(fake, now=OPEN, quote_fn=lambda t: _quote(None, None, outage=True))
        assert summary["evaluated"] == 0 and summary["skipped"] == {"skipped: no quote (provider outage)": 1}
        stored = alerts.list(USER_A)[0]
        assert stored["last_evaluated_at"] is None and stored["last_result"].startswith("skipped")

    def test_a_day_move_uses_the_previous_close(self, fake):
        alerts = AlertsRepository(fake)
        alerts.create(USER_A, validate_definition({"kind": "day_move", "ticker": "AAPL", "threshold": 2, "direction": "down"}))
        quote = _quote(95.0, (OPEN - timedelta(minutes=1)).isoformat(), prev=100.0)
        summary = alert_engine.run(fake, now=OPEN, quote_fn=lambda t: quote, series_fn=lambda t: None)
        assert summary["triggered"] == 1
        assert "-5.00%" in fake.store["notifications"][0]["body"]

    def test_one_failing_alert_does_not_stop_the_pass(self, fake):
        alerts = AlertsRepository(fake)
        alerts.create(USER_A, validate_definition({"kind": "cross_above", "ticker": "AAPL", "threshold": 200}), 195.0)
        alerts.create(USER_B, validate_definition({"kind": "cross_above", "ticker": "MSFT", "threshold": 400}), 390.0)

        def quotes(t):
            if t == "AAPL":
                raise RuntimeError("vendor exploded")
            return _quote(401.0, (OPEN - timedelta(minutes=2)).isoformat())

        summary = alert_engine.run(fake, now=OPEN, quote_fn=quotes)
        assert summary["triggered"] == 1 and summary["skipped"]


# ── API ──────────────────────────────────────────────────────────────────────

class TestAlertAndInboxApi:
    def test_create_validates_the_symbol_against_real_data(self, client, monkeypatch):
        from src import providers

        monkeypatch.setattr(providers.market_data, "get_price", lambda s: _quote(None, None, outage=False))
        r = client.post("/api/alerts", json={"kind": "cross_above", "ticker": "ZZZZ", "threshold": 10})
        assert r.status_code == 422 and "recognizes" in r.json()["detail"]
        monkeypatch.setattr(providers.market_data, "get_price", lambda s: _quote(None, None, outage=True))
        assert client.post("/api/alerts", json={"kind": "cross_above", "ticker": "AAPL", "threshold": 10}).status_code == 503
        monkeypatch.setattr(providers.market_data, "get_price", lambda s: _quote(190.0, OPEN.isoformat()))
        created = client.post("/api/alerts", json={"kind": "cross_above", "ticker": "aapl", "threshold": 200})
        assert created.status_code == 201 and created.json()["ticker"] == "AAPL"
        assert client.get("/api/alerts").json()["alerts"][0]["condition"] == "AAPL crosses above 200.00"
        assert client.post("/api/alerts", json={"kind": "cross_above", "ticker": "AAPL"}).status_code == 422

    def test_inbox_read_state(self, client, fake):
        AlertsRepository(fake).create(USER_A, validate_definition({"kind": "cross_above", "ticker": "AAPL", "threshold": 200}), 195.0)
        alert_engine.run(fake, now=OPEN, quote_fn=lambda t: _quote(205.0, (OPEN - timedelta(minutes=1)).isoformat()))
        inbox = client.get("/api/notifications").json()
        assert inbox["unread"] == 1
        nid = inbox["notifications"][0]["id"]
        assert client.post(f"/api/notifications/{nid}/read").status_code == 200
        assert client.get("/api/notifications").json()["unread"] == 0
        assert client.post("/api/notifications/someone-elses/read").status_code == 404


class TestSchedulerEndpoint:
    def test_without_a_configured_secret_it_does_not_run(self, monkeypatch):
        monkeypatch.delenv("ALERTS_SCHEDULER_TOKEN", raising=False)
        r = TestClient(api_module.app).post("/api/internal/alerts/evaluate")
        assert r.status_code == 503

    def test_a_wrong_token_is_refused_and_the_right_one_runs(self, monkeypatch, fake):
        monkeypatch.setenv("ALERTS_SCHEDULER_TOKEN", "s" * 40)
        database.set_client_for_testing(fake)
        calls = []
        monkeypatch.setattr(alert_engine, "run", lambda c: calls.append(c) or {"status": "ok"})
        try:
            app = TestClient(api_module.app)
            assert app.post("/api/internal/alerts/evaluate", headers={"X-Scheduler-Token": "nope"}).status_code == 403
            assert app.post("/api/internal/alerts/evaluate").status_code == 403
            ok = app.post("/api/internal/alerts/evaluate", headers={"X-Scheduler-Token": "s" * 40})
            assert ok.status_code == 200 and calls == [fake]
        finally:
            database.set_client_for_testing(None)

    def test_overlapping_runs_do_not_both_run(self, fake):
        assert alert_engine._RUN_LOCK.acquire(blocking=False)
        try:
            assert alert_engine.run(fake) == {"status": "already_running"}
        finally:
            alert_engine._RUN_LOCK.release()
