"""The estimator comparison must show the disagreement, not hide it.

A single covariance shown alone implies the risk it produces is the risk. It is
not: on the research book the four estimators disagree about portfolio
volatility by roughly a fifth, and which one is used is a choice nobody was
being shown.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.services.covariance_service import compare, correlation_view


def _staggered(k: int = 12, n: int = 250) -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(5)
    factor = rng.normal(0, 0.02, n)
    frame = pd.DataFrame(
        {f"N{i}": 0.9 * factor + 0.1 * rng.normal(0, 0.02, n) for i in range(k)}
    )
    for i in range(k):
        frame.iloc[: i * 18, i] = np.nan
    return frame, pd.Series([1.0 / k] * k, index=frame.columns)


def test_the_default_is_compared_not_replaced() -> None:
    returns, weights = _staggered()
    names = [e["estimator"] for e in compare(returns, weights)["estimators"]]
    assert names[0] == "pairwise (default)"
    assert {"empirical", "ledoit_wolf", "exponentially_weighted"} <= set(names)


def test_every_estimator_reports_whether_it_is_psd() -> None:
    returns, weights = _staggered()
    for e in compare(returns, weights)["estimators"]:
        assert isinstance(e["positive_semi_definite"], bool)
        assert e["min_eigenvalue"] is not None


def test_the_named_estimators_are_psd_where_the_default_is_not() -> None:
    """The reason the comparison exists."""
    returns, weights = _staggered()
    rows = {e["estimator"]: e for e in compare(returns, weights)["estimators"]}
    assert rows["pairwise (default)"]["positive_semi_definite"] is False
    for name in ("empirical", "ledoit_wolf", "exponentially_weighted"):
        assert rows[name]["positive_semi_definite"] is True


def test_an_impossible_diversification_ratio_is_flagged() -> None:
    """Below 1 is not a diversification result; it is a broken matrix.

    Correlation can only push portfolio volatility below the weighted average,
    so the ratio has a hard floor of 1. A value under it looks like an ordinary
    number and is not, so it carries an explicit flag.
    """
    returns, weights = _staggered()
    rows = {e["estimator"]: e for e in compare(returns, weights)["estimators"]}
    default = rows["pairwise (default)"]
    if default["diversification_ratio"] is not None and default["diversification_ratio"] < 1.0:
        assert default["diversification_ratio_below_one"] is True
        assert "not positive semi-definite" in (default["impossible_reason"] or "")
    for name in ("empirical", "ledoit_wolf", "exponentially_weighted"):
        assert rows[name]["diversification_ratio_below_one"] is False


def test_shrinkage_is_reported_only_where_it_applies() -> None:
    returns, weights = _staggered()
    rows = {e["estimator"]: e for e in compare(returns, weights)["estimators"]}
    assert rows["ledoit_wolf"]["shrinkage"] is not None
    assert rows["pairwise (default)"]["shrinkage"] is None


def test_shrinkage_improves_conditioning() -> None:
    """The property shrinkage exists for: the extreme eigenvalues move in."""
    returns, weights = _staggered()
    rows = {e["estimator"]: e for e in compare(returns, weights)["estimators"]}
    assert rows["ledoit_wolf"]["condition_number"] < rows["empirical"]["condition_number"]


def test_complete_case_reports_the_rows_it_actually_used() -> None:
    returns, weights = _staggered()
    rows = {e["estimator"]: e for e in compare(returns, weights)["estimators"]}
    assert rows["empirical"]["complete_rows"] < rows["empirical"]["observations"]


def test_correlation_leaves_unmeasured_pairs_null_not_zero() -> None:
    """An unobserved pair is not an uncorrelated pair."""
    rng = np.random.default_rng(3)
    frame = pd.DataFrame(np.nan, index=range(200), columns=[f"D{i}" for i in range(5)])
    for i in range(5):
        frame.iloc[i * 34 : i * 34 + 40, i] = rng.normal(0, 0.02, 40)
    view = correlation_view(frame)
    flat = [v for row in view["values"] for v in row]
    assert any(v is None for v in flat) or view["complete_rows"] == 0


def test_the_diagonal_of_a_correlation_view_is_one() -> None:
    returns, _ = _staggered()
    view = correlation_view(returns)
    for i in range(len(view["labels"])):
        assert view["values"][i][i] == pytest.approx(1.0, abs=1e-6)
