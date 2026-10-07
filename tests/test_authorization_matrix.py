"""Who may touch what: anonymous, the owner, and a different signed-in user.

The persistence tests drive the REST routes with `require_clerk_user` overridden
to a fixed user, which is right for testing what a route *does* and says nothing
about who may reach it: the real dependency never runs, so no test could see a
route that forgot it. These tests patch only the lowest seam — the token →
user-id lookup — so the genuine dependency, the router and the repositories run
exactly as in production, with two distinct users.

The contract, pinned here:

  no credential / bad credential     401   never reaches a handler
  authentication not configured      503   fails closed, never open
  another user's object              404   indistinguishable from "does not
                                           exist", so the API cannot be used to
                                           discover that someone else's id is
                                           real; and the object is left as it was
  a permission the caller lacks      403   (paper trading, admin, metrics reset)

Object ownership answers 404 rather than 403 on purpose. A 403 says "this exists
and is not yours", which is the oracle an attacker enumerating ids wants.

A real Clerk session is not available to a test; what is proved is the
authorization logic around the token check, with the check itself stubbed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api.index as api_module
import api.persistence as persistence
from src.services import clerk_auth, database

from test_persistence import FakeSupabase, _research_payload  # noqa: E402 — shared in-memory database

TOKENS = {"owner-token": "user_owner", "other-token": "user_other"}
OWNER = {"Authorization": "Bearer owner-token"}
OTHER = {"Authorization": "Bearer other-token"}
GARBAGE = {"Authorization": "Bearer not-a-real-token"}


@pytest.fixture
def world(monkeypatch):
    """A fake database, two known tokens, and the real auth dependency."""
    fake = FakeSupabase()
    database.set_client_for_testing(fake)
    monkeypatch.setattr(clerk_auth, "is_configured", lambda: True)
    monkeypatch.setattr(clerk_auth, "verify_token", lambda token: TOKENS.get(token))
    client = TestClient(api_module.app, raise_server_exceptions=False)
    try:
        yield client, fake
    finally:
        database.set_client_for_testing(None)


# ── every persistence route requires a verified user ─────────────────────────

def _persistence_routes() -> list[tuple[str, str]]:
    routes = []
    for route in persistence.router.routes:
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            path = route.path
            for name in ("watchlist_id", "position_id", "history_id", "saved_id", "session_id", "ticker", "note_id"):
                path = path.replace("{" + name + "}", "x")
            routes.append((method, path))
    return routes


def test_the_route_inventory_is_not_empty():
    # A discovery bug that found no routes would make every test below pass.
    routes = _persistence_routes()
    assert len(routes) >= 30, routes
    assert ("DELETE", "/api/watchlists/x") in routes
    assert ("GET", "/api/me/capabilities") in routes


@pytest.mark.parametrize("method,path", _persistence_routes())
def test_anonymous_callers_are_refused_by_every_persistence_route(world, method, path):
    client, _ = world
    response = client.request(method, path, json={} if method in ("POST", "PATCH", "PUT") else None)
    assert response.status_code == 401, f"{method} {path} answered {response.status_code} to an anonymous caller"


@pytest.mark.parametrize("method,path", _persistence_routes())
def test_an_unverifiable_token_is_refused_by_every_persistence_route(world, method, path):
    client, _ = world
    response = client.request(method, path, headers=GARBAGE, json={} if method in ("POST", "PATCH", "PUT") else None)
    assert response.status_code == 401, f"{method} {path} accepted a token that does not verify"


@pytest.mark.parametrize("method,path", _persistence_routes())
def test_with_authentication_unconfigured_every_route_fails_closed(world, monkeypatch, method, path):
    """No JWKS means no way to verify anyone — so nobody is let in, not everybody."""
    client, _ = world
    monkeypatch.setattr(clerk_auth, "is_configured", lambda: False)
    response = client.request(method, path, headers=OWNER, json={} if method in ("POST", "PATCH", "PUT") else None)
    assert response.status_code == 503, f"{method} {path} answered {response.status_code} with no auth configured"


# ── another signed-in user cannot read or change the owner's objects ────────

def _seed(client, fake):
    """The owner's objects, created through the API like a real user's."""
    wl = client.post("/api/watchlists", headers=OWNER, json={"name": "Mine", "tickers": ["NVDA"]})
    assert wl.status_code == 201, wl.text
    pos = client.post("/api/portfolio", headers=OWNER, json={"ticker": "MSFT", "shares": 3, "average_price": 400})
    assert pos.status_code == 201, pos.text
    from src.services.database.repositories import AnalysisRepository

    history_id = AnalysisRepository(fake).record("user_owner", _research_payload())
    saved = client.post("/api/saved-reports", headers=OWNER,
                        json={"analysis_history_id": history_id, "custom_title": "Keep", "notes": "private"})
    assert saved.status_code == 201, saved.text
    return {
        "watchlist": wl.json()["id"],
        "position": pos.json()["id"],
        "history": history_id,
        "saved": saved.json()["id"],
    }


def test_the_owner_can_reach_their_own_objects(world):
    client, fake = world
    ids = _seed(client, fake)
    assert client.get(f"/api/history/{ids['history']}", headers=OWNER).status_code == 200
    assert client.patch(f"/api/watchlists/{ids['watchlist']}", headers=OWNER, json={"name": "Renamed"}).status_code == 200
    assert client.patch(f"/api/portfolio/{ids['position']}", headers=OWNER, json={"shares": 4}).status_code == 200
    assert client.patch(f"/api/saved-reports/{ids['saved']}", headers=OWNER, json={"notes": "edited"}).status_code == 200


def test_another_user_gets_not_found_for_every_object_that_is_not_theirs(world):
    client, fake = world
    ids = _seed(client, fake)
    attempts = [
        ("PATCH", f"/api/watchlists/{ids['watchlist']}", {"name": "Stolen"}),
        ("DELETE", f"/api/watchlists/{ids['watchlist']}", None),
        ("POST", f"/api/watchlists/{ids['watchlist']}/tickers", {"ticker": "TSLA"}),
        ("DELETE", f"/api/watchlists/{ids['watchlist']}/tickers/NVDA", None),
        ("PATCH", f"/api/portfolio/{ids['position']}", {"shares": 1}),
        ("DELETE", f"/api/portfolio/{ids['position']}", None),
        ("GET", f"/api/history/{ids['history']}", None),
        ("DELETE", f"/api/history/{ids['history']}", None),
        ("PATCH", f"/api/saved-reports/{ids['saved']}", {"notes": "overwritten"}),
        ("DELETE", f"/api/saved-reports/{ids['saved']}", None),
        ("POST", "/api/saved-reports", {"analysis_history_id": ids["history"]}),
    ]
    for method, path, body in attempts:
        response = client.request(method, path, headers=OTHER, json=body)
        assert response.status_code == 404, f"{method} {path} answered {response.status_code} to a different user"
        assert response.status_code != 403, "a 403 would confirm the object exists"


def test_a_refused_attempt_leaves_the_owners_data_exactly_as_it_was(world):
    client, fake = world
    ids = _seed(client, fake)
    before = {
        "watchlists": client.get("/api/watchlists", headers=OWNER).json(),
        "portfolio": client.get("/api/portfolio", headers=OWNER).json(),
        "history": client.get(f"/api/history/{ids['history']}", headers=OWNER).json(),
        "saved": client.get("/api/saved-reports", headers=OWNER).json(),
    }
    for method, path, body in (
        ("PATCH", f"/api/watchlists/{ids['watchlist']}", {"name": "Stolen"}),
        ("DELETE", f"/api/watchlists/{ids['watchlist']}", None),
        ("PATCH", f"/api/portfolio/{ids['position']}", {"shares": 999}),
        ("DELETE", f"/api/portfolio/{ids['position']}", None),
        ("DELETE", f"/api/history/{ids['history']}", None),
        ("PATCH", f"/api/saved-reports/{ids['saved']}", {"notes": "overwritten"}),
        ("DELETE", f"/api/saved-reports/{ids['saved']}", None),
    ):
        client.request(method, path, headers=OTHER, json=body)
    after = {
        "watchlists": client.get("/api/watchlists", headers=OWNER).json(),
        "portfolio": client.get("/api/portfolio", headers=OWNER).json(),
        "history": client.get(f"/api/history/{ids['history']}", headers=OWNER).json(),
        "saved": client.get("/api/saved-reports", headers=OWNER).json(),
    }
    assert after == before


def test_lists_never_include_another_users_objects(world):
    client, fake = world
    _seed(client, fake)
    assert client.get("/api/watchlists", headers=OTHER).json()["watchlists"] == []
    assert client.get("/api/portfolio", headers=OTHER).json() in ({"positions": []}, [], {"positions": [], "count": 0}) \
        or not client.get("/api/portfolio", headers=OTHER).json().get("positions")
    assert client.get("/api/history", headers=OTHER).json()["total"] == 0
    assert client.get("/api/saved-reports", headers=OTHER).json()["saved"] == []


def test_comparing_the_owners_runs_as_another_user_reveals_nothing(world):
    client, fake = world
    from src.services.database.repositories import AnalysisRepository

    a = AnalysisRepository(fake).record("user_owner", _research_payload(momentum=0.1))
    b = AnalysisRepository(fake).record("user_owner", _research_payload(momentum=0.3))
    assert client.get(f"/api/history/compare?a={a}&b={b}", headers=OWNER).status_code == 200
    assert client.get(f"/api/history/compare?a={a}&b={b}", headers=OTHER).status_code == 404


def test_one_users_preference_cannot_point_at_anothers_watchlist(world):
    client, fake = world
    ids = _seed(client, fake)
    response = client.patch("/api/preferences", headers=OTHER, json={"default_watchlist": ids["watchlist"]})
    stored = client.get("/api/preferences", headers=OTHER).json()
    assert stored.get("default_watchlist") != ids["watchlist"], (
        f"a foreign watchlist id was stored (PATCH answered {response.status_code})"
    )


def test_each_users_preferences_are_their_own(world):
    client, _ = world
    assert client.patch("/api/preferences", headers=OWNER, json={"theme": "dark"}).status_code == 200
    assert client.patch("/api/preferences", headers=OTHER, json={"theme": "light"}).status_code == 200
    assert client.get("/api/preferences", headers=OWNER).json().get("theme") == "dark"
    assert client.get("/api/preferences", headers=OTHER).json().get("theme") == "light"


# ── permissions that are not about owning an object ──────────────────────────

ORDER = {"symbol": "AAPL", "qty": 1, "side": "buy", "type": "market", "time_in_force": "day"}


def test_a_signed_in_user_without_the_permission_gets_403_not_401_or_404(world, monkeypatch):
    client, _ = world
    for name in ("PAPER_TRADING_OWNERS", "METRICS_RESET_OWNERS", "ADMIN_CLERK_USER_IDS"):
        monkeypatch.delenv(name, raising=False)
    cases = [
        ("POST", "/api/paper/orders", ORDER),
        ("POST", "/api/paper/orders/preview", ORDER),
        ("GET", "/api/paper/account", None),
        ("POST", "/api/metrics/reset", None),
        ("GET", "/api/admin/diagnostics", None),
    ]
    for method, path, body in cases:
        anonymous = client.request(method, path, json=body)
        signed_in = client.request(method, path, headers=OTHER, json=body)
        assert anonymous.status_code == 401, f"{method} {path}: anonymous got {anonymous.status_code}"
        assert signed_in.status_code == 403, f"{method} {path}: a signed-in stranger got {signed_in.status_code}"


def test_the_configured_operator_passes_the_gate_and_a_second_user_still_does_not(world, monkeypatch):
    client, _ = world
    monkeypatch.setenv("METRICS_RESET_OWNERS", "user_owner")
    assert client.post("/api/metrics/reset", headers=OWNER).status_code == 200
    assert client.post("/api/metrics/reset", headers=OTHER).status_code == 403


def test_granting_one_user_a_permission_does_not_grant_it_to_another(world, monkeypatch):
    client, _ = world
    monkeypatch.setenv("PAPER_TRADING_OWNERS", "user_owner")
    owner = client.get("/api/paper/account", headers=OWNER).status_code
    other = client.get("/api/paper/account", headers=OTHER).status_code
    assert owner not in (401, 403), f"the configured owner was refused ({owner})"
    assert other == 403


def test_an_administrator_by_bootstrap_id_reaches_diagnostics_and_nobody_else_does(world, monkeypatch, offline_network):
    client, _ = world
    monkeypatch.setenv("ADMIN_CLERK_USER_IDS", "user_owner")
    assert client.get("/api/admin/diagnostics", headers=OWNER).status_code == 200
    assert client.get("/api/admin/diagnostics", headers=OTHER).status_code == 403
