"""
Risk decomposition must say when it did not cover the whole book.

`weights.reindex(cov.index).fillna(0.0)` silently drops any held position the
covariance matrix does not cover — a new listing, a name with too little
history, a data gap. Portfolio volatility is then computed on a subset, the
component contributions still sum to *that subset's* volatility so the identity
assertion passes, and `share` still totals 1.0.

The output is plausible, internally consistent, and understates risk. Nothing
indicated a position had gone missing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.quant.risk import engine


@pytest.fixture()
def cov():
    rng = np.random.default_rng(0)
    panel = pd.DataFrame(rng.normal(0, 0.01, (400, 4)), columns=list("ABCD"))
    return engine.covariance_matrix(panel)


def test_a_fully_covered_book_reports_complete(cov):
    weights = pd.Series([0.25] * 4, index=list("ABCD"))
    frame = engine.risk_contributions(weights, cov)
    assert frame.attrs["weight_coverage"] == pytest.approx(1.0)
    assert frame.attrs["complete"] is True
    assert frame.attrs["caveat"] is None
    assert frame.attrs["uncovered_symbols"] == []


def test_an_uncovered_position_is_detected_and_named(cov):
    """The defect. E is held and has no covariance row."""
    weights = pd.Series([0.25] * 4, index=list("ABCE"))
    frame = engine.risk_contributions(weights, cov)

    assert frame.attrs["weight_coverage"] == pytest.approx(0.75)
    assert frame.attrs["complete"] is False
    assert frame.attrs["uncovered_symbols"] == ["E"]
    assert "understate" in frame.attrs["caveat"]


def test_the_understatement_is_real_and_measurable(cov):
    """Dropping a position genuinely lowers the reported volatility.

    This is why silence was dangerous: the number moves in the flattering
    direction and nothing else about the output changes.
    """
    covered = pd.Series([0.25] * 4, index=list("ABCD"))
    with_uncovered = pd.Series([0.25] * 4, index=list("ABCE"))

    full = engine.risk_contributions(covered, cov)["component"].sum()
    partial = engine.risk_contributions(with_uncovered, cov)["component"].sum()
    assert partial < full, "the subset's volatility must be lower — hence the caveat"


def test_contributions_still_sum_to_the_subset_volatility(cov):
    """The identity holds on the subset, which is exactly why it caught nothing."""
    weights = pd.Series([0.25] * 4, index=list("ABCE"))
    frame = engine.risk_contributions(weights, cov)
    portfolio_vol = frame["component"].sum()
    assert frame["share"].sum() == pytest.approx(1.0)
    assert portfolio_vol > 0


def test_a_wholly_uncovered_book_reports_zero_coverage(cov):
    weights = pd.Series([0.5, 0.5], index=["X", "Y"])
    frame = engine.risk_contributions(weights, cov)
    assert frame.attrs["weight_coverage"] == pytest.approx(0.0)
    assert frame.attrs["complete"] is False


def test_coverage_reaches_the_report(cov):
    rng = np.random.default_rng(1)
    index = pd.bdate_range("2024-01-01", periods=400)
    panel = pd.DataFrame(rng.normal(0, 0.01, (400, 4)), columns=list("ABCD"), index=index)
    returns = pd.Series(rng.normal(0.0003, 0.01, 400), index=index)
    weights = pd.Series([0.25] * 4, index=list("ABCE"))

    report = engine.analyse(returns, weights=weights, panel=panel)
    coverage = report.tables["risk_contributions_coverage"]
    assert coverage["complete"] is False
    assert coverage["uncovered_symbols"] == ["E"]
    assert coverage["minimum_required"] == engine.MIN_RISK_COVERAGE


def test_the_threshold_demands_near_total_coverage():
    """Risk understated by even a few percent is still understated."""
    assert engine.MIN_RISK_COVERAGE >= 0.99
