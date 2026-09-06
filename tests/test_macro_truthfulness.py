"""A macro outage must not become an economic reading.

Three substitutions lived on this path, and each one turned a provider
failure into a number the scoring engine treated as a measurement.

A missing FRED observation was replaced with `0.0` before the risk multiplier
was computed, so an unreturned term spread became "the curve spread is exactly
zero" — which sits precisely on the inversion boundary the gate exists to
detect — and an unreturned CPI print became "inflation is exactly zero".

Total provider failure returned fixed demo values: inflation 3.2%, Fed funds
5.25%, multiplier 1.15. Nothing downstream could tell them from measurements.

And `_macro_assessment` defaulted an absent status to STABLE, so "we never got
a reading" resolved to the most reassuring value in the enum.
"""

from unittest.mock import patch

import pytest

import api.index as api
from src.models import MacroStatus


class _Snap:
    def __init__(self, yield_spread=None, inflation_rate=None, fed_funds_rate=None):
        self.yield_spread = yield_spread
        self.inflation_rate = inflation_rate
        self.fed_funds_rate = fed_funds_rate


class _Result:
    def __init__(self, data=None, ok=True, error=None):
        self.data = data
        self.ok = ok
        self.error = error


@pytest.fixture(autouse=True)
def _no_cache():
    """The macro cache is process-wide; a stale entry would mask everything."""
    api._macro_cache.clear()
    yield
    api._macro_cache.clear()


def _with_macro(result):
    return patch.object(api.providers.macro, "get_macro", return_value=result)


# ── total failure ───────────────────────────────────────────────────────────

def test_a_provider_outage_produces_no_multiplier():
    with _with_macro(_Result(ok=False, error="FRED unreachable")):
        multiplier, stats = api._fetch_macro_safe()
    assert multiplier is None, f"an outage produced a risk multiplier of {multiplier}"
    assert stats["status"] == api.MACRO_UNAVAILABLE


def test_a_provider_outage_invents_no_economic_observations():
    with _with_macro(_Result(ok=False, error="FRED unreachable")):
        _, stats = api._fetch_macro_safe()
    for field in ("yield_spread", "inflation_rate", "fed_funds_rate",
                  "yield_curve_inverted", "recession_warning"):
        assert stats[field] is None, f"{field} was fabricated as {stats[field]!r}"


def test_the_old_demo_numbers_are_gone():
    """3.2% inflation, 5.25% Fed funds and a 1.15 multiplier, specifically."""
    with _with_macro(_Result(ok=False, error="down")):
        multiplier, stats = api._fetch_macro_safe()
    blob = str(stats)
    assert "3.2" not in blob and "5.25" not in blob, f"demo macro values survive: {blob}"
    assert multiplier != 1.15
    assert not hasattr(api, "DEMO_MACRO_MULTIPLIER"), "the demo multiplier constant is back"
    assert not hasattr(api, "_demo_macro_stats"), "the demo payload builder is back"


def test_an_exception_inside_the_provider_is_also_reported_as_unavailable():
    with patch.object(api.providers.macro, "get_macro", side_effect=RuntimeError("boom")):
        multiplier, stats = api._fetch_macro_safe()
    assert multiplier is None
    assert stats["status"] == api.MACRO_UNAVAILABLE
    assert "boom" in str(stats["error"])


# ── partial data ────────────────────────────────────────────────────────────

def test_a_missing_term_spread_is_not_replaced_with_zero():
    """Zero sits on the inversion boundary. It is the worst possible guess."""
    with _with_macro(_Result(_Snap(yield_spread=None, inflation_rate=3.1, fed_funds_rate=4.2))):
        multiplier, stats = api._fetch_macro_safe()
    assert multiplier is None, "a multiplier was computed from a substituted spread"
    assert stats["yield_spread"] is None


def test_a_missing_inflation_print_is_not_replaced_with_zero():
    with _with_macro(_Result(_Snap(yield_spread=0.4, inflation_rate=None, fed_funds_rate=4.2))):
        multiplier, stats = api._fetch_macro_safe()
    assert multiplier is None
    assert stats["inflation_rate"] is None


def test_partial_data_stays_partial_rather_than_being_discarded():
    """What did arrive is still reported. Absence of one is not absence of all."""
    with _with_macro(_Result(_Snap(yield_spread=0.41, inflation_rate=None, fed_funds_rate=3.63))):
        _, stats = api._fetch_macro_safe()
    assert stats["yield_spread"] == 0.41, "an observation that arrived was thrown away"
    assert stats["fed_funds_rate"] == "3.63%"
    assert stats["inflation_rate"] is None
    assert "CPI inflation" in str(stats["error"])


# ── a complete reading still works ──────────────────────────────────────────

def test_a_complete_reading_produces_a_real_multiplier():
    with _with_macro(_Result(_Snap(yield_spread=0.41, inflation_rate=3.52, fed_funds_rate=3.63))):
        multiplier, stats = api._fetch_macro_safe()
    assert isinstance(multiplier, float)
    assert stats["status"] in {s.value for s in MacroStatus}
    assert stats["inflation_rate"] == "3.52%"


def test_a_genuine_zero_spread_is_kept_as_a_measurement():
    """Zero is a reading when the provider actually returned it."""
    with _with_macro(_Result(_Snap(yield_spread=0.0, inflation_rate=2.0, fed_funds_rate=1.0))):
        multiplier, stats = api._fetch_macro_safe()
    assert multiplier is not None, "a real zero spread was treated as missing"
    assert stats["yield_spread"] == 0.0


# ── the assessment ──────────────────────────────────────────────────────────

def test_an_unavailable_status_becomes_a_data_error_not_stable():
    unavailable = api._macro_unavailable("down")
    assessment = api._macro_assessment(None, unavailable)
    assert assessment.status is MacroStatus.DATA_ERROR


def test_an_absent_status_does_not_default_to_stable():
    """The default was literally "STABLE"."""
    assessment = api._macro_assessment(None, {})
    assert assessment.status is MacroStatus.DATA_ERROR, (
        "a stats dict with no status resolved to a calm market"
    )


def test_an_unmeasured_regime_applies_no_dampening():
    """The identity, so the arithmetic stays well formed — never a guess."""
    assessment = api._macro_assessment(None, api._macro_unavailable("down"))
    assert assessment.risk_multiplier == 1.0
