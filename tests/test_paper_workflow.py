"""The paper-order workflow: one submission per reference, the broker's word.

A fake broker records every call, so each test can assert not only what the
workflow answered but whether it sent a second order. No test reaches Alpaca;
the transport-level test drives the real client against a recording session
and checks that no request can leave for anything but the paper host.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import api.index as api
from src.broker.alpaca_paper import PAPER_HOST, AlpacaPaper, BrokerMisconfigured, BrokerUnavailable
from src.providers.schemas import PriceQuote
from src.services import clerk_auth, database, paper_access, paper_trading
from src.services.database.repositories import PaperOrdersRepository
from test_persistence import FakeSupabase

OPEN = datetime(2026, 10, 20, 14, 30, tzinfo=timezone.utc)
OWNER = "user_owner_1"
CID = "omni-0123456789abcdef0123456789abcdef"


class FakeBroker:
    """Answers like Alpaca's paper API, and remembers what it was asked."""

    def __init__(self, *, buying_power="10000", positions=(), submit_error=None, existing=None,
                 found_after=None, clock_open=True):
        self.calls: list[str] = []
        self.submitted: list[dict] = []
        self.buying_power = buying_power
        self._positions = list(positions)
        self.submit_error = submit_error
        self.by_cid = dict(existing or {})
        self.found_after = found_after   # an order that appears after a timeout
        self.clock_open = clock_open
        self.orders_by_id: dict[str, dict] = {}

    def asset(self, symbol):
        self.calls.append("asset")
        if symbol == "NOPE":
            raise BrokerUnavailable("the broker returned 404: asset not found", kind="not_found", status=404)
        return {"symbol": symbol, "tradable": True, "fractionable": symbol != "BRK.A", "shortable": True,
                "exchange": "NASDAQ", "name": f"{symbol} Inc"}

    def account(self):
        self.calls.append("account")
        return {"buying_power": self.buying_power, "equity": "10500", "last_equity": "10000", "cash": "2500",
                "long_market_value": "8000", "short_market_value": "0", "status": "ACTIVE",
                "trading_blocked": False, "account_blocked": False}

    def positions(self):
        self.calls.append("positions")
        return list(self._positions)

    def clock(self):
        self.calls.append("clock")
        return {"is_open": self.clock_open, "next_open": "2026-10-21T09:30:00-04:00"}

    def order_by_client_id(self, cid):
        self.calls.append("lookup")
        if cid in self.by_cid:
            return self.by_cid[cid]
        if self.found_after is not None and self.submitted:
            self.by_cid[cid] = self.found_after
            return self.found_after
        return None

    def submit_order(self, **kw):
        self.calls.append("submit")
        self.submitted.append(kw)
        if self.submit_error is not None:
            raise self.submit_error
        order = {"id": "4b1d2a00-0000-4000-8000-000000000001", "client_order_id": kw["client_order_id"],
                 "status": "accepted", "symbol": kw["symbol"], "filled_qty": "0", "filled_avg_price": None}
        self.by_cid[kw["client_order_id"]] = order
        self.orders_by_id[order["id"]] = order
        return order

    def order(self, order_id):
        self.calls.append("order")
        return self.orders_by_id.get(order_id, {"id": order_id, "status": "filled"})

    def cancel_order(self, order_id):
        self.calls.append("cancel")
        if self.orders_by_id.get(order_id, {}).get("status") == "filled" or order_id.endswith("filled"):
            raise BrokerUnavailable("the broker returned 422: order is not cancelable", kind="invalid", status=422)


def _order(**kw):
    base = {"symbol": "AAPL", "side": "buy", "order_type": "market", "time_in_force": "day",
            "qty": 2.0, "notional": None, "limit_price": None, "client_order_id": CID, "origin": "ticket"}
    return {**base, **kw}


def _quote(price=200.0, as_of=None):
    return SimpleNamespace(ok=True, source="massive",
                           data=PriceQuote(symbol="AAPL", price=price, as_of=as_of or OPEN.isoformat()))


def _no_sleep(_s):
    return None


# ── validation ───────────────────────────────────────────────────────────────

class TestValidation:
    @pytest.mark.parametrize("changes, fragment", [
        ({"qty": None}, "quantity or a dollar amount"),
        ({"notional": 100.0}, "quantity or a dollar amount"),
        ({"qty": None, "notional": 100.0, "order_type": "limit", "limit_price": 10.0}, "market orders good for the day"),
        ({"qty": None, "notional": 0.5}, "at least $1"),
        ({"qty": 1.5, "order_type": "limit", "limit_price": 10.0}, "Fractional"),
        ({"qty": 1.5, "time_in_force": "gtc"}, "Fractional"),
        ({"limit_price": 10.0}, "Only a limit order"),
        ({"order_type": "limit"}, "needs a limit price"),
        ({"order_type": "stop"}, "market or limit"),
        ({"client_order_id": "bad id!"}, "reference is malformed"),
        ({"qty": float("inf")}, "not a number"),
        ({"symbol": "aapl; drop"}, "valid ticker"),
    ])
    def test_rules(self, changes, fragment):
        assert any(fragment in p for p in paper_trading.validate(_order(**changes))), paper_trading.validate(_order(**changes))

    def test_a_good_notional_order(self):
        assert paper_trading.validate(_order(qty=None, notional=250.0)) == []


# ── preview ──────────────────────────────────────────────────────────────────

class TestPreview:
    def test_preview_prices_with_a_timestamped_quote_and_issues_a_reference(self):
        out = paper_trading.preview(FakeBroker(), _order(client_order_id=None), lambda s: _quote(), now=OPEN)
        assert out["ok"] and out["estimate"]["value"] == 400.0
        assert out["quote"] == {"price": 200.0, "as_of": OPEN.isoformat(), "source": "massive", "freshness": "live"}
        assert paper_trading.CLIENT_ORDER_ID.match(out["client_order_id"])

    def test_insufficient_buying_power_is_a_problem(self):
        out = paper_trading.preview(FakeBroker(buying_power="100"), _order(), lambda s: _quote(), now=OPEN)
        assert not out["ok"] and "exceeds paper buying power" in out["problems"][0]

    def test_stale_quote_and_closed_market_are_warnings(self):
        stale = _quote(as_of="2026-10-16T20:00:00+00:00")
        out = paper_trading.preview(FakeBroker(clock_open=False), _order(), lambda s: stale, now=OPEN)
        text = " ".join(out["warnings"])
        assert "stale" in text and "market is closed" in text

    def test_no_quote_means_no_estimate(self):
        out = paper_trading.preview(FakeBroker(), _order(), lambda s: SimpleNamespace(ok=False, data=None), now=OPEN)
        assert out["estimate"]["value"] is None and "No current price" in out["warnings"][0]

    def test_unknown_asset_and_unfractionable_dollar_order(self):
        assert "not an asset" in paper_trading.preview(FakeBroker(), _order(symbol="NOPE"), lambda s: _quote(), now=OPEN)["problems"][0]
        out = paper_trading.preview(FakeBroker(), _order(symbol="BRK.A", qty=None, notional=50.0), lambda s: _quote(), now=OPEN)
        assert any("fractional" in p for p in out["problems"])

    def test_selling_more_than_held_is_warned(self):
        broker = FakeBroker(positions=[{"symbol": "AAPL", "qty": "1"}])
        out = paper_trading.preview(broker, _order(side="sell"), lambda s: _quote(), now=OPEN)
        assert any("sells more than the 1 shares held" in w for w in out["warnings"])


# ── submit ───────────────────────────────────────────────────────────────────

class TestSubmit:
    def test_a_clean_submission_is_sent_once_and_recorded(self):
        fake = FakeSupabase()
        repo, broker = PaperOrdersRepository(fake), FakeBroker()
        status, body = paper_trading.submit(broker, _order(), OWNER, repo, sleep=_no_sleep)
        assert status == 201 and body["order"]["status"] == "accepted"
        assert broker.calls.count("submit") == 1
        row = repo.by_client_id(CID)
        assert row["last_status"] == "accepted" and row["broker_order_id"] == "4b1d2a00-0000-4000-8000-000000000001"
        assert row["clerk_user_id"] == OWNER

    def test_a_repeated_confirmation_returns_the_first_order(self):
        fake = FakeSupabase()
        repo, broker = PaperOrdersRepository(fake), FakeBroker()
        paper_trading.submit(broker, _order(), OWNER, repo, sleep=_no_sleep)
        status, body = paper_trading.submit(broker, _order(), OWNER, repo, sleep=_no_sleep)
        assert status == 200 and body["replayed"] is True
        assert broker.calls.count("submit") == 1, "the second confirmation must not send a second order"

    def test_an_order_already_at_the_broker_is_not_sent_again_even_without_a_local_record(self):
        broker = FakeBroker(existing={CID: {"id": "x" * 36, "status": "filled"}})
        status, body = paper_trading.submit(broker, _order(), OWNER, None, sleep=_no_sleep)
        assert status == 200 and body["order"]["status"] == "filled"
        assert "submit" not in broker.calls

    def test_a_timeout_is_resolved_by_lookup_never_by_resending(self):
        found = {"id": "4b1d2a00-0000-4000-8000-0000000000aa", "status": "new"}
        broker = FakeBroker(submit_error=BrokerUnavailable("timeout", kind="transport"), found_after=found)
        status, body = paper_trading.submit(broker, _order(), OWNER, None, sleep=_no_sleep)
        assert status == 201 and body["order"] == found and body["reconciled_after"] == "transport"
        assert broker.calls.count("submit") == 1

    def test_an_unresolvable_timeout_is_reported_unknown_and_left_for_reconciliation(self):
        fake = FakeSupabase()
        repo = PaperOrdersRepository(fake)
        broker = FakeBroker(submit_error=BrokerUnavailable("the broker returned 504", kind="upstream", status=504))
        status, body = paper_trading.submit(broker, _order(), OWNER, repo, sleep=_no_sleep)
        assert status == 202 and body["outcome"] == "unknown" and "not resent" in body["detail"]
        assert broker.calls.count("submit") == 1
        assert repo.by_client_id(CID)["last_status"] == "unknown"
        assert [r["client_order_id"] for r in repo.unresolved()] == [CID]

        # Later the broker shows it: reconciliation records the broker's word.
        broker.by_cid[CID] = {"id": "4b1d2a00-0000-4000-8000-0000000000bb", "status": "partially_filled"}
        out = paper_trading.reconcile_unresolved(broker, repo)
        assert out[0]["order"]["status"] == "partially_filled"
        assert repo.by_client_id(CID)["last_status"] == "partially_filled" and repo.unresolved() == []

    @pytest.mark.parametrize("error, expected_status, fragment", [
        (BrokerUnavailable("the broker returned 403: insufficient buying power", kind="refused", status=403), 422, "insufficient buying power"),
        (BrokerUnavailable("the broker returned 422: qty must be integer", kind="invalid", status=422), 422, "qty must be integer"),
        (BrokerUnavailable("the broker returned 401: unauthorized", kind="credentials", status=401), 502, "credentials were rejected"),
        (BrokerUnavailable("the broker returned 429", kind="rate_limited", status=429), 503, "rate limiting"),
    ])
    def test_definite_refusals_are_reported_and_not_retried(self, error, expected_status, fragment):
        broker = FakeBroker(submit_error=error)
        status, body = paper_trading.submit(broker, _order(), OWNER, None, sleep=_no_sleep)
        assert status == expected_status and fragment in body["detail"]
        assert broker.calls.count("submit") == 1

    def test_an_invalid_order_never_reaches_the_broker(self):
        broker = FakeBroker()
        status, _ = paper_trading.submit(broker, _order(qty=-1), OWNER, None, sleep=_no_sleep)
        assert status == 422 and broker.calls == []

    def test_a_reference_another_confirmation_reserved_is_not_sent_twice(self):
        fake = FakeSupabase()
        repo = PaperOrdersRepository(fake)
        assert repo.reserve(OWNER, CID, _order(), "ticket")
        broker = FakeBroker()
        status, body = paper_trading.submit(broker, _order(), OWNER, repo, sleep=_no_sleep)
        assert status == 202 and "submit" not in broker.calls


# ── cancel ───────────────────────────────────────────────────────────────────

class TestCancel:
    def test_cancel_reports_the_brokers_resulting_state(self):
        broker = FakeBroker()
        _, placed = paper_trading.submit(broker, _order(), OWNER, None, sleep=_no_sleep)
        status, body = paper_trading.cancel(broker, placed["order"]["id"])
        assert status == 200 and body["requested"] and body["order"]["id"] == placed["order"]["id"]

    def test_a_filled_order_cannot_be_shown_as_canceled(self):
        status, body = paper_trading.cancel(FakeBroker(), "4b1d2a00-0000-4000-8000-0000000filled")
        assert status == 409 and body["order"]["status"] == "filled"


# ── account views ────────────────────────────────────────────────────────────

class TestAccountViews:
    def test_connection_states(self):
        def missing():
            raise BrokerMisconfigured("Alpaca paper credentials are not configured.")
        assert paper_trading.connection(missing)["state"] == "not_configured"

        rejected = MagicMock()
        rejected.account.side_effect = BrokerUnavailable("the broker returned 401", kind="credentials", status=401)
        assert paper_trading.connection(lambda: rejected)["state"] == "credentials_rejected"

        blocked = MagicMock()
        blocked.account.return_value = {"status": "ACTIVE", "trading_blocked": True}
        assert paper_trading.connection(lambda: blocked)["state"] == "blocked"

        out = paper_trading.connection(lambda: FakeBroker())
        assert out["state"] == "connected" and out["account_status"] == "ACTIVE"

    def test_history_parameters_follow_the_brokers_rules(self):
        assert paper_trading.history_params("1M", "1D") == []
        assert paper_trading.history_params("1W", "15Min") == []
        assert paper_trading.history_params("3M", "5Min")
        assert paper_trading.history_params("5Y", "1D")

    def test_history_points_drop_windows_without_equity(self):
        points = paper_trading.history_points({
            "timestamp": [1, 2, 3], "equity": [100.0, None, 101.0], "profit_loss": [0, None, 1], "profit_loss_pct": [0, None, 0.01],
        })
        assert [p["t"] for p in points] == [1, 3]

    def test_analytics_keep_reported_and_derived_apart(self):
        positions = [
            {"symbol": "AAPL", "market_value": "6000", "unrealized_pl": "300", "unrealized_plpc": "0.05", "side": "long"},
            {"symbol": "TSLA", "market_value": "-2000", "unrealized_pl": "-100", "unrealized_plpc": "-0.05", "side": "short"},
        ]
        out = paper_trading.analytics(FakeBroker().account(), positions, [{"status": "filled"}, {"status": "canceled"}])
        assert out["reported"]["equity"] == 10500.0
        assert out["derived"]["day_change"] == 500.0 and round(out["derived"]["day_change_pct"], 6) == 5.0
        assert out["derived"]["unrealized_pl_total"] == 200.0
        assert [round(w["weight"], 2) for w in out["weights"]] == [0.75, 0.25], "a short counts as exposure"
        assert out["best"]["symbol"] == "AAPL" and out["worst"]["symbol"] == "TSLA"
        assert out["realized_pl"] is None and "Simulated" in out["label"]


# ── the paper host, at the transport ─────────────────────────────────────────

def test_the_whole_order_path_only_ever_reaches_the_paper_host(monkeypatch):
    monkeypatch.setenv("APCA_API_KEY_ID", "PKTEST000000000000")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "secret-test-value-000000")
    monkeypatch.delenv("APCA_API_BASE_URL", raising=False)
    urls: list[str] = []

    def reply(method, url, **kw):
        urls.append(url)
        if url.endswith("/v2/orders:by_client_order_id"):
            return MagicMock(status_code=404, content=b"{}", json=lambda: {"message": "order not found"})
        if url.endswith("/v2/positions"):
            return MagicMock(status_code=200, content=b"[]", json=lambda: [])
        return MagicMock(status_code=200, content=b"{}", json=lambda: {
            "id": "4b1d2a00-0000-4000-8000-000000000001", "status": "accepted", "buying_power": "1000",
            "tradable": True, "fractionable": True, "is_open": True,
        })

    session = MagicMock()
    session.request.side_effect = reply
    client = AlpacaPaper(session=session)
    paper_trading.preview(client, _order(), lambda s: _quote(), now=OPEN)
    paper_trading.submit(client, _order(), OWNER, None, sleep=_no_sleep)
    paper_trading.cancel(client, "4b1d2a00-0000-4000-8000-000000000001")
    assert urls and all(u.startswith(PAPER_HOST + "/") for u in urls)
    assert not any(u.startswith("https://api.alpaca.markets") for u in urls)


@pytest.mark.parametrize("base_url", [
    "https://api.alpaca.markets", "https://api.alpaca.markets/", "https://paper-api.alpaca.markets.attacker.example",
    "http://paper-api.alpaca.markets",
])
def test_a_configured_live_or_lookalike_host_stops_the_client(monkeypatch, base_url):
    monkeypatch.setenv("APCA_API_KEY_ID", "PKTEST000000000000")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "secret-test-value-000000")
    monkeypatch.setenv("APCA_API_BASE_URL", base_url)
    with pytest.raises(BrokerMisconfigured):
        AlpacaPaper(session=MagicMock())


# ── through the API ──────────────────────────────────────────────────────────

@pytest.fixture
def operator():
    with patch.object(clerk_auth, "is_configured", return_value=True), \
         patch.object(clerk_auth, "verify_token", return_value=OWNER), \
         patch.dict(os.environ, {paper_access.OWNERS_ENV: OWNER}, clear=False):
        yield TestClient(api.app)


class TestApi:
    def test_preview_then_confirm_then_resend(self, operator, monkeypatch):
        broker = FakeBroker()
        fake = FakeSupabase()
        database.set_client_for_testing(fake)
        monkeypatch.setattr(api, "_paper_client", lambda: broker)
        monkeypatch.setattr(api.providers.market_data, "get_price", lambda s: _quote())
        try:
            body = {"symbol": "aapl", "side": "buy", "qty": 1, "order_type": "market", "time_in_force": "day"}
            preview = operator.post("/api/paper/orders/preview", json=body).json()
            assert preview["ok"] and preview["environment"] == "paper"
            confirmed = {**body, "client_order_id": preview["client_order_id"]}
            first = operator.post("/api/paper/orders", json=confirmed)
            again = operator.post("/api/paper/orders", json=confirmed)
            assert first.status_code == 201 and again.status_code == 200 and again.json()["replayed"]
            assert broker.calls.count("submit") == 1
            reconciled = operator.get(f"/api/paper/orders/by-client/{preview['client_order_id']}").json()
            assert reconciled["found"] and reconciled["order"]["status"] == "accepted"
        finally:
            database.set_client_for_testing(None)

    def test_a_refusal_reaches_the_operator_with_the_brokers_reason(self, operator, monkeypatch):
        broker = FakeBroker(submit_error=BrokerUnavailable("the broker returned 403: insufficient buying power", kind="refused", status=403))
        monkeypatch.setattr(api, "_paper_client", lambda: broker)
        r = operator.post("/api/paper/orders", json={"symbol": "AAPL", "side": "buy", "qty": 1, "client_order_id": CID})
        assert r.status_code == 422 and "insufficient buying power" in r.json()["detail"]

    def test_history_and_connection_routes(self, operator, monkeypatch):
        broker = FakeBroker()
        broker.portfolio_history = lambda p, t: {"timestamp": [1, 2], "equity": [10000, 10100], "profit_loss": [0, 100],
                                                 "profit_loss_pct": [0, 0.01], "base_value": 10000, "timeframe": t}
        monkeypatch.setattr(api, "_paper_client", lambda: broker)
        hist = operator.get("/api/paper/history?period=1M&timeframe=1D").json()
        assert [p["equity"] for p in hist["points"]] == [10000, 10100]
        assert operator.get("/api/paper/history?period=6M&timeframe=5Min").status_code == 422

    def test_the_connection_test_never_returns_a_credential(self, operator, monkeypatch):
        monkeypatch.setenv("APCA_API_KEY_ID", "PKSECRET0000000001")
        monkeypatch.setenv("APCA_API_SECRET_KEY", "verysecretvalue000000001")
        monkeypatch.delenv("APCA_API_BASE_URL", raising=False)
        with patch("requests.Session.request") as req:
            req.return_value = MagicMock(status_code=401, content=b"{}", json=lambda: {"message": "unauthorized."})
            body = operator.get("/api/paper/connection")
        assert body.status_code == 200 and body.json()["state"] == "credentials_rejected"
        assert "PKSECRET" not in body.text and "verysecret" not in body.text
