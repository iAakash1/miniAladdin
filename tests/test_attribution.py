"""Cross-sectional return attribution tests."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from src.research.attribution import MIN_NAMES, attribute

FACTORS = ("a", "b")


def _panel(dates: int, names: int, builder, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for step in range(dates):
        day = date(2024, 1, 1) + timedelta(days=7 * step)
        a = rng.normal(size=names)
        b = rng.normal(size=names)
        noise = rng.normal(size=names)
        for i in range(names):
            rows.append({
                "symbol": f"S{i:02d}", "date": day, "a": float(a[i]), "b": float(b[i]),
                "forward_return": float(builder(a[i], b[i], noise[i])),
            })
    return pd.DataFrame(rows)


def test_a_driving_factor_gets_a_positive_return_and_high_t():
    result = attribute(_panel(60, 30, lambda a, b, n: 0.02 * a + 0.002 * n), FACTORS)
    assert result.factor_returns["a"] > 0
    assert result.t_stats["a"] > 4
    assert abs(result.t_stats["b"]) < 3


def test_an_inverted_factor_gets_a_negative_return():
    result = attribute(_panel(60, 30, lambda a, b, n: -0.02 * a + 0.002 * n), FACTORS)
    assert result.factor_returns["a"] < 0


def test_pure_noise_leaves_almost_everything_unexplained():
    """The result this must be willing to report."""
    result = attribute(_panel(60, 30, lambda a, b, n: 0.02 * n, seed=4), FACTORS)
    assert result.unexplained_share > 0.85
    assert "almost none" in result.assessment


def test_a_fully_explained_cross_section_reports_high_r_squared():
    result = attribute(_panel(60, 30, lambda a, b, n: 0.02 * a + 0.01 * b), FACTORS)
    assert result.mean_r_squared > 0.95
    assert result.unexplained_share < 0.05


def test_unexplained_share_uses_the_adjusted_figure():
    """Raw R² flatters a multi-predictor fit on a small cross-section."""
    result = attribute(_panel(40, 30, lambda a, b, n: 0.01 * a + 0.01 * n), FACTORS)
    assert result.mean_adjusted_r_squared + result.unexplained_share == pytest.approx(1.0, abs=1e-9)
    assert result.mean_adjusted_r_squared < result.mean_r_squared


def test_overfit_gap_grows_as_the_cross_section_shrinks():
    """Fewer names per predictor means more of the fit is free parameters."""
    wide = attribute(_panel(40, 60, lambda a, b, n: 0.02 * n, seed=6), FACTORS)
    narrow = attribute(_panel(40, 14, lambda a, b, n: 0.02 * n, seed=6), FACTORS)
    assert narrow.overfit_gap > wide.overfit_gap


def test_market_wide_moves_are_absorbed_by_the_intercept():
    """A day where every name rises must not become a factor return.

    This is the error the per-date arrangement exists to prevent: pooling all
    (name, date) pairs would let a common shock load onto whichever factor
    happened to drift with it.
    """
    rng = np.random.default_rng(9)
    rows = []
    for step in range(60):
        day = date(2024, 1, 1) + timedelta(days=7 * step)
        shock = rng.normal(0, 0.05)          # large common move
        for i in range(30):
            a = rng.normal()
            rows.append({"symbol": f"S{i:02d}", "date": day, "a": a, "b": rng.normal(),
                         "forward_return": shock + 0.0005 * rng.normal()})
    result = attribute(pd.DataFrame(rows), FACTORS)
    assert abs(result.t_stats["a"]) < 3
    assert abs(result.factor_returns["a"]) < 0.002


def test_thin_dates_are_skipped():
    panel = _panel(40, MIN_NAMES - 1, lambda a, b, n: 0.01 * a)
    assert attribute(panel, FACTORS) is None


def test_too_few_dates_returns_none():
    assert attribute(_panel(5, 30, lambda a, b, n: 0.01 * a), FACTORS) is None


def test_missing_columns_return_none():
    panel = _panel(30, 30, lambda a, b, n: 0.01 * a)
    assert attribute(panel, ("nope",)) is None
    assert attribute(panel.drop(columns=["forward_return"]), FACTORS) is None


def test_constant_factor_within_a_date_is_skipped_not_divided_by_zero():
    rng = np.random.default_rng(2)
    rows = []
    for step in range(40):
        day = date(2024, 1, 1) + timedelta(days=7 * step)
        for i in range(30):
            rows.append({"symbol": f"S{i:02d}", "date": day, "a": 1.0,
                         "b": float(rng.normal()),
                         "forward_return": float(0.01 * rng.normal())})
    assert attribute(pd.DataFrame(rows), FACTORS) is None
