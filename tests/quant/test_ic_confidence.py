"""
A confidence interval on the pooled IC, blocked for overlapping labels.

The surface reported a point estimate, which invites reading a mean of 0.029 as
though its precision were known. The block size is the part that has to be
right: labels span 21 sessions against a 5-session rebalance, so consecutive
observations share roughly four fifths of their outcome. An i.i.d. bootstrap on
dependent draws produces an interval far too narrow — understating uncertainty
in the direction that flatters the result.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.quant.validation.metrics import bootstrap_interval
from src.services import quant_series


def test_the_block_is_derived_from_the_experiment_not_hardcoded():
    """The service must not carry its own copy of the label horizon.

    It did, as `21 // 5`, and the floor was wrong — see
    tests/quant/test_label_geometry.py.
    """
    assert not hasattr(quant_series, "_LABEL_HORIZON_SESSIONS")
    assert not hasattr(quant_series, "_OVERLAP_BLOCK")

    served = quant_series.fold_series("EXP-006", "gradient_boosting")
    if served.get("status") != "ok":
        pytest.skip("EXP-006 predictions not present in this checkout")
    assert served["label_geometry"]["block_length"] == 5


def test_a_blocked_bootstrap_is_wider_than_an_iid_one_on_dependent_data():
    """The reason blocking is not optional.

    On an autocorrelated series the i.i.d. interval is too narrow. If this ever
    inverts, the blocking has stopped doing its job.
    """
    rng = np.random.default_rng(0)
    noise = rng.normal(0, 1, 600)
    # Strong AR(1): each observation mostly repeats the previous one, which is
    # what overlapping labels do.
    series = np.zeros(600)
    for i in range(1, 600):
        series[i] = 0.9 * series[i - 1] + 0.1 * noise[i]

    iid = bootstrap_interval(series, block=1, samples=800, seed=1)
    blocked = bootstrap_interval(series, block=20, samples=800, seed=1)

    assert (blocked["upper"] - blocked["lower"]) > (iid["upper"] - iid["lower"])


def test_the_interval_brackets_its_point_estimate():
    rng = np.random.default_rng(2)
    values = rng.normal(0.03, 0.1, 400)
    result = bootstrap_interval(values, block=4, samples=800, seed=0)
    assert result["lower"] <= result["point"] <= result["upper"]


def test_a_short_sample_refuses_rather_than_estimating():
    result = bootstrap_interval([0.1, 0.2, 0.3], block=4)
    assert result["point"] is None
    assert result["samples"] == 0


def test_the_bootstrap_is_deterministic():
    """Same seed, same interval. A research number that moves between reads is
    not a research number."""
    values = np.random.default_rng(3).normal(0.02, 0.08, 300)
    first = bootstrap_interval(values, block=4, samples=500, seed=7)
    second = bootstrap_interval(values, block=4, samples=500, seed=7)
    assert first == second


def test_the_served_interval_is_consistent_with_the_recorded_ic():
    """The interval must be about the same number the artifact records."""
    served = quant_series.fold_series("EXP-006", "gradient_boosting")
    if served.get("status") != "ok":
        pytest.skip("EXP-006 predictions not present in this checkout")

    pooled = served["pooled_ic"]
    assert pooled["point"] == pytest.approx(0.02895, abs=5e-4), (
        "the bootstrap point estimate must match EXP-006's recorded mean IC"
    )
    assert pooled["lower"] < pooled["point"] < pooled["upper"]
    assert pooled["observations"] > 100
    assert "moving-block" in pooled["method"]
    # The justification is derived from the label geometry, so it names the
    # actual horizon and cadence rather than restating a generic sentence.
    assert "21-session" in pooled["why_blocked"]
    assert "every 5 sessions" in pooled["why_blocked"]
