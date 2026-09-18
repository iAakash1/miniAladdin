"""Who may operate the shared paper account.

Authentication alone does not make this safe. There is exactly one Alpaca
paper account behind the API, so requiring a Clerk session would stop
anonymous callers and still leave every signed-in user reading and mutating
the same positions, orders and balance — one person's cancel deleting
another's order, each seeing it as their own account.

These assert the three-state ladder: anonymous is refused, a signed-in
non-operator is refused, and only a named operator reaches the broker. And
that it fails closed — with no operator configured, nobody is authorised,
because an empty allowlist meaning "everyone" is the exact flaw this closes.
"""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import api.index as api
from src.services import clerk_auth, paper_access

ACCOUNT_ROUTES = [
    ("get", "/api/paper/account", None),
    ("get", "/api/paper/positions", None),
    ("get", "/api/paper/orders", None),
]
#: A well-formed order, so a refusal is about authorisation and not about the
#: body. `qty`, not `quantity` — the wrong field name 422s before the handler
#: runs and would have made the operator assertions pass vacuously.
VALID_ORDER = {"symbol": "AAPL", "qty": 1, "side": "buy", "order_type": "market"}

ORDER_ROUTES = [
    ("post", "/api/paper/orders/preview", VALID_ORDER),
    ("post", "/api/paper/orders", VALID_ORDER),
    ("delete", "/api/paper/orders/abc123", None),
]
ALL_ROUTES = ACCOUNT_ROUTES + ORDER_ROUTES

OWNER = "user_owner_1"
STRANGER = "user_stranger_2"


@pytest.fixture
def client():
    return TestClient(api.app)


def _call(client, method, path, body):
    fn = getattr(client, method)
    return fn(path, json=body) if body is not None else fn(path)


def _as(user_id):
    """Present a caller the server accepts as `user_id`."""
    return patch.object(clerk_auth, "verify_token", return_value=user_id)


def _clerk_on():
    return patch.object(clerk_auth, "is_configured", return_value=True)


def _owners(*ids):
    return patch.dict(os.environ, {paper_access.OWNERS_ENV: ",".join(ids)}, clear=False)


# ── anonymous ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("method,path,body", ALL_ROUTES)
def test_anonymous_callers_are_refused(client, method, path, body):
    with _clerk_on(), _owners(OWNER), _as(None):
        r = _call(client, method, path, body)
    assert r.status_code == 401, f"{method.upper()} {path} answered {r.status_code} to an anonymous caller"


@pytest.mark.parametrize("method,path,body", ALL_ROUTES)
def test_an_anonymous_caller_never_reaches_the_broker(client, method, path, body):
    """The refusal must happen before any broker construction."""
    with _clerk_on(), _owners(OWNER), _as(None), \
         patch.object(api, "_paper_client") as build:
        _call(client, method, path, body)
    assert build.call_count == 0, "the broker was constructed for an anonymous caller"


# ── signed in, not an operator ──────────────────────────────────────────────

@pytest.mark.parametrize("method,path,body", ALL_ROUTES)
def test_a_signed_in_stranger_is_refused(client, method, path, body):
    with _clerk_on(), _owners(OWNER), _as(STRANGER):
        r = _call(client, method, path, body)
    assert r.status_code == 403, f"{method.upper()} {path} answered {r.status_code} to a non-operator"


def test_two_different_users_are_not_both_treated_as_the_owner(client):
    """The defect in one assertion: one account, one operator."""
    with _clerk_on(), _owners(OWNER):
        with _as(OWNER), patch.object(api, "_paper_client"):
            allowed = client.get("/api/paper/account").status_code
        with _as(STRANGER):
            refused = client.get("/api/paper/account").status_code
    assert allowed != 401 and allowed != 403
    assert refused == 403, "a second user was treated as an owner of the same account"


# ── fails closed ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("method,path,body", ALL_ROUTES)
def test_with_no_operator_configured_nobody_is_authorised(client, method, path, body):
    """An empty allowlist must not mean 'everyone'."""
    with _clerk_on(), _owners(), _as(OWNER):
        r = _call(client, method, path, body)
    assert r.status_code == 403, (
        f"{method.upper()} {path} allowed a caller with no owner allowlist configured"
    )


def test_the_closed_state_says_why():
    state = paper_access.paper_access_state()
    with patch.dict(os.environ, {paper_access.OWNERS_ENV: ""}, clear=False):
        closed = paper_access.paper_access_state()
    assert closed["enabled"] is False
    assert paper_access.OWNERS_ENV in str(closed["reason"])
    assert isinstance(state, dict)


def test_owner_ids_are_never_returned_to_a_client(client):
    """They are account identifiers; a client has no use for someone else's."""
    with _clerk_on(), _owners(OWNER, STRANGER):
        body = client.get("/api/paper/status").json()
    blob = str(body)
    assert OWNER not in blob and STRANGER not in blob, "an owner id leaked to the client"
    assert body["access"]["enabled"] is True


# ── the operator gets through ───────────────────────────────────────────────

@pytest.mark.parametrize("method,path,body", ALL_ROUTES)
def test_the_named_operator_reaches_the_broker(client, method, path, body):
    with _clerk_on(), _owners(OWNER), _as(OWNER), \
         patch.object(api, "_paper_client") as build:
        r = _call(client, method, path, body)
    assert r.status_code not in (401, 403), (
        f"{method.upper()} {path} refused the configured operator with {r.status_code}"
    )
    assert build.call_count >= 1, "the operator's request never reached the broker"


def test_access_probe_uses_the_same_authentication_and_owner_gate(client):
    with _clerk_on(), _owners(OWNER):
        with _as(None):
            assert client.get("/api/paper/access").status_code == 401
        with _as(STRANGER):
            assert client.get("/api/paper/access").status_code == 403
        with _as(OWNER):
            response = client.get("/api/paper/access")

    assert response.status_code == 200
    assert response.json() == {
        "authenticated": True,
        "authorized": True,
        "environment": "paper",
    }


def test_access_probe_never_constructs_the_broker(client):
    with _clerk_on(), _owners(OWNER), _as(OWNER), patch.object(api, "_paper_client") as build:
        response = client.get("/api/paper/access")
    assert response.status_code == 200
    build.assert_not_called()


# ── the exact incident: a caller not on the current allowlist ────────────────
#
# The production failure this reproduces: authentication succeeded (the
# bearer token verified, `sub` resolved to a real signed-in user), but that
# `sub` was not the value configured in PAPER_TRADING_OWNERS — a stale id
# from a different Clerk identity or environment left over from an earlier
# configuration. The fix is not code; it is correcting the deployed
# environment variable. What belongs here is proof that the code responds
# correctly on both sides of that correction, so a future stale-allowlist
# incident is caught by a red test rather than by a signed-in user filing
# another report.

def test_a_caller_not_on_the_current_allowlist_is_refused(client):
    """The exact shape of the incident: a real, authenticated `sub` that
    simply is not the value currently configured."""
    with _clerk_on(), _owners("user_old_stale_id"), _as("user_current_real_id"):
        response = client.get("/api/paper/account")
    assert response.status_code == 403


def test_correcting_the_allowlist_to_the_current_caller_restores_access(client):
    """The same caller, after the deployed value is corrected to match them —
    proof that the fix is exactly the environment variable and nothing else
    needs to change in the request path."""
    with _clerk_on(), _owners("user_current_real_id"), \
         _as("user_current_real_id"), \
         patch.object(api, "_paper_client") as build:
        build.return_value.account.return_value = {"status": "ACTIVE"}
        response = client.get("/api/paper/account")
    assert response.status_code == 200


@pytest.mark.parametrize("raw, expected", [
    ("user_a,user_b", {"user_a", "user_b"}),
    ("user_a, user_b", {"user_a", "user_b"}),           # space after comma
    (" user_a , user_b ", {"user_a", "user_b"}),          # padding on both sides
    ("user_a,,user_b", {"user_a", "user_b"}),             # empty segment from a stray comma
    ("user_a,user_a", {"user_a"}),                        # duplicate collapses
    ("", set()),
    ("   ", set()),
])
def test_the_allowlist_parses_comma_separated_ids_with_whitespace_handled_safely(raw, expected):
    """Direct unit coverage of `configured_owners()` itself — the parsing the
    whole authorization chain depends on, tested independently of any HTTP
    request so a parsing regression fails here rather than surfacing as a
    confusing 403 for a correctly-configured owner whose id had a stray space."""
    with patch.dict(os.environ, {paper_access.OWNERS_ENV: raw}, clear=False):
        assert paper_access.configured_owners() == frozenset(expected)


# ── status stays public and carries no secret ───────────────────────────────

def test_status_is_readable_without_a_session(client):
    """The interface needs it to decide whether to offer the workspace."""
    r = client.get("/api/paper/status")
    assert r.status_code == 200
    body = r.json()
    assert "configured" in body and "access" in body and "tradable" in body


def test_status_carries_no_credential(client):
    body = str(client.get("/api/paper/status").json()).lower()
    for secret in ("apca", "secret", "api-key", "api_key"):
        assert secret not in body, f"paper status leaked {secret}"


def test_the_paper_host_is_still_the_only_venue(client):
    """The broker's own guarantee, unchanged by adding authorisation."""
    body = client.get("/api/paper/status").json()
    assert body["endpoint"] == "https://paper-api.alpaca.markets"
    assert "api.alpaca.markets" not in body["endpoint"].replace("paper-api.alpaca.markets", "")
