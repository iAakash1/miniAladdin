"""Factor stability tests."""

from __future__ import annotations

import numpy as np
import pytest

from src.research.stability import MIN_FOR_SPLIT, analyse


def _series(values):
    return [(f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}", float(v)) for i, v in enumerate(values)]


def test_a_decayed_factor_is_named_as_decayed():
    """Worked, then stopped — the case a mean IC hides completely."""
    result = analyse("f", _series([0.15] * 40 + [-0.02] * 40))
    assert result.first_half_ic > 0.1
    assert result.second_half_ic < 0
    assert result.decayed
    assert "worked earlier and stopped" in result.assessment


def test_a_stable_factor_is_not_flagged_as_decayed():
    rng = np.random.default_rng(2)
    result = analyse("f", _series(0.05 + rng.normal(0, 0.01, 80)))
    assert not result.decayed
    assert "stable across the sample" in result.assessment


def test_an_improving_factor_is_described_as_improving():
    """Gradual improvement, not a step.

    A factor that was flat then jumped is *concentrated* as well as improving,
    and the concentration verdict rightly takes precedence — it is the more
    skeptical reading. This fixture spreads the edge so the direction is what
    stands out.
    """
    result = analyse("f", _series([0.03] * 40 + [0.08] * 40))
    assert not result.decayed
    assert result.concentration < 0.6
    assert "improved" in result.assessment


def test_a_concentrated_edge_is_called_an_anecdote():
    """All the edge in one stretch is not a factor."""
    result = analyse("f", _series([0.0] * 60 + [0.9] * 20))
    assert result.concentration > 0.6
    assert "anecdote" in result.assessment


def test_rolling_series_is_produced_and_shorter_than_the_input():
    result = analyse("f", _series([0.05] * 60))
    assert result.rolling
    assert len(result.rolling) == 60 - result.window + 1
    assert result.rolling[-1]["ic"] == pytest.approx(0.05)


def test_best_and_worst_windows_are_identified():
    result = analyse("f", _series([0.2] * 30 + [-0.2] * 30))
    assert result.best_window["mean_ic"] > 0
    assert result.worst_window["mean_ic"] < 0
    assert result.best_window["start"] < result.worst_window["start"]


def test_sign_flips_counted_for_an_unstable_factor():
    result = analyse("f", _series(([0.3] * 10 + [-0.3] * 10) * 4))
    assert result.sign_flips > 0


def test_sign_flips_are_zero_for_a_consistent_factor():
    assert analyse("f", _series([0.08] * 60)).sign_flips == 0


def test_short_series_is_flagged_rather_than_split():
    result = analyse("f", _series([0.05] * (MIN_FOR_SPLIT - 1)))
    assert result.first_half_ic is None
    assert "too few observations" in result.assessment


def test_empty_series_does_not_raise():
    result = analyse("f", [])
    assert result.rolling == []
    assert result.first_half_ic is None
    assert result.concentration == 0.0


def test_window_shrinks_for_short_samples():
    """A 26-week window over 30 observations would leave almost no curve."""
    assert analyse("f", _series([0.05] * 30)).window < 26
