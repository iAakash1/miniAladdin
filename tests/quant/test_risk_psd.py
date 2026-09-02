"""An invalid covariance must not render as a portfolio with no risk.

`sqrt(max(variance, 0))` converts the single piece of evidence that a
covariance estimate is broken into a book whose every position contributes
zero risk. The contributions then sum to zero, which satisfies the identity
assertion exactly, so the table looks verified.

These tests build the matrix the way the shipped estimator does — pandas
pairwise covariance over names with staggered histories — rather than by
writing an indefinite matrix by hand, so they fail if the estimator changes in
a way that stops producing them.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

from src.quant.portfolio.optimizer import COVARIANCE_RIDGE, covariance
from src.quant.risk.engine import NotPositiveSemiDefinite, risk_contributions


def _staggered_correlated(n: int = 250, k: int = 15) -> pd.DataFrame:
    """Names on a common factor, each listing later than the last."""
    rng = np.random.default_rng(5)
    factor = rng.normal(0, 0.02, n)
    frame = pd.DataFrame(
        {f"N{i}": 0.9 * factor + 0.1 * rng.normal(0, 0.02, n) for i in range(k)}
    )
    for i in range(k):
        frame.iloc[: i * 16, i] = np.nan
    return frame


def _book_with_negative_variance(cov: pd.DataFrame) -> pd.Series:
    rng = np.random.default_rng(1)
    matrix = cov.to_numpy()
    for _ in range(5000):
        w = pd.Series(rng.normal(0, 1, len(cov)), index=cov.index)
        w /= w.abs().sum()
        if float(w.to_numpy() @ matrix @ w.to_numpy()) < 0:
            return w
    pytest.skip("no negative-variance book found")


def test_pairwise_estimation_really_does_produce_an_indefinite_matrix() -> None:
    """The premise. If this stops holding, the guard below is untested."""
    cov = covariance(_staggered_correlated())
    assert np.linalg.eigvalsh(cov.to_numpy()).min() < 0


def test_the_ridge_is_far_too_small_to_repair_it() -> None:
    cov = covariance(_staggered_correlated())
    worst = float(np.linalg.eigvalsh(cov.to_numpy()).min())
    assert abs(worst) > 1000 * COVARIANCE_RIDGE, (
        "the ridge is sized for numerical inversion, not for PSD repair"
    )


def test_negative_variance_is_refused_not_reported_as_zero_risk() -> None:
    cov = covariance(_staggered_correlated())
    w = _book_with_negative_variance(cov)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(NotPositiveSemiDefinite, match="negative"):
            risk_contributions(w, cov)


def test_a_non_finite_covariance_entry_is_refused() -> None:
    """Two names whose histories never overlap produce NaN, not a number."""
    rng = np.random.default_rng(3)
    frame = pd.DataFrame(np.nan, index=range(200), columns=[f"D{i}" for i in range(6)])
    for i in range(6):
        frame.iloc[i * 32 : i * 32 + 40, i] = rng.normal(0, 0.02, 40)
    cov = covariance(frame)
    assert cov.isna().to_numpy().sum() > 0
    with pytest.raises(NotPositiveSemiDefinite, match="non-finite"):
        risk_contributions(pd.Series([1 / 6] * 6, index=frame.columns), cov)


def test_a_genuinely_riskless_book_still_reports_zero() -> None:
    """Zero variance is a true answer here and must not be turned into an error."""
    names = list("ABC")
    cov = pd.DataFrame(np.zeros((3, 3)), index=names, columns=names)
    out = risk_contributions(pd.Series([0.5, 0.3, 0.2], index=names), cov)
    assert list(out["component"]) == [0.0, 0.0, 0.0]


def test_an_empty_book_still_reports_zero() -> None:
    names = list("ABC")
    rng = np.random.default_rng(0)
    frame = pd.DataFrame(rng.normal(0, 0.02, (300, 3)), columns=names)
    out = risk_contributions(pd.Series([0.0, 0.0, 0.0], index=names), covariance(frame))
    assert float(out["component"].sum()) == 0.0


def test_a_healthy_book_is_unchanged() -> None:
    """The guard must not move a number that was already right."""
    names = list("VWXYZ")
    rng = np.random.default_rng(9)
    frame = pd.DataFrame(rng.normal(0, 0.02, (400, 5)), columns=names)
    w = pd.Series([0.2] * 5, index=names)
    out = risk_contributions(w, covariance(frame))
    assert out["share"].sum() == pytest.approx(1.0)
    assert out["component"].sum() > 0


def test_zero_risk_and_invalid_risk_are_distinguishable() -> None:
    """The defect: both produced the same all-zero table."""
    names = list("ABC")
    riskless = risk_contributions(
        pd.Series([0.5, 0.3, 0.2], index=names),
        pd.DataFrame(np.zeros((3, 3)), index=names, columns=names),
    )
    assert float(riskless["component"].sum()) == 0.0

    cov = covariance(_staggered_correlated())
    w = _book_with_negative_variance(cov)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(NotPositiveSemiDefinite):
            risk_contributions(w, cov)
