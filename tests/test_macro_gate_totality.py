"""An unmeasurable macro regime must not crash the research endpoint.

P0-02 stopped inventing macro data: when FRED cannot be read, the risk
multiplier is `None` rather than a fabricated 1.15. That was correct, and it
left one consumer behind. `apply_dampening` still compared its argument
against three float thresholds, so the moment the multiplier became honestly
absent the comparison raised

    TypeError: '>=' not supported between instances of 'NoneType' and 'float'

and `/api/research/{ticker}` — the product's primary endpoint — answered 500.
A deployment with no `FRED_API_KEY` at all hits this on *every* request, so
the failure is not an edge case; it is the default for an unconfigured
install.

The fix has to be the identity, not a neutral 1.0. Substituting 1.0 and then
running the threshold comparisons would land between BOOST_THRESHOLD (0.9)
and DAMPEN_THRESHOLD (1.2) and return the raw verdict anyway — the same
answer, reached by asserting a measurement that was never taken. These tests
pin the behaviour and the reason: no dampening is applied, nothing is
invented, and the absence stays visible to the reader.
"""

import math

import pytest

from src.models import SignalVerdict
from src.prediction_agent import RiskAwarePredictionAgent as Agent


@pytest.fixture(autouse=True)
def _no_threaded_prefetch(monkeypatch):
    """Stop the research handler's prefetch from fanning out to real vendors.

    `research_prefetch.warm` runs its warmers through `map_concurrent`, which
    abandons a worker when the future times out — Python cannot kill the
    thread, so the outbound call still happens, just later. Later can be
    inside a *different* test's `patch` window, which is how a broker test
    asserting "no request was made" ends up seeing seven calls to sec.gov.

    Nothing here depends on a warm cache: a cold cache is slower, never
    different.
    """
    from src.services import research_prefetch

    monkeypatch.setattr(research_prefetch, "warm", lambda ticker: {})

ORDER = [
    SignalVerdict.STRONG_SELL,
    SignalVerdict.SELL,
    SignalVerdict.HOLD,
    SignalVerdict.BUY,
    SignalVerdict.STRONG_BUY,
]


@pytest.mark.parametrize("raw", ORDER)
def test_absent_multiplier_applies_no_dampening(raw):
    """`None` is "we could not measure it", so the verdict passes through."""
    assert Agent.apply_dampening(raw, None) is raw


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("raw", [SignalVerdict.BUY, SignalVerdict.STRONG_SELL])
def test_non_finite_multiplier_applies_no_dampening(raw, bad):
    """A non-finite SRM is not a regime reading either.

    `inf >= CRITICAL_THRESHOLD` is True, so an infinite multiplier would
    otherwise cut two steps off the verdict on the strength of a number that
    cannot have come from a measurement. NaN is worse: every comparison is
    False, so it would silently take the boost branch's absence and look like
    a deliberate no-op.
    """
    assert not math.isfinite(bad)
    assert Agent.apply_dampening(raw, bad) is raw


def test_real_multipliers_still_dampen_and_boost():
    """The guard must not have disarmed the gate for measured regimes."""
    assert Agent.apply_dampening(SignalVerdict.STRONG_BUY, 1.4) is SignalVerdict.HOLD
    assert Agent.apply_dampening(SignalVerdict.STRONG_BUY, 1.25) is SignalVerdict.BUY
    assert Agent.apply_dampening(SignalVerdict.HOLD, 0.8) is SignalVerdict.BUY
    assert Agent.apply_dampening(SignalVerdict.BUY, 1.0) is SignalVerdict.BUY


def test_research_survives_an_unreadable_macro_provider():
    """The endpoint-level regression: macro down must not mean 500.

    Driven through the real route with the macro fetch reporting exactly what
    an unreadable FRED reports — `(None, {...UNAVAILABLE...})` — because that
    tuple is the contract `_fetch_macro_safe` was given by the P0-02 fix and
    the crash lived in the code that consumed it.
    """
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    import api.index as api

    unavailable = (
        None,
        {
            "status": "UNAVAILABLE",
            "error": "The macro provider could not be read: all vendors failed",
            "yield_spread": None,
            "inflation_rate": None,
            "fed_funds_rate": None,
            "yield_curve_inverted": None,
            "recession_warning": None,
        },
    )

    with patch.object(api, "_fetch_macro_safe", return_value=unavailable):
        with TestClient(api.app) as client:
            response = client.get("/api/research/AAPL")

    assert response.status_code == 200, response.text
    body = response.json()

    # The absence is reported, not papered over.
    assert body["macro"]["risk_multiplier"] is None
    assert body["macro"]["status"] == "UNAVAILABLE"

    # And none of the retired demo constants came back with it.
    blob = response.text
    assert "3.2" not in blob or '"inflation_rate":null' in blob.replace(" ", "")
    assert body["macro"]["inflation_rate"] is None
    assert body["macro"]["fed_funds_rate"] is None
