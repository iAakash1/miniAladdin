"""Named covariance estimators, tested on properties rather than outputs.

The shipped default stays pairwise and is deliberately untouched. These are
alternatives a caller chooses, and the point of each is a property the default
does not have.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.quant.portfolio import psd
from src.quant.portfolio.covariance import (
    ESTIMATORS,
    empirical,
    estimate,
    exponentially_weighted,
    ledoit_wolf,
)
from src.quant.portfolio.optimizer import covariance as pairwise_default


def _staggered(k: int = 15, n: int = 250) -> pd.DataFrame:
    """Names on a common factor, each listing later than the last."""
    rng = np.random.default_rng(5)
    factor = rng.normal(0, 0.02, n)
    frame = pd.DataFrame(
        {f"N{i}": 0.9 * factor + 0.1 * rng.normal(0, 0.02, n) for i in range(k)}
    )
    for i in range(k):
        frame.iloc[: i * 16, i] = np.nan
    return frame


def _clean_panel(k: int = 6, n: int = 1200, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame(rng.normal(0, 0.02, (n, k)), columns=[f"C{i}" for i in range(k)])


# ── the property that motivates the module ───────────────────────────────────

def test_the_default_is_not_psd_on_staggered_histories() -> None:
    """The premise. If this stops holding the tests below prove nothing."""
    assert np.linalg.eigvalsh(pairwise_default(_staggered()).to_numpy()).min() < 0


@pytest.mark.parametrize("name", sorted(ESTIMATORS))
def test_every_named_estimator_is_psd(name: str) -> None:
    assert estimate(_staggered(), estimator=name).is_psd


@pytest.mark.parametrize("name", sorted(ESTIMATORS))
def test_no_book_can_produce_a_negative_variance(name: str) -> None:
    """The failure the refusal guard exists for cannot arise from these."""
    result = estimate(_staggered(), estimator=name)
    matrix = result.matrix.to_numpy()
    rng = np.random.default_rng(1)
    for _ in range(3000):
        w = rng.normal(0, 1, matrix.shape[0])
        w /= np.abs(w).sum()
        assert psd.quadratic_form(w, matrix, context=name) >= 0.0


# ── complete-case honesty ────────────────────────────────────────────────────

def test_complete_case_reports_the_rows_it_actually_used() -> None:
    result = empirical(_staggered())
    assert result.complete_rows < result.observations
    assert "dropped for incompleteness" in (result.note or "")


def test_a_complete_panel_drops_nothing_and_says_nothing() -> None:
    result = empirical(_clean_panel())
    assert result.complete_rows == result.observations
    assert result.note is None


# ── Ledoit-Wolf ──────────────────────────────────────────────────────────────

def test_shrinkage_is_a_valid_intensity() -> None:
    result = ledoit_wolf(_staggered())
    assert 0.0 <= result.shrinkage <= 1.0


def test_shrinkage_is_heavier_when_observations_are_scarce() -> None:
    """T barely above N is where the sample estimate is worst."""
    scarce = ledoit_wolf(_clean_panel(k=8, n=12)).shrinkage
    plentiful = ledoit_wolf(_clean_panel(k=8, n=4000)).shrinkage
    assert scarce > plentiful


def test_shrinkage_preserves_the_diagonal_variances() -> None:
    """The target keeps each name's own variance; only correlations move."""
    panel = _clean_panel(k=5, n=900)
    result = ledoit_wolf(panel)
    for name in panel.columns:
        assert result.matrix.loc[name, name] == pytest.approx(
            float(panel[name].var(ddof=1)), rel=0.02
        )


def test_shrinkage_pulls_correlations_toward_their_average() -> None:
    rng = np.random.default_rng(8)
    n = 40
    factor = rng.normal(0, 0.02, n)
    panel = pd.DataFrame(
        {
            "A": factor + rng.normal(0, 0.001, n),      # near 1 with B
            "B": factor + rng.normal(0, 0.001, n),
            "C": rng.normal(0, 0.02, n),                # near 0 with the others
            "D": rng.normal(0, 0.02, n),
        }
    )
    sample = panel.corr()
    shrunk = ledoit_wolf(panel).matrix
    stds = np.sqrt(np.diag(shrunk.to_numpy()))
    shrunk_corr = shrunk.to_numpy() / np.outer(stds, stds)
    assert abs(shrunk_corr[0, 1]) < abs(sample.iloc[0, 1])


def test_estimates_are_symmetric() -> None:
    for name in ESTIMATORS:
        m = estimate(_staggered(), estimator=name).matrix.to_numpy()
        assert np.allclose(m, m.T)


# ── exponential weighting ────────────────────────────────────────────────────

def test_recent_observations_dominate_a_short_halflife() -> None:
    """A regime change must move the estimate, and faster for a shorter halflife."""
    rng = np.random.default_rng(2)
    calm = rng.normal(0, 0.005, 400)
    wild = rng.normal(0, 0.040, 100)
    panel = pd.DataFrame({"X": np.concatenate([calm, wild])})

    slow = exponentially_weighted(panel, halflife=250.0).matrix.iloc[0, 0]
    fast = exponentially_weighted(panel, halflife=20.0).matrix.iloc[0, 0]
    flat = empirical(panel).matrix.iloc[0, 0]
    assert fast > slow > flat


def test_equal_weighting_is_the_limit_of_a_long_halflife() -> None:
    panel = _clean_panel(k=4, n=600)
    long_life = exponentially_weighted(panel, halflife=1e7).matrix
    flat = empirical(panel).matrix
    assert np.allclose(long_life.to_numpy(), flat.to_numpy(), rtol=1e-3)


def test_the_halflife_is_reported_because_it_is_the_whole_claim() -> None:
    result = exponentially_weighted(_clean_panel(), halflife=63.0)
    assert "halflife 63" in (result.note or "")
    assert "effective sample" in (result.note or "")


# ── dispatch ─────────────────────────────────────────────────────────────────

def test_an_unknown_estimator_raises_rather_than_falling_back() -> None:
    with pytest.raises(ValueError, match="unknown covariance estimator"):
        estimate(_clean_panel(), estimator="ledoit_wolfe")


def test_the_default_remains_the_empirical_one() -> None:
    """No existing result may move because this module exists."""
    panel = _clean_panel()
    assert estimate(panel).estimator == "empirical_complete_case"


def test_the_pairwise_default_is_untouched() -> None:
    """optimizer.covariance still does exactly what it did."""
    panel = _staggered()
    direct = panel.dropna(axis=1, how="all").cov() + np.eye(panel.shape[1]) * 1e-8
    assert np.allclose(pairwise_default(panel).to_numpy(), direct.to_numpy())
