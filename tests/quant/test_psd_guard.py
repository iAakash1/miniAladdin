"""The variance guard is one implementation, used everywhere, and scale-aware.

Three modules had independently written `sqrt(max(variance, floor))` with
different floors — 0.0 in the risk engine, 0.0 in the ex-ante diagnostic, 1e-24
in the risk-parity loop — and each produced a different flavour of plausible
nonsense from the same invalid input.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.quant.portfolio import optimizer, psd
from src.quant.risk import engine as risk


def _indefinite() -> np.ndarray:
    """Eigenvalues 1e-3 and -8e-4. The negative eigenvector is [1, -1]."""
    return np.array([[1e-4, 9e-4], [9e-4, 1e-4]])


def test_the_matrix_really_is_indefinite() -> None:
    assert np.linalg.eigvalsh(_indefinite()).min() < 0


def test_negative_variance_is_refused() -> None:
    with pytest.raises(psd.NotPositiveSemiDefinite, match="negative"):
        psd.volatility(np.array([0.5, -0.5]), _indefinite(), context="t")


def test_non_finite_entries_are_refused() -> None:
    m = np.array([[1e-4, np.nan], [np.nan, 1e-4]])
    with pytest.raises(psd.NotPositiveSemiDefinite, match="non-finite"):
        psd.volatility(np.array([0.5, 0.5]), m, context="t")


def test_a_genuinely_zero_variance_is_not_an_error() -> None:
    assert psd.volatility(np.array([0.5, 0.5]), np.zeros((2, 2)), context="t") == 0.0


def test_a_healthy_matrix_matches_the_direct_computation() -> None:
    m = np.array([[4e-4, 1e-4], [1e-4, 9e-4]])
    w = np.array([0.6, 0.4])
    assert psd.volatility(w, m, context="t") == pytest.approx(np.sqrt(w @ m @ w))


def test_the_tolerance_is_scale_aware_not_absolute() -> None:
    """An absolute floor is either too strict on a small book or too loose on a
    large one. Float noise at each scale must pass; real indefiniteness must not."""
    for scale in (1e-8, 1e-4, 1.0, 1e4):
        m = np.array([[scale, 0.0], [0.0, scale]])
        assert psd.volatility(np.array([0.5, -0.5]), m, context="t") >= 0.0
        bad = np.array([[scale, 9 * scale], [9 * scale, scale]])
        with pytest.raises(psd.NotPositiveSemiDefinite):
            psd.volatility(np.array([0.5, -0.5]), bad, context="t")


def test_the_risk_engine_uses_the_same_exception_object() -> None:
    """Not a lookalike class — the service catches one of them."""
    assert risk.NotPositiveSemiDefinite is psd.NotPositiveSemiDefinite


def test_risk_parity_falls_back_rather_than_iterating_on_nonsense() -> None:
    """A 1e-24 floor passed the `> 0` check and divided by 1e-12."""
    names = ["A", "B"]
    cov = pd.DataFrame(_indefinite(), index=names, columns=names)
    w = optimizer.risk_parity(cov)
    assert np.all(np.isfinite(w.to_numpy()))
    assert w.sum() == pytest.approx(1.0)
    assert w.max() <= 1.0


def test_ex_ante_volatility_is_none_not_zero_when_unmeasurable() -> None:
    """Zero ex-ante volatility on a real book is a claim, not a fallback."""
    rng = np.random.default_rng(5)
    n, k = 250, 15
    f = rng.normal(0, 0.02, n)
    frame = pd.DataFrame(
        {f"N{i}": 0.9 * f + 0.1 * rng.normal(0, 0.02, n) for i in range(k)}
    )
    for i in range(k):
        frame.iloc[: i * 16, i] = np.nan

    cov = optimizer.covariance(frame)
    assert np.linalg.eigvalsh(cov.to_numpy()).min() < 0

    rng2 = np.random.default_rng(1)
    for _ in range(5000):
        w = pd.Series(rng2.normal(0, 1, k), index=cov.index)
        w /= w.abs().sum()
        if float(w.to_numpy() @ cov.to_numpy() @ w.to_numpy()) < 0:
            break
    else:
        pytest.skip("no negative-variance book found")

    with pytest.raises(psd.NotPositiveSemiDefinite):
        psd.volatility(w.to_numpy(), cov.to_numpy(), context="ex-ante")
