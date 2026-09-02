"""The diversification ratio, against its two closed-form limits.

Also records, as an executable test, why the effective-number-of-bets measure
is absent: the standard principal-axis construction is not a function of its
inputs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.quant.portfolio import psd
from src.quant.portfolio.diversification import diversification_ratio


def _identical(k: int = 10, n: int = 800) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    factor = rng.normal(0, 0.02, n)
    return pd.DataFrame({f"S{i}": factor for i in range(k)})


def _independent(k: int = 10, n: int = 4000) -> pd.DataFrame:
    rng = np.random.default_rng(2)
    return pd.DataFrame(rng.normal(0, 0.02, (n, k)), columns=[f"I{i}" for i in range(k)])


def _equal(frame: pd.DataFrame) -> pd.Series:
    k = frame.shape[1]
    return pd.Series([1.0 / k] * k, index=frame.columns)


def test_identical_names_have_a_ratio_of_one() -> None:
    """Perfect correlation: the book is exactly the sum of its parts."""
    frame = _identical()
    assert diversification_ratio(_equal(frame), frame.cov()) == pytest.approx(1.0, rel=1e-6)


def test_independent_equal_variance_names_approach_sqrt_k() -> None:
    """The closed form: DR = sqrt(k)."""
    frame = _independent()
    ratio = diversification_ratio(_equal(frame), frame.cov())
    assert ratio == pytest.approx(np.sqrt(frame.shape[1]), rel=0.05)


def test_the_ratio_is_never_below_one() -> None:
    """Correlation can only reduce risk below the weighted sum, never raise it."""
    for frame in (_identical(), _independent()):
        assert diversification_ratio(_equal(frame), frame.cov()) >= 1.0 - 1e-9


def test_correlation_reduces_the_ratio_monotonically() -> None:
    k, n = 6, 3000
    rng = np.random.default_rng(5)
    factor = rng.normal(0, 0.02, n)
    ratios = []
    for rho in (0.0, 0.3, 0.6, 0.9):
        frame = pd.DataFrame(
            {
                f"N{i}": np.sqrt(rho) * factor
                + np.sqrt(1 - rho) * rng.normal(0, 0.02, n)
                for i in range(k)
            }
        )
        ratios.append(diversification_ratio(_equal(frame), frame.cov()))
    assert ratios == sorted(ratios, reverse=True)


def test_a_long_short_book_is_measured_on_gross_not_net() -> None:
    """A book that nets to zero still takes risk."""
    frame = _independent(k=4)
    w = pd.Series([0.5, -0.5, 0.5, -0.5], index=frame.columns)
    assert w.sum() == pytest.approx(0.0)
    assert diversification_ratio(w, frame.cov()) > 1.0


def test_an_invalid_covariance_is_refused() -> None:
    names = ["A", "B"]
    bad = pd.DataFrame([[1e-4, 9e-4], [9e-4, 1e-4]], index=names, columns=names)
    with pytest.raises(psd.NotPositiveSemiDefinite):
        diversification_ratio(pd.Series([0.5, -0.5], index=names), bad)


def test_a_non_finite_covariance_is_refused() -> None:
    names = ["A", "B"]
    bad = pd.DataFrame([[1e-4, np.nan], [np.nan, 1e-4]], index=names, columns=names)
    with pytest.raises(psd.NotPositiveSemiDefinite):
        diversification_ratio(pd.Series([0.5, 0.5], index=names), bad)


# ── why the bet count is not shipped ─────────────────────────────────────────

def test_principal_axis_bet_count_is_not_a_function_of_its_inputs() -> None:
    """The reason effective_number_of_bets is absent from this module.

    For k equal-variance uncorrelated names the covariance is sigma^2 * I, and
    every orthonormal basis is an eigenbasis. The entropy-of-variance-shares
    construction therefore has no single answer, and sample noise picks one.
    """
    k = 10
    cov = np.eye(k) * 4e-4
    w = np.full(k, 1.0 / k)

    def bets(basis: np.ndarray, eigenvalues: np.ndarray) -> float:
        rotated = basis.T @ w
        p = (rotated**2) * eigenvalues
        p = p / p.sum()
        p = p[p > 0]
        return float(np.exp(-np.sum(p * np.log(p))))

    eigenvalues, natural = np.linalg.eigh(cov)
    arbitrary, _ = np.linalg.qr(np.random.default_rng(0).normal(size=(k, k)))

    assert bets(natural, eigenvalues) == pytest.approx(10.0, rel=1e-6)
    assert bets(arbitrary, eigenvalues) < 5.0, (
        "same covariance, different eigenbasis, different answer"
    )


def test_the_diversification_ratio_has_no_such_freedom() -> None:
    """It is built from the diagonal and the quadratic form, both determined."""
    k = 6
    rng = np.random.default_rng(4)
    frame = pd.DataFrame(rng.normal(0, 0.02, (2000, k)), columns=[f"N{i}" for i in range(k)])
    cov = frame.cov()
    w = pd.Series([1.0 / k] * k, index=frame.columns)

    first = diversification_ratio(w, cov)
    # Reordering the names is a relabelling, not a different book.
    order = list(reversed(frame.columns))
    second = diversification_ratio(w[order], cov.loc[order, order])
    assert first == pytest.approx(second)
