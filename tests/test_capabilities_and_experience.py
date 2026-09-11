"""The capabilities endpoint, experience-mode persistence, and the admin wall.

Two things are being pinned here.

The first is that the admin boundary lives on the server. It is easy to build
a product where the operator console is protected by not drawing a link to
it; this asserts that an ordinary signed-in account constructing the request
by hand is refused, which is the only version of that protection that means
anything.

The second is that experience mode is inert with respect to authorization. A
user who switches to advanced gains no permission, and a user who switches to
beginner loses none. The mode changes how much of the same analysis is drawn
and nothing else.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.index as api_module
from src.services import authz, database
from src.services.clerk_auth import require_clerk_user
from src.services.database.repositories import PreferencesRepository

USER_A = "user_aaa"
OPERATOR = "user_ops"


class _Store:
    """Minimal preferences-only fake of the supabase fluent client."""

    def __init__(self):
        self.rows: list[dict] = []

    def table(self, name):
        self._table = name
        self._filters = []
        self._action = ("select", None)
        return self

    def select(self, *_a, **_k):
        self._action = ("select", None)
        return self

    def upsert(self, payload, on_conflict=""):
        self._action = ("upsert", payload)
        return self

    def eq(self, field, value):
        self._filters.append((field, value))
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        kind, payload = self._action
        if kind == "upsert":
            for row in self.rows:
                if row["clerk_user_id"] == payload["clerk_user_id"]:
                    row.update(payload)
                    return SimpleNamespace(data=[row])
            self.rows.append(dict(payload))
            return SimpleNamespace(data=[self.rows[-1]])
        matched = [
            r for r in self.rows
            if all(r.get(f) == v for f, v in self._filters)
        ]
        return SimpleNamespace(data=matched)


@pytest.fixture()
def store():
    s = _Store()
    database.set_client_for_testing(s)
    yield s
    database.set_client_for_testing(None)


@pytest.fixture()
def client_as():
    """A TestClient signed in as whichever user the test names."""

    def _make(user_id: str):
        api_module.app.dependency_overrides[require_clerk_user] = lambda: user_id
        return TestClient(api_module.app)

    yield _make
    api_module.app.dependency_overrides.pop(require_clerk_user, None)


@pytest.fixture(autouse=True)
def _no_bootstrap(monkeypatch):
    monkeypatch.delenv(authz.ADMIN_IDS_ENV, raising=False)


# ── the admin wall ───────────────────────────────────────────────────────────

def test_an_anonymous_caller_cannot_reach_diagnostics():
    with TestClient(api_module.app) as client:
        assert client.get("/api/admin/diagnostics").status_code == 401


def test_an_ordinary_user_is_refused_diagnostics(client_as, store):
    """Not hidden — refused. The request is well formed and still denied."""
    with client_as(USER_A) as client:
        response = client.get("/api/admin/diagnostics")
    assert response.status_code == 403
    assert "capability" in response.json()["detail"].lower()


def test_an_operator_reaches_diagnostics(client_as, monkeypatch):
    monkeypatch.setenv(authz.ADMIN_IDS_ENV, OPERATOR)
    with client_as(OPERATOR) as client:
        response = client.get("/api/admin/diagnostics")
    assert response.status_code == 200
    body = response.json()
    assert "providers" in body and "persistence" in body


def test_diagnostics_report_posture_not_material(client_as, monkeypatch):
    """Which capabilities are configured, never the values configuring them."""
    monkeypatch.setenv(authz.ADMIN_IDS_ENV, OPERATOR)
    monkeypatch.setenv("FINNHUB_API_KEY", "sk-should-never-appear-in-a-response")
    with client_as(OPERATOR) as client:
        blob = client.get("/api/admin/diagnostics").text
    assert "sk-should-never-appear-in-a-response" not in blob


# ── capabilities ─────────────────────────────────────────────────────────────

def test_capabilities_require_a_session():
    with TestClient(api_module.app) as client:
        assert client.get("/api/me/capabilities").status_code == 401


def test_capabilities_describe_an_ordinary_user(client_as, store):
    with client_as(USER_A) as client:
        body = client.get("/api/me/capabilities").json()

    assert body["role"] == "user"
    assert "analyze" in body["permissions"]
    assert "view_admin_diagnostics" not in body["permissions"]
    assert body["experience_mode"] == "advanced"
    assert body["experience_mode_chosen"] is False


def test_capabilities_distinguish_never_asked_from_answered_advanced(client_as, store):
    """Both produce mode "advanced"; only one should trigger onboarding."""
    with client_as(USER_A) as client:
        assert client.get("/api/me/capabilities").json()["experience_mode_chosen"] is False
        client.patch("/api/preferences", json={"experience_mode": "advanced"})
        after = client.get("/api/me/capabilities").json()

    assert after["experience_mode"] == "advanced"
    assert after["experience_mode_chosen"] is True


def test_capabilities_survive_an_unavailable_database(client_as, monkeypatch):
    """Being unable to read a preference is not a reason to refuse to render."""
    # Unset the credentials as well as the injected client: restoring normal
    # behaviour on a machine that *has* credentials would build a real client
    # and reach the network, which is not what this test is about.
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    database.set_client_for_testing(None)
    with client_as(USER_A) as client:
        body = client.get("/api/me/capabilities").json()
    assert body["role"] == "user"
    assert body["experience_mode"] == "advanced"


def test_capabilities_carry_no_credential(client_as, store):
    with client_as(USER_A) as client:
        blob = client.get("/api/me/capabilities").text.lower()
    for leaked in ("token", "jwt", "secret", "jwks", "admin_clerk_user_ids"):
        assert leaked not in blob


# ── experience mode is presentation, not permission ──────────────────────────

def test_experience_mode_round_trips(client_as, store):
    with client_as(USER_A) as client:
        client.patch("/api/preferences", json={"experience_mode": "beginner"})
        assert client.get("/api/me/capabilities").json()["experience_mode"] == "beginner"
        client.patch("/api/preferences", json={"experience_mode": "advanced"})
        assert client.get("/api/me/capabilities").json()["experience_mode"] == "advanced"


@pytest.mark.parametrize("bogus", ["expert", "BEGINNER", "pro", "admin", "", "null"])
def test_an_unsupported_experience_mode_is_rejected(client_as, store, bogus):
    with client_as(USER_A) as client:
        client.patch("/api/preferences", json={"experience_mode": "beginner"})
        client.patch("/api/preferences", json={"experience_mode": bogus})
        assert client.get("/api/me/capabilities").json()["experience_mode"] == "beginner"


def test_switching_to_advanced_grants_no_permission(client_as, store):
    """The dimension test. Presentation must not become authorization."""
    with client_as(USER_A) as client:
        client.patch("/api/preferences", json={"experience_mode": "advanced"})
        body = client.get("/api/me/capabilities").json()
        assert body["role"] == "user"
        assert "view_admin_diagnostics" not in body["permissions"]
        assert client.get("/api/admin/diagnostics").status_code == 403


def test_a_user_cannot_write_their_own_role(client_as, store):
    """There is no client path that sets a role. The field is not writable."""
    with client_as(USER_A) as client:
        client.patch("/api/preferences", json={"role": "admin", "experience_mode": "beginner"})
        body = client.get("/api/me/capabilities").json()
        assert body["role"] == "user"
        assert client.get("/api/admin/diagnostics").status_code == 403

    assert all("admin" not in str(row.get("role", "")) for row in store.rows)


def test_the_repository_refuses_a_role_field_outright(store):
    """Belt and braces beneath the route: the allowlist has no `role`."""
    repo = PreferencesRepository(store)
    row = repo.patch(USER_A, {"experience_mode": "beginner", "role": "admin"})
    assert row.get("role") is None
    assert row["experience_mode"] == "beginner"
