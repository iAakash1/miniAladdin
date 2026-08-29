"""
Leakage tests — the ones that must be able to fail.

Every test here is paired: one asserts the correct implementation passes, and
where the property is subtle, a sibling asserts that a *deliberately broken*
implementation fails. A leakage test that cannot fail is decoration, and the
repository already makes that argument for the panel builder — mutation-testing
`_pit_window` to confirm the flagship test breaks. The same standard applies
here.
"""

from __future__ import annotations

from datetime import date as Date
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from src.quant.features import macro, price  # noqa: F401 - registers features
from src.quant.features.cross_section import UniverseRequired, cross_sectional_frame
from src.quant.features.registry import REGISTRY
from src.quant.labels import compute_symbol_labels, forward_return
from src.quant.models.base import FoldImputer
from src.quant.pit.calendar import TradingCalendar
from src.quant.pit.guards import (
    LeakageError,
    assert_features_declared_safe,
    assert_no_future_dependence,
    assert_no_target_leakage,
    assert_split_is_purged,
    assert_universe_is_point_in_time,
)
from src.quant.validation.walkforward import build_plan


def _series(n: int = 400, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = [Date(2020, 1, 1) + timedelta(days=i) for i in range(n)]
    return pd.DataFrame(
        {
            "date": dates,
            "total_return": rng.normal(0.0004, 0.015, n),
            "dollar_volume": np.exp(rng.normal(18, 0.35, n)),
        }
    )


# ── every registered feature ────────────────────────────────────────────────


@pytest.mark.parametrize("feature_name", REGISTRY.per_symbol_names())
def test_no_registered_feature_depends_on_the_future(feature_name):
    """Perturb only post-cutoff data; every pre-cutoff feature value must be identical.

    Makes no assumption about how a feature is computed, so it catches any path
    from the future to the present: a centred window, a negative shift, a
    fitted statistic over the whole sample.
    """
    source = _series()
    cutoff = source["date"].iloc[250]
    computer = REGISTRY.computer(feature_name)

    def build(frame: pd.DataFrame) -> pd.DataFrame:
        out = frame.copy()
        out["value"] = computer(frame).to_numpy()
        return out

    # DISTINCT factors per column. A uniform scale cancels inside any feature
    # that is a ratio of two perturbed inputs (amihud_21 is |r| / dollar_volume),
    # leaving the output bit-identical — a vacuous pass the `guard_is_live`
    # check would correctly reject.
    report = assert_no_future_dependence(
        build, source, cutoff=cutoff,
        perturb_columns=["total_return", "dollar_volume"], compare_columns=["value"],
        scale={"total_return": 3.0, "dollar_volume": 7.0},
    )
    report.raise_for_status()


def test_the_leakage_guard_actually_catches_a_leak():
    """A centred rolling mean must fail. Without this the suite proves nothing."""
    source = _series()
    cutoff = source["date"].iloc[250]

    def leaky(frame: pd.DataFrame) -> pd.DataFrame:
        out = frame.copy()
        out["value"] = frame["total_return"].rolling(11, min_periods=11, center=True).mean()
        return out

    report = assert_no_future_dependence(
        leaky, source, cutoff=cutoff,
        perturb_columns=["total_return"], compare_columns=["value"],
    )
    assert not report.passed
    with pytest.raises(LeakageError):
        report.raise_for_status()


def test_a_negative_shift_in_a_feature_is_caught():
    source = _series()
    cutoff = source["date"].iloc[250]

    def leaky(frame: pd.DataFrame) -> pd.DataFrame:
        out = frame.copy()
        out["value"] = frame["total_return"].shift(-1)
        return out

    report = assert_no_future_dependence(
        leaky, source, cutoff=cutoff,
        perturb_columns=["total_return"], compare_columns=["value"],
    )
    assert not report.passed


# ── labels ──────────────────────────────────────────────────────────────────


def test_labels_are_null_for_the_final_horizon():
    """A label must not silently shorten its horizon at the end of the sample."""
    frame = _series(120)
    labels = compute_symbol_labels(frame)
    assert labels["fwd_ret_21"].tail(21).isna().all()
    assert labels["fwd_ret_21"].iloc[-22] == labels["fwd_ret_21"].iloc[-22]  # not NaN


def test_forward_return_matches_an_explicit_product():
    returns = pd.Series([0.01] * 20)
    expected = 1.01**5 - 1
    assert forward_return(returns, 5).iloc[0] == pytest.approx(expected, rel=1e-12)


def test_forward_return_starts_after_the_observation_date():
    """The label must not include the observation date's own return."""
    returns = pd.Series([0.5] + [0.0] * 20)
    # Day 0's own +50% must not appear in day 0's forward return.
    assert forward_return(returns, 5).iloc[0] == pytest.approx(0.0, abs=1e-12)


# ── target leakage ──────────────────────────────────────────────────────────


def test_target_leakage_is_detected_by_name_and_by_correlation():
    rng = np.random.default_rng(0)
    frame = pd.DataFrame({"a": rng.normal(size=300)})
    frame["y"] = frame["a"] * 2.5 - 0.1
    frame["clean"] = rng.normal(size=300)

    report = assert_no_target_leakage(frame, ["a", "clean"], ["y"])
    assert not report.passed
    assert any(check["check"] == "no_target_correlation" for check in report.failures())

    clean = assert_no_target_leakage(frame, ["clean"], ["y"])
    assert clean.passed


def test_a_label_left_in_the_feature_list_is_caught():
    frame = pd.DataFrame({"y": np.arange(100.0), "f": np.arange(100.0)})
    report = assert_no_target_leakage(frame, ["f", "y"], ["y"])
    assert not report.passed


# ── cross-sectional universe ────────────────────────────────────────────────


def test_cross_sectional_normalisation_refuses_an_implicit_universe():
    frame = pd.DataFrame(
        {"date": [Date(2024, 1, 2)] * 20, "symbol": [f"S{i}" for i in range(20)],
         "f": np.arange(20.0)}
    )
    with pytest.raises(UniverseRequired):
        cross_sectional_frame(frame, ["f"])


def test_cross_sectional_values_ignore_non_members():
    """A name outside the universe must not influence a member's rank."""
    day = Date(2024, 1, 2)
    members = [f"S{i}" for i in range(12)]
    frame = pd.DataFrame(
        {"date": [day] * 14, "symbol": members + ["OUT1", "OUT2"],
         "f": list(np.linspace(0, 1, 12)) + [999.0, -999.0]}
    )
    out = cross_sectional_frame(frame, ["f"], universe_for={day: set(members)})
    assert out.loc[out["symbol"] == "OUT1", "f_xs"].isna().all()
    assert out.loc[out["symbol"] == "S11", "f_xs"].iloc[0] == pytest.approx(1.0)


# ── splits ──────────────────────────────────────────────────────────────────


def _weekday_calendar(n: int = 2200) -> TradingCalendar:
    days, cursor = [], Date(2014, 1, 1)
    while len(days) < n:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return TradingCalendar.from_dates(days)


def test_every_walk_forward_fold_has_a_gap_covering_the_label_horizon():
    calendar = _weekday_calendar()
    plan = build_plan(
        calendar, start=calendar.start, end=calendar.end,
        label_horizon_sessions=21, validation_sessions=252, min_train_sessions=756,
    )
    assert len(plan) > 0
    for fold in plan.folds:
        report = assert_split_is_purged(
            fold.train_end, fold.validation_start,
            label_horizon_sessions=21, embargo_sessions=plan.embargo_sessions,
            calendar=calendar,
        )
        report.raise_for_status()


def test_an_insufficient_gap_is_refused():
    calendar = _weekday_calendar()
    train_end = calendar.sessions[1000]
    too_close = calendar.shift(train_end, 3)
    report = assert_split_is_purged(
        train_end, too_close, label_horizon_sessions=21, embargo_sessions=5, calendar=calendar
    )
    assert not report.passed


def test_holdout_is_outside_every_fold():
    calendar = _weekday_calendar()
    plan = build_plan(
        calendar, start=calendar.start, end=calendar.end,
        label_horizon_sessions=21, validation_sessions=252,
        min_train_sessions=756, holdout_sessions=252,
    )
    assert plan.holdout_start is not None
    for fold in plan.folds:
        assert fold.validation_end < plan.holdout_start


# ── fold-local statistics ───────────────────────────────────────────────────


def test_imputer_statistics_come_from_the_training_fold_only():
    """Fitting a scaler on the full sample is a leak no downstream metric shows."""
    train = np.array([[1.0], [2.0], [3.0]])
    validation = np.array([[1000.0], [2000.0]])

    imputer = FoldImputer(standardise=True).fit(train, feature_names=["f"])
    train_mean = imputer.means[0]

    pooled = FoldImputer(standardise=True).fit(
        np.vstack([train, validation]), feature_names=["f"]
    )
    assert train_mean == pytest.approx(2.0)
    assert pooled.means[0] != pytest.approx(train_mean)
    # Transforming validation must not change what was learned from training.
    imputer.transform(validation)
    assert imputer.means[0] == pytest.approx(train_mean)


def test_imputer_fills_with_median_never_zero():
    train = np.array([[10.0], [12.0], [np.nan], [14.0]])
    imputer = FoldImputer().fit(train, feature_names=["f"])
    filled = imputer.transform(np.array([[np.nan]]))
    assert filled[0, 0] == pytest.approx(12.0)


# ── declared safety ─────────────────────────────────────────────────────────


def test_every_registered_feature_declares_point_in_time_safety():
    report = assert_features_declared_safe(REGISTRY, REGISTRY.names(pit_only=False))
    report.raise_for_status()
    assert REGISTRY.unsafe() == []


def test_an_unregistered_feature_is_refused():
    report = assert_features_declared_safe(REGISTRY, ["not_a_real_feature"])
    assert not report.passed


# ── universe ────────────────────────────────────────────────────────────────


class _FakeSnapshot:
    def __init__(self, as_of, symbols):
        self.as_of = as_of
        self.symbols = tuple(symbols)


class _FakeUniverse:
    def __init__(self, snapshots, point_in_time=True):
        self.snapshots = snapshots
        self.point_in_time = point_in_time


def test_a_universe_that_only_grows_is_flagged_as_survivorship_biased():
    growing = _FakeUniverse([
        _FakeSnapshot(Date(2020, 1, 31), ["A"]),
        _FakeSnapshot(Date(2020, 2, 28), ["A", "B"]),
        _FakeSnapshot(Date(2020, 3, 31), ["A", "B", "C"]),
    ])
    report = assert_universe_is_point_in_time(growing)
    assert not report.passed
    assert any(check["check"] == "universe_has_exits" for check in report.failures())


def test_a_universe_with_exits_passes():
    realistic = _FakeUniverse([
        _FakeSnapshot(Date(2020, 1, 31), ["A", "B"]),
        _FakeSnapshot(Date(2020, 2, 28), ["A", "C"]),
        _FakeSnapshot(Date(2020, 3, 31), ["C", "D"]),
    ])
    assert_universe_is_point_in_time(realistic).raise_for_status()
