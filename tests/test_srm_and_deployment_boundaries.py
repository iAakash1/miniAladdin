"""Boundary and deployment-configuration corrections.

**One multiplier, two verdicts at 1.30.** `calculate_multiplier` classified
CRITICAL on `> 1.3`, so exactly 1.30 fell through to ELEVATED. Both consumers
of that number test `>= 1.3`: `decision.SRM_HIGH` and
`RiskAwarePredictionAgent.CRITICAL_THRESHOLD`, which cuts two steps off a
verdict. And 1.30 is not a floating-point curiosity — it is what an inverted
yield curve alone produces, 1.0 + 0.3, the single most recession-associated
state this gate exists to detect. So the same reading was narrated ELEVATED
and acted on as CRITICAL.

**A boost that cannot happen.** The multiplier starts at 1.0 and only ever
takes additive penalties, so its real range is [1.0, 1.6] — the 0.5 floor in
the clamp is unreachable, and so is the legacy `BOOST_THRESHOLD = 0.9` path
that upgrades a verdict in a calm regime. These tests pin the real range so
the dead path stays documented rather than quietly acquiring a meaning later.

**Deployment detection that described the previous host.** `/api/health`
reported "production" from `RAILWAY_ENVIRONMENT` while the deploy identity had
already moved to `RENDER_GIT_COMMIT`. On Render the service reported itself as
development.

**Issuer validation that disappeared when unset.** `verify_token` passed
`issuer=os.getenv("CLERK_ISSUER") or None`, and PyJWT skips the issuer claim
entirely when that is None. Signature checking still happened, so this was
defence in depth rather than an open door — but in production it should fail
closed rather than silently drop a check.

**A default watchlist nobody checked the owner of.** `PATCH /api/preferences`
accepted any `default_watchlist` id and stored it. Reads are separately
scoped, so this leaked no data, but it let one user's preferences reference
another user's object — broken referential integrity, and exactly the kind of
unvalidated id that becomes an IDOR the moment some later code trusts it.
"""

import os

import pytest

from src.models import MacroIndicators, MacroStatus
from src.risk_analysis import OmniSignalRiskEngine


@pytest.fixture()
def engine():
    return OmniSignalRiskEngine(api_key="fixture-key-not-real")


def _indicators(spread=1.0, inflation=2.0, fed=3.0):
    return MacroIndicators(
        yield_spread=spread, inflation_rate=inflation, fed_funds_rate=fed
    )


# ── the 1.30 boundary ────────────────────────────────────────────────────────

def test_an_inverted_curve_alone_lands_exactly_on_the_boundary(engine):
    """The precondition for the whole finding: 1.0 + 0.3 is reachable."""
    assessment = engine.calculate_multiplier(_indicators(spread=-0.25))
    assert assessment.risk_multiplier == pytest.approx(1.3)
    assert assessment.yield_curve_inverted is True


def test_the_boundary_multiplier_is_critical_not_elevated(engine):
    """1.30 must classify the same way its consumers treat it."""
    from src.decision import SRM_HIGH
    from src.prediction_agent import RiskAwarePredictionAgent

    assessment = engine.calculate_multiplier(_indicators(spread=-0.25))
    multiplier = assessment.risk_multiplier

    # Both consumers act on 1.30 as the high/critical case.
    assert multiplier >= SRM_HIGH
    assert multiplier >= RiskAwarePredictionAgent.CRITICAL_THRESHOLD

    assert assessment.status is MacroStatus.CRITICAL, (
        f"multiplier {multiplier} is treated as critical by decision.py and the "
        f"prediction agent but reported as {assessment.status.value}"
    )


def test_just_below_the_boundary_is_still_elevated(engine):
    """The fix must not sweep the whole ELEVATED band into CRITICAL."""
    assessment = engine.calculate_multiplier(_indicators(inflation=5.0))
    assert assessment.risk_multiplier == pytest.approx(1.2)
    assert assessment.status is MacroStatus.ELEVATED


def test_a_calm_regime_is_still_stable(engine):
    assert engine.calculate_multiplier(_indicators()).status is MacroStatus.STABLE


# ── the unreachable boost ────────────────────────────────────────────────────

@pytest.mark.parametrize("spread", [-1.0, -0.01, 0.0, 0.5, 3.0])
@pytest.mark.parametrize("inflation", [-2.0, 0.0, 4.0, 9.0])
@pytest.mark.parametrize("fed", [None, 0.0, 5.0, 12.0])
def test_the_multiplier_never_leaves_its_real_range(engine, spread, inflation, fed):
    """Every combination of inputs lands in [1.0, 1.6]."""
    multiplier = engine.calculate_multiplier(
        MacroIndicators(yield_spread=spread, inflation_rate=inflation, fed_funds_rate=fed)
    ).risk_multiplier
    assert 1.0 <= multiplier <= 1.6


def test_the_legacy_low_risk_boost_is_unreachable_from_this_producer(engine):
    """Documented, not deleted.

    `BOOST_THRESHOLD` upgrades a verdict when the multiplier is at or below
    0.9. The only producer of that multiplier cannot emit such a value, so the
    branch is dead. It is pinned here rather than removed so that a future
    macro model which *can* go below 1.0 fails this test and has to decide
    deliberately whether reviving the boost is intended.
    """
    from src.prediction_agent import RiskAwarePredictionAgent

    worst_case_calm = engine.calculate_multiplier(
        MacroIndicators(yield_spread=99.0, inflation_rate=-99.0, fed_funds_rate=0.0)
    ).risk_multiplier
    assert worst_case_calm > RiskAwarePredictionAgent.BOOST_THRESHOLD


# ── deployment detection ─────────────────────────────────────────────────────

_HOST_VARS = ("APP_ENV", "RENDER", "RENDER_GIT_COMMIT", "RAILWAY_ENVIRONMENT", "ENV")


@pytest.fixture()
def clean_env(monkeypatch):
    for name in _HOST_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _environment():
    from fastapi.testclient import TestClient

    import api.index as api

    with TestClient(api.app) as client:
        return client.get("/api/health").json()["environment"]


def test_app_env_is_the_explicit_production_switch(clean_env):
    clean_env.setenv("APP_ENV", "production")
    assert _environment() == "production"


def test_the_current_host_is_recognised(clean_env):
    """Render, where this service actually runs."""
    clean_env.setenv("RENDER", "true")
    assert _environment() == "production"


def test_the_previous_host_is_still_recognised(clean_env):
    """Backwards compatible: an existing Railway deployment must not regress."""
    clean_env.setenv("RAILWAY_ENVIRONMENT", "production")
    assert _environment() == "production"


def test_a_local_checkout_is_development(clean_env):
    assert _environment() == "development"


def test_app_env_development_is_not_production(clean_env):
    clean_env.setenv("APP_ENV", "development")
    assert _environment() == "development"


# ── issuer validation ────────────────────────────────────────────────────────

_JWKS = "https://example.clerk.accounts.dev/.well-known/jwks.json"


def test_production_without_an_issuer_reports_itself_unconfigured(monkeypatch):
    """Fail closed.

    Asserted on `is_configured()` rather than on a token: a garbage token is
    rejected either way, so testing rejection would pass for the wrong reason
    and prove nothing. What must change is that the deployment stops claiming
    it can verify sessions, which is what turns the persistence endpoints into
    an honest 503.
    """
    from src.services import clerk_auth

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CLERK_JWKS_URL", _JWKS)
    monkeypatch.delenv("CLERK_ISSUER", raising=False)
    clerk_auth._reset_for_testing()

    assert clerk_auth.is_configured() is False
    assert clerk_auth.verify_token("any.token.value") is None


def test_production_with_an_issuer_is_configured(monkeypatch):
    """The guard must not disable a correctly configured deployment."""
    from src.services import clerk_auth

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CLERK_JWKS_URL", _JWKS)
    monkeypatch.setenv("CLERK_ISSUER", "https://example.clerk.accounts.dev")
    clerk_auth._reset_for_testing()

    assert clerk_auth.is_configured() is True


def test_the_guard_does_not_fire_without_a_jwks_url(monkeypatch):
    """An unconfigured deployment is already unconfigured; nothing changes."""
    from src.services import clerk_auth

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("CLERK_JWKS_URL", raising=False)
    monkeypatch.delenv("CLERK_ISSUER", raising=False)
    clerk_auth._reset_for_testing()

    assert clerk_auth.is_configured() is False


def test_development_still_tolerates_a_missing_issuer(monkeypatch):
    """Local ergonomics are preserved; only production fails closed."""
    from src.services import clerk_auth

    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("CLERK_ISSUER", raising=False)
    monkeypatch.setenv("CLERK_JWKS_URL", "https://example.clerk.accounts.dev/.well-known/jwks.json")
    clerk_auth._reset_for_testing()

    # Still rejects a garbage token, but by signature verification rather than
    # by refusing to run at all.
    assert clerk_auth.verify_token("not-a-real-jwt") is None
    assert clerk_auth.is_configured() is True
