"""The broker client, and the one thing it must never do.

A market-data provider pointed at the wrong host returns wrong numbers: bad,
and visible. A broker client pointed at the wrong host spends real money:
irreversible, and — same code path, same credential shape, same response
schema — invisible until afterwards. These tests exist for that asymmetry.
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock, patch

from src.broker.alpaca_paper import (
    PAPER_HOST, AlpacaPaper, BrokerMisconfigured, BrokerUnavailable, status,
)

LIVE_HOST = "https://api.alpaca.markets"
ALL_ENVS = (
    "APCA_API_KEY_ID", "ALPACA_API_KEY_ID",
    "APCA_API_SECRET_KEY", "ALPACA_API_SECRET_KEY",
    "APCA_API_BASE_URL", "ALPACA_API_BASE_URL",
)


@pytest.fixture(autouse=True)
def clean_env():
    saved = {k: os.environ.get(k) for k in ALL_ENVS}
    for k in ALL_ENVS:
        os.environ.pop(k, None)
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _configure():
    os.environ["APCA_API_KEY_ID"] = "PKTEST_not_real"
    os.environ["APCA_API_SECRET_KEY"] = "secret_not_real"


# ── the guarantee ────────────────────────────────────────────────────────────

def test_the_live_host_is_refused_not_silently_replaced():
    """Pointing this at live is a statement of intent. The safe answer is to
    stop — not to quietly use paper anyway and let someone believe live
    trading is configured and working."""
    _configure()
    os.environ["APCA_API_BASE_URL"] = LIVE_HOST
    with pytest.raises(BrokerMisconfigured):
        AlpacaPaper()
    assert status().configured is False
    assert "paper" in (status().reason or "").lower()


def test_any_non_paper_host_is_refused():
    _configure()
    for host in (LIVE_HOST, "https://example.com", "http://paper-api.alpaca.markets"):
        os.environ["APCA_API_BASE_URL"] = host
        with pytest.raises(BrokerMisconfigured):
            AlpacaPaper()


def test_the_paper_host_configured_explicitly_is_accepted():
    _configure()
    os.environ["APCA_API_BASE_URL"] = PAPER_HOST
    AlpacaPaper()  # does not raise


def test_every_request_goes_to_the_paper_host():
    _configure()
    session = MagicMock()
    session.request.return_value = MagicMock(status_code=200, content=b"{}", json=lambda: {})
    c = AlpacaPaper(session=session)

    c.account(); c.positions(); c.orders(); c.asset("AAPL")
    c.submit_order(symbol="AAPL", qty=1, side="buy")
    c.cancel_order("abc")

    assert session.request.call_count == 6
    for call in session.request.call_args_list:
        url = call.args[1]
        assert url.startswith(PAPER_HOST), url
        assert "api.alpaca.markets" not in url.replace("paper-api.alpaca.markets", "")


# ── configuration ────────────────────────────────────────────────────────────

def test_missing_credentials_report_unconfigured_rather_than_crashing():
    s = status()
    assert s.configured is False
    assert "not configured" in (s.reason or "")
    assert s.environment == "paper"


def test_status_never_carries_a_credential():
    """This crosses the API boundary to a browser."""
    _configure()
    s = status()
    blob = f"{s.configured}{s.reason}{s.environment}"
    assert "PKTEST_not_real" not in blob
    assert "secret_not_real" not in blob


def test_credentials_travel_in_headers_never_in_the_url():
    _configure()
    session = MagicMock()
    session.request.return_value = MagicMock(status_code=200, content=b"{}", json=lambda: {})
    c = AlpacaPaper(session=session)
    c.account()

    call = session.request.call_args
    assert "PKTEST_not_real" not in call.args[1]
    headers = call.kwargs["headers"]
    assert headers["APCA-API-KEY-ID"] == "PKTEST_not_real"
    assert headers["APCA-API-SECRET-KEY"] == "secret_not_real"


def test_a_broker_error_does_not_leak_the_key():
    _configure()
    session = MagicMock()
    session.request.return_value = MagicMock(
        status_code=403, content=b'{"message":"forbidden"}',
        json=lambda: {"message": "forbidden"}, text='{"message":"forbidden"}',
    )
    c = AlpacaPaper(session=session)
    with pytest.raises(BrokerUnavailable) as e:
        c.account()
    assert "PKTEST_not_real" not in str(e.value)
    assert "secret_not_real" not in str(e.value)


# ── honesty about state ──────────────────────────────────────────────────────

def test_the_order_response_is_the_brokers_own():
    """No fill is simulated and no status is inferred. If the broker says
    accepted, this says accepted — a market order that "probably" filled is
    still not filled until the broker says so."""
    _configure()
    session = MagicMock()
    reply = {"id": "order-1", "status": "accepted", "filled_qty": "0",
             "filled_avg_price": None, "symbol": "AAPL"}
    session.request.return_value = MagicMock(
        status_code=200, content=b"{}", json=lambda: reply)
    c = AlpacaPaper(session=session)

    out = c.submit_order(symbol="AAPL", qty=10, side="buy")
    assert out == reply
    assert out["status"] == "accepted"
    assert out["filled_avg_price"] is None


# ── order validation ─────────────────────────────────────────────────────────

def test_validation_reports_every_problem_not_the_first():
    """A ticket that reports one error at a time is a ticket someone submits
    four times."""
    from api.index import PaperOrderRequest, _validate_paper_order

    problems = _validate_paper_order(PaperOrderRequest(
        symbol="", qty=0, side="hodl", order_type="teleport", time_in_force="whenever",
    ))
    assert len(problems) >= 5
    joined = " ".join(problems).lower()
    for expected in ("symbol", "quantity", "side", "order type", "time in force"):
        assert expected in joined


def test_a_well_formed_order_has_no_problems():
    from api.index import PaperOrderRequest, _validate_paper_order
    assert _validate_paper_order(PaperOrderRequest(
        symbol="AAPL", qty=10, side="buy", order_type="market", time_in_force="day",
    )) == []


def test_a_limit_order_needs_a_price():
    from api.index import PaperOrderRequest, _validate_paper_order
    problems = _validate_paper_order(PaperOrderRequest(
        symbol="AAPL", qty=10, side="buy", order_type="limit",
    ))
    assert any("limit price" in p.lower() for p in problems)

    assert _validate_paper_order(PaperOrderRequest(
        symbol="AAPL", qty=10, side="buy", order_type="limit", limit_price=300.0,
    )) == []


def test_negative_and_zero_quantities_are_refused():
    from api.index import PaperOrderRequest, _validate_paper_order
    for q in (0, -1, -0.5):
        problems = _validate_paper_order(PaperOrderRequest(symbol="AAPL", qty=q, side="buy"))
        assert any("quantity" in p.lower() for p in problems), q


def test_an_unparseable_buying_power_is_unknown_not_zero():
    """A buying power this product could not parse is unknown. Substituting
    zero would silently refuse every order with a message about funds."""
    from api.index import _safe_float_api
    assert _safe_float_api(None) is None
    assert _safe_float_api("") is None
    assert _safe_float_api("not a number") is None
    assert _safe_float_api(float("nan")) is None
    assert _safe_float_api("104238.71") == 104238.71
