"""Hermetic extension audit; no sockets, no real broker calls, no repository writes."""
import io
import os
from unittest.mock import patch

import pytest
import requests
from fastapi.testclient import TestClient

import api.index as api
from src.broker import alpaca_paper
from src.services import clerk_auth


PAPER_ENV = {
    "APCA_API_KEY_ID": "audit_dummy_key",
    "APCA_API_SECRET_KEY": "audit_dummy_secret",
    "ALPACA_API_KEY_ID": "",
    "ALPACA_API_SECRET_KEY": "",
    "APCA_API_BASE_URL": "",
    "ALPACA_API_BASE_URL": "",
    "PAPER_TRADING_OWNERS": "user_owner",
    "METRICS_RESET_OWNERS": "user_owner",
}
ROUTES = [
    ("GET", "/api/paper/account", None),
    ("GET", "/api/paper/positions", None),
    ("GET", "/api/paper/orders", None),
    ("POST", "/api/paper/orders/preview", {"symbol": "AAPL", "qty": 1, "side": "buy"}),
    ("POST", "/api/paper/orders", {"symbol": "AAPL", "qty": 1, "side": "buy"}),
    ("DELETE", "/api/paper/orders/audit_order", None),
]


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    import socket
    def denied(*args, **kwargs):
        raise AssertionError("Network access is forbidden in this audit")
    monkeypatch.setattr(socket.socket, "connect", denied)
    for name, value in PAPER_ENV.items():
        monkeypatch.setenv(name, value)


@pytest.mark.parametrize("method,path,body", ROUTES)
@pytest.mark.parametrize("identity,expected", [(None, 401), ("user_stranger", 403)])
def test_matrix_l_m_paper_identity(method, path, body, identity, expected):
    with patch.object(clerk_auth, "is_configured", return_value=True), \
         patch.object(clerk_auth, "verify_token", return_value=identity), \
         patch.object(api, "_paper_client") as broker, TestClient(api.app) as client:
        response = client.request(method, path, json=body)
    assert response.status_code == expected
    broker.assert_not_called()


@pytest.mark.parametrize("host", [
    "https://api.alpaca.markets", "https://paper-api.alpaca.markets.evil.invalid",
    "http://paper-api.alpaca.markets", "https://paper-api.alpaca.markets@evil.invalid",
])
def test_matrix_n_unsafe_host(host, monkeypatch):
    monkeypatch.setenv("APCA_API_BASE_URL", host)
    with patch.object(clerk_auth, "is_configured", return_value=True), \
         patch.object(clerk_auth, "verify_token", return_value="user_owner"), \
         patch.object(requests.Session, "request") as request, TestClient(api.app) as client:
        response = client.get("/api/paper/account")
    assert response.status_code == 503
    request.assert_not_called()


def test_matrix_o_metrics_get_cannot_reset():
    with patch.object(api.observability.registry, "reset") as reset, TestClient(api.app) as client:
        assert client.get("/api/metrics?reset=true").status_code == 200
        assert client.get("/api/metrics/reset").status_code == 405
    reset.assert_not_called()


def test_matrix_p_metrics_anonymous_post_cannot_reset():
    with patch.object(clerk_auth, "is_configured", return_value=True), \
         patch.object(clerk_auth, "verify_token", return_value=None), \
         patch.object(api.observability.registry, "reset") as reset, TestClient(api.app) as client:
        response = client.post("/api/metrics/reset")
    assert response.status_code == 401
    reset.assert_not_called()


def test_candidate_metrics_non_operator_cannot_erase_global_metrics():
    with patch.object(clerk_auth, "is_configured", return_value=True), \
         patch.object(clerk_auth, "verify_token", return_value="user_stranger"), \
         patch.object(api.observability.registry, "reset") as reset, TestClient(api.app) as client:
        response = client.post("/api/metrics/reset")
    assert (response.status_code, reset.call_count) == (403, 0)


class CannedTransport(requests.adapters.BaseAdapter):
    """A genuine requests Session transport that cannot open a connection."""
    def __init__(self, *, redirect=False, payload=b"[]"):
        self.seen = []
        self.redirect = redirect
        self.payload = payload

    def send(self, request, **kwargs):
        self.seen.append(request)
        response = requests.Response()
        response.request = request
        response.url = request.url
        response.raw = io.BytesIO(b"")
        if self.redirect and len(self.seen) == 1:
            response.status_code = 307
            response.headers["Location"] = "https://api.alpaca.markets/v2/orders"
            response._content = b""
        else:
            response.status_code = 200
            response._content = self.payload
        return response

    def close(self):
        pass


def test_candidate_broker_redirect_cannot_escape_paper_host():
    transport = CannedTransport(redirect=True, payload=b'{"id":"audit","status":"accepted"}')
    session = requests.Session()
    session.trust_env = False
    session.mount("https://", transport)
    broker = alpaca_paper.AlpacaPaper(session=session)
    with pytest.raises(alpaca_paper.BrokerUnavailable):
        broker.submit_order(symbol="AAPL", qty=1, side="buy")
    assert len(transport.seen) == 1
    assert all(request.url.startswith(alpaca_paper.PAPER_HOST + "/") for request in transport.seen)


@pytest.mark.parametrize("payload", [b"null", b"{}", b"", b'""'])
def test_candidate_empty_broker_payload_is_not_flat_account(payload):
    session = requests.Session()
    session.trust_env = False
    session.mount("https://", CannedTransport(payload=payload))
    broker = alpaca_paper.AlpacaPaper(session=session)
    with patch.object(clerk_auth, "is_configured", return_value=True), \
         patch.object(clerk_auth, "verify_token", return_value="user_owner"), \
         patch.object(api, "_paper_client", return_value=broker), TestClient(api.app) as client:
        response = client.get("/api/paper/positions")
    assert response.status_code == 502, response.json()


def test_legitimate_zero_broker_positions_remain_zero():
    session = requests.Session()
    session.trust_env = False
    session.mount("https://", CannedTransport(payload=b"[]"))
    broker = alpaca_paper.AlpacaPaper(session=session)
    assert broker.positions() == []
