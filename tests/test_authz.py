"""Authorization: what a caller may do, kept separate from who they are.

Three dimensions share this codebase and any two of them collapsing into one
is a security bug: role decides authorization, experience mode decides
presentation, entitlement decides what was paid for. An ADVANCED user is not
an administrator; a PRO subscriber is not an administrator; a BEGINNER is not
a free-tier account.

The property that matters most here is the direction of failure. Every
unknown — no database, no profile row, an unrecognised role string, a query
that raises — must resolve to USER. A module that fails towards ADMIN is one
outage away from handing an operator console to whoever is holding the door.
"""

from types import SimpleNamespace

import pytest

from src.services import authz, database
from src.services.authz import Permission, Role


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.delenv(authz.ADMIN_IDS_ENV, raising=False)
    database.set_client_for_testing(None)
    yield
    database.set_client_for_testing(None)


class _Profiles:
    """The narrowest fake that satisfies `ProfilesRepository.role_of`."""

    def __init__(self, rows=None, raises=False):
        self._rows = rows if rows is not None else []
        self._raises = raises

    def table(self, _name):
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        if self._raises:
            raise RuntimeError("database is down")
        return SimpleNamespace(data=self._rows)


# ── the permission matrix ────────────────────────────────────────────────────

def test_an_ordinary_user_can_do_the_ordinary_things():
    granted = authz.permissions_for(Role.USER)
    for permission in (
        Permission.ANALYZE,
        Permission.USE_BEGINNER,
        Permission.USE_ADVANCED,
        Permission.USE_EXPLORE,
        Permission.MANAGE_OWN_WATCHLISTS,
        Permission.MANAGE_OWN_PORTFOLIO,
        Permission.VIEW_OWN_HISTORY,
    ):
        assert permission in granted


@pytest.mark.parametrize("permission", [
    Permission.VIEW_ADMIN_DIAGNOSTICS,
    Permission.VIEW_AGENT_EVALUATION,
    Permission.MANAGE_SYSTEM,
])
def test_operator_capabilities_are_not_granted_to_users(permission):
    assert not authz.has_permission(Role.USER, permission)
    assert authz.has_permission(Role.ADMIN, permission)


def test_an_administrator_keeps_every_user_capability():
    """Admin is additive. An operator is not a user with *different*
    financial permissions — there are no different financial permissions."""
    assert authz.permissions_for(Role.USER) <= authz.permissions_for(Role.ADMIN)


def test_both_experience_modes_are_open_to_an_ordinary_user():
    """Experience mode is presentation. It is not a tier and not a role, so
    neither mode may be gated behind one."""
    assert authz.has_permission(Role.USER, Permission.USE_BEGINNER)
    assert authz.has_permission(Role.USER, Permission.USE_ADVANCED)


# ── resolution, and which way it fails ───────────────────────────────────────

def test_with_no_database_a_caller_is_an_ordinary_user():
    assert authz.resolve_role("user_abc") is Role.USER


def test_a_caller_with_no_profile_row_is_an_ordinary_user():
    database.set_client_for_testing(_Profiles(rows=[]))
    assert authz.resolve_role("user_abc") is Role.USER


def test_a_stored_admin_role_is_honoured():
    database.set_client_for_testing(_Profiles(rows=[{"role": "admin"}]))
    assert authz.resolve_role("user_abc") is Role.ADMIN


def test_a_database_fault_does_not_grant_access():
    """The important direction. An outage must not read as elevation."""
    database.set_client_for_testing(_Profiles(raises=True))
    assert authz.resolve_role("user_abc") is Role.USER


@pytest.mark.parametrize("stored", ["superuser", "ADMIN ", "root", "", None, "owner"])
def test_an_unrecognised_role_is_treated_as_the_floor(stored):
    """A value the CHECK constraint should have refused is corruption, and
    corruption must not read as elevation."""
    database.set_client_for_testing(_Profiles(rows=[{"role": stored}]))
    assert authz.resolve_role("user_abc") is Role.USER


def test_an_empty_user_id_is_never_an_administrator():
    database.set_client_for_testing(_Profiles(rows=[{"role": "admin"}]))
    assert authz.resolve_role("") is Role.USER


# ── the bootstrap path ───────────────────────────────────────────────────────

def test_the_bootstrap_variable_promotes_a_named_id(monkeypatch):
    """A fresh deployment has no administrator, so nobody could promote one."""
    monkeypatch.setenv(authz.ADMIN_IDS_ENV, "user_ops,user_second")
    assert authz.resolve_role("user_ops") is Role.ADMIN
    assert authz.resolve_role("user_second") is Role.ADMIN
    assert authz.resolve_role("user_other") is Role.USER


def test_bootstrap_works_while_the_database_is_unreachable(monkeypatch):
    """Which is exactly when an operator most needs to get in."""
    monkeypatch.setenv(authz.ADMIN_IDS_ENV, "user_ops")
    database.set_client_for_testing(_Profiles(raises=True))
    assert authz.resolve_role("user_ops") is Role.ADMIN


def test_an_empty_bootstrap_list_promotes_nobody(monkeypatch):
    """An unset or blank variable must never mean "everyone"."""
    monkeypatch.setenv(authz.ADMIN_IDS_ENV, "   ,  ,")
    assert authz.bootstrap_admin_ids() == frozenset()
    assert authz.resolve_role("user_ops") is Role.USER


# ── the self-description ─────────────────────────────────────────────────────

def test_capabilities_describe_the_caller_and_nothing_else(monkeypatch):
    monkeypatch.setenv(authz.ADMIN_IDS_ENV, "user_ops")
    payload = authz.capabilities_for("user_ops", "beginner")

    assert payload["role"] == "admin"
    assert payload["experience_mode"] == "beginner"
    assert Permission.MANAGE_SYSTEM.value in payload["permissions"]

    # Nothing about the deployment's other operators, and no credential.
    blob = str(payload)
    assert "user_ops" not in blob.replace("'user_ops'", "")
    for leaked in ("token", "jwt", "secret", "ADMIN_CLERK_USER_IDS"):
        assert leaked not in blob.lower()


def test_capabilities_for_an_ordinary_user_omit_operator_permissions():
    payload = authz.capabilities_for("user_plain", "advanced")
    assert payload["role"] == "user"
    assert Permission.VIEW_ADMIN_DIAGNOSTICS.value not in payload["permissions"]
