"""
Windowed order statistics — tested against a naive reference implementation.

The fast implementations exist only because the obvious ones are too slow.
So the obvious ones are written here, in the clearest form available, and the
fast ones are required to match them exactly. When an optimization and its
reference disagree, the reference is right by definition.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.panel.windowed import (
    rolling_count,
    rolling_median,
    rolling_median_mad,
    rolling_quantile,
    rolling_robust_z,
)

MAD_CONSISTENCY = 1.4826
WINSOR_Z = 3.0


# ── naive references ─────────────────────────────────────────────────────────

def naive_median_mad(values, window, min_count):
    """`.dropna()`-then-compute, one window at a time. Obviously correct."""
    count = len(values)
    median = np.full(count, np.nan)
    mad = np.full(count, np.nan)
    for index in range(count):
        low = max(0, index - window + 1)
        sample = values[low : index + 1]
        sample = sample[~np.isnan(sample)]
        if len(sample) < min_count:
            continue
        center = float(np.median(sample))
        median[index] = center
        mad[index] = float(np.median(np.abs(sample - center)))
    return median, mad


def naive_robust_z(values, window, min_count):
    median, mad = naive_median_mad(values, window, min_count)
    count = len(values)
    z = np.full(count, np.nan)
    for index in range(count):
        if np.isnan(mad[index]) or mad[index] <= 1e-12 or np.isnan(values[index]):
            continue
        raw = (values[index] - median[index]) / (MAD_CONSISTENCY * mad[index])
        z[index] = float(np.clip(raw, -WINSOR_Z, WINSOR_Z))
    return z


def _series(count: int, seed: int, nan_head: int = 0, nan_holes: int = 0):
    rng = np.random.default_rng(seed)
    values = rng.normal(size=count)
    values[:nan_head] = np.nan
    if nan_holes:
        values[rng.choice(count, nan_holes, replace=False)] = np.nan
    return values


# ── median and MAD ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("count,window,min_count", [
    (200, 50, 20),
    (200, 300, 20),     # window longer than the data — all expanding
    (500, 120, 40),
    (61, 60, 20),       # exactly at the fixed/expanding boundary
    (60, 60, 20),
    (59, 60, 20),
])
def test_median_mad_matches_naive(count, window, min_count):
    values = _series(count, seed=count + window)
    fast_median, fast_mad = rolling_median_mad(values, window, min_count)
    slow_median, slow_mad = naive_median_mad(values, window, min_count)
    np.testing.assert_allclose(fast_median, slow_median, rtol=0, atol=1e-12)
    np.testing.assert_allclose(fast_mad, slow_mad, rtol=0, atol=1e-12)


def test_median_mad_matches_naive_with_leading_nans():
    """Derived series (pct_change, rolling means, RSI) all start with NaN."""
    values = _series(300, seed=3, nan_head=14)
    fast = rolling_median_mad(values, 100, 20)
    slow = naive_median_mad(values, 100, 20)
    np.testing.assert_allclose(fast[0], slow[0], rtol=0, atol=1e-12)
    np.testing.assert_allclose(fast[1], slow[1], rtol=0, atol=1e-12)


def test_median_mad_matches_naive_with_interior_nans():
    """Vendor gaps put NaNs mid-series, which forces the nan-aware slow path."""
    values = _series(300, seed=4, nan_head=5, nan_holes=25)
    fast = rolling_median_mad(values, 90, 20)
    slow = naive_median_mad(values, 90, 20)
    np.testing.assert_allclose(fast[0], slow[0], rtol=0, atol=1e-12)
    np.testing.assert_allclose(fast[1], slow[1], rtol=0, atol=1e-12)


def test_min_count_suppresses_short_windows():
    values = _series(100, seed=5)
    median, mad = rolling_median_mad(values, 50, min_count=30)
    assert np.isnan(median[:29]).all()
    assert not np.isnan(median[29:]).any()
    assert np.isnan(mad[:29]).all()


def test_constant_series_has_zero_mad():
    """Zero MAD is the engine's "no usable estimate" signal, not an error."""
    values = np.full(100, 7.0)
    median, mad = rolling_median_mad(values, 50, 20)
    np.testing.assert_allclose(median[19:], 7.0)
    np.testing.assert_allclose(mad[19:], 0.0)


def test_empty_input():
    median, mad = rolling_median_mad(np.array([]), 50, 20)
    assert len(median) == 0 and len(mad) == 0


def test_all_nan_input():
    values = np.full(50, np.nan)
    median, mad = rolling_median_mad(values, 20, 10)
    assert np.isnan(median).all()
    assert np.isnan(mad).all()


def test_chunking_does_not_change_results(monkeypatch):
    """Memory bounding must be invisible in the output."""
    import src.panel.windowed as windowed

    values = _series(600, seed=9)
    expected = rolling_median_mad(values, 100, 20)

    monkeypatch.setattr(windowed, "_CHUNK_BYTES", 512)  # forces many chunks
    actual = rolling_median_mad(values, 100, 20)

    np.testing.assert_array_equal(np.nan_to_num(actual[0]), np.nan_to_num(expected[0]))
    np.testing.assert_array_equal(np.nan_to_num(actual[1]), np.nan_to_num(expected[1]))


# ── robust z ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("count,window", [(200, 60), (400, 150), (100, 200)])
def test_robust_z_matches_naive(count, window):
    values = _series(count, seed=count)
    fast = rolling_robust_z(values, window, 20, MAD_CONSISTENCY, WINSOR_Z)
    slow = naive_robust_z(values, window, 20)
    np.testing.assert_allclose(fast, slow, rtol=0, atol=1e-12)


def test_robust_z_is_winsorized():
    """An extreme outlier must clip, not dominate. Needs real dispersion in
    the window — a constant window has zero MAD and correctly yields NaN,
    which would make this assertion vacuous."""
    values = np.concatenate([_series(199, seed=41), [1e9]])
    z = rolling_robust_z(values, 200, 20, MAD_CONSISTENCY, WINSOR_Z)
    assert np.nanmax(np.abs(z)) <= WINSOR_Z
    assert z[-1] == pytest.approx(WINSOR_Z)


def test_robust_z_is_nan_on_degenerate_scale():
    """A constant window cannot produce a z-score. It must not produce zero."""
    values = np.full(80, 3.0)
    z = rolling_robust_z(values, 50, 20, MAD_CONSISTENCY, WINSOR_Z)
    assert np.isnan(z).all()


# ── quantile and count ───────────────────────────────────────────────────────

@pytest.mark.parametrize("quantile", [0.5, 0.8, 0.95])
def test_quantile_matches_naive(quantile):
    values = _series(300, seed=21, nan_head=7)
    fast = rolling_quantile(values, 80, quantile, 30)

    expected = np.full(len(values), np.nan)
    for index in range(len(values)):
        sample = values[max(0, index - 79) : index + 1]
        sample = sample[~np.isnan(sample)]
        if len(sample) >= 30:
            expected[index] = np.quantile(sample, quantile, method="linear")

    np.testing.assert_allclose(fast, expected, rtol=0, atol=1e-12)


def test_count_ignores_nans():
    values = _series(100, seed=31, nan_head=10)
    counts = rolling_count(values, 50)
    assert counts[0] == 0
    assert counts[9] == 0
    assert counts[10] == 1
    assert counts[-1] == 50
