"""
Negative controls — and the distinction between a leak and a slow signal.

The `shifted_forward` control was written as a leakage gate and reclassified as
a diagnostic after direct measurement showed it tests horizon persistence
instead. These tests pin both the mechanics and that reclassification, so it
cannot drift back silently in either direction.
"""

from __future__ import annotations

from datetime import date as Date
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from src.quant.validation.controls import (
    BLOCKING_CONTROLS,
    CONTROL_IC_THRESHOLD,
    CONTROL_T_THRESHOLD,
    ControlOutcome,
    permute_symbols_within_date,
    shift_target_forward,
    shuffle_within_date,
    summarise,
)


def _panel(dates: int = 6, symbols: int = 8) -> pd.DataFrame:
    return pd.DataFrame([
        {"date": Date(2024, 1, 5) + timedelta(days=7 * d),
         "symbol": f"S{s:02d}", "y": float(d * 100 + s), "feat": float(s)}
        for d in range(dates) for s in range(symbols)
    ])


# ── shuffle ─────────────────────────────────────────────────────────────────


def test_shuffle_preserves_each_dates_target_multiset():
    """Level, dispersion and regime effects must survive; only pairing dies."""
    frame = _panel()
    shuffled = shuffle_within_date(frame, "y", seed=3)
    for day in frame["date"].unique():
        assert sorted(frame[frame["date"] == day]["y"]) == sorted(
            shuffled[shuffled["date"] == day]["y"]
        )


def test_shuffle_destroys_the_feature_target_pairing():
    frame = _panel()
    shuffled = shuffle_within_date(frame, "y", seed=3)
    assert not np.array_equal(frame["y"].to_numpy(), shuffled["y"].to_numpy())


def test_shuffle_leaves_features_untouched():
    frame = _panel()
    shuffled = shuffle_within_date(frame, "y", seed=3)
    np.testing.assert_array_equal(frame["feat"].to_numpy(), shuffled["feat"].to_numpy())


def test_shuffle_preserves_the_null_pattern():
    """Permuting must not change which rows are observed, or the control would
    alter sample composition as well as pairing."""
    frame = _panel()
    frame.loc[frame.index[:5], "y"] = np.nan
    shuffled = shuffle_within_date(frame, "y", seed=1)
    np.testing.assert_array_equal(frame["y"].isna().to_numpy(), shuffled["y"].isna().to_numpy())


def test_shuffle_is_deterministic_given_a_seed():
    frame = _panel()
    a = shuffle_within_date(frame, "y", seed=7)["y"].to_numpy()
    b = shuffle_within_date(frame, "y", seed=7)["y"].to_numpy()
    np.testing.assert_array_equal(a, b)


# ── shift ───────────────────────────────────────────────────────────────────


def test_shift_moves_each_symbols_own_future_target_back():
    frame = _panel(dates=5, symbols=2)
    shifted = shift_target_forward(frame, "y", periods=1)
    for symbol in frame["symbol"].unique():
        original = frame[frame["symbol"] == symbol].sort_values("date")["y"].tolist()
        moved = shifted[shifted["symbol"] == symbol].sort_values("date")["y"].tolist()
        assert moved == original[1:]


def test_shift_never_borrows_another_symbols_target():
    """A global shift would hand one name's outcome to another."""
    frame = pd.DataFrame(
        [{"date": Date(2024, 1, 5) + timedelta(days=7 * d), "symbol": "A", "y": 1.0} for d in range(4)]
        + [{"date": Date(2024, 1, 5) + timedelta(days=7 * d), "symbol": "B", "y": 99.0} for d in range(4)]
    )
    shifted = shift_target_forward(frame, "y", periods=1)
    assert set(shifted[shifted["symbol"] == "A"]["y"]) == {1.0}
    assert set(shifted[shifted["symbol"] == "B"]["y"]) == {99.0}


def test_shift_drops_rows_with_no_future_target_rather_than_filling():
    frame = _panel(dates=5, symbols=3)
    shifted = shift_target_forward(frame, "y", periods=2)
    assert len(shifted) == len(frame) - 2 * 3


# ── classification of controls ──────────────────────────────────────────────


def test_only_the_pairing_destroying_controls_block():
    """`shifted_forward` is a diagnostic, established by measurement.

    Leak-free passthrough baselines retain 122% and 61% of their real-target IC
    on a target displaced 4 periods, while collapsing to ~0 when shuffled. The
    control therefore measures horizon persistence, not contamination.
    """
    assert BLOCKING_CONTROLS == {"shuffled_within_date", "permuted_symbols"}
    assert "shifted_forward" not in BLOCKING_CONTROLS


def test_a_failing_diagnostic_does_not_invalidate_the_study():
    outcomes = [
        ControlOutcome("shuffled_within_date", "d", -0.0035, -1.07, 500),
        ControlOutcome("shifted_forward", "d", 0.0271, 2.00, 500),
        ControlOutcome("permuted_symbols", "d", -0.0009, -0.27, 500),
    ]
    report = summarise(outcomes)
    assert report["all_passed"] is True
    assert report["blocking_failed"] == []
    assert report["diagnostic_findings"] == ["shifted_forward"]
    assert "slow-moving signal rather than contamination" in report["interpretation"]


def test_a_failing_blocking_control_does_invalidate_the_study():
    outcomes = [
        ControlOutcome("shuffled_within_date", "d", 0.0400, 3.10, 500),
        ControlOutcome("permuted_symbols", "d", -0.0009, -0.27, 500),
    ]
    report = summarise(outcomes)
    assert report["all_passed"] is False
    assert report["blocking_failed"] == ["shuffled_within_date"]
    assert "Do not proceed to a holdout" in report["interpretation"]


def test_a_control_with_no_result_counts_as_failed():
    """Absent evidence is not passing evidence."""
    assert ControlOutcome("shuffled_within_date", "d", None, None, 0).passed is False


@pytest.mark.parametrize(
    "ic,t,expected",
    [(0.001, 0.4, True), (0.05, 0.5, False), (0.001, 3.0, False), (0.0199, 1.99, True)],
)
def test_control_pass_thresholds(ic, t, expected):
    assert ControlOutcome("shuffled_within_date", "d", ic, t, 500).passed is expected
    assert CONTROL_IC_THRESHOLD == 0.02 and CONTROL_T_THRESHOLD == 2.0


def test_permuted_symbols_is_deterministic_and_distinct_from_shuffle():
    frame = _panel()
    a = permute_symbols_within_date(frame, "y", seed=0)["y"].to_numpy()
    b = permute_symbols_within_date(frame, "y", seed=0)["y"].to_numpy()
    np.testing.assert_array_equal(a, b)
    plain = shuffle_within_date(frame, "y", seed=0)["y"].to_numpy()
    assert not np.array_equal(a, plain), "the two controls must not use the same permutation"
