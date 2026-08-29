"""Validation: fold construction, metric honesty, and significance behaviour."""

from __future__ import annotations

from datetime import date as Date
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from src.quant.pit.calendar import CalendarRangeError, TradingCalendar
from src.quant.validation.metrics import (
    bootstrap_interval, calibration_bins, classification_metrics,
    directional_accuracy, expected_calibration_error, ic_summary,
    per_date_ic, regression_metrics,
)
from src.quant.validation.significance import (
    deflated_sharpe_ratio, minimum_track_record_length,
    probability_of_backtest_overfitting,
)
from src.quant.validation.walkforward import build_plan, fold_row_counts, verify_no_overlap


def _calendar(n: int = 2600) -> TradingCalendar:
    days, cursor = [], Date(2013, 1, 1)
    while len(days) < n:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return TradingCalendar.from_dates(days)


# ── calendar ────────────────────────────────────────────────────────────────


def test_calendar_anchors_a_weekend_to_the_prior_session():
    calendar = TradingCalendar.from_dates(
        [Date(2024, 1, 4), Date(2024, 1, 5), Date(2024, 1, 8)]
    )
    assert calendar.on_or_before(Date(2024, 1, 7)) == Date(2024, 1, 5)


def test_calendar_shift_returns_none_past_the_end_rather_than_clamping():
    """Clamping would silently shorten a label horizon at the end of the sample."""
    calendar = TradingCalendar.from_dates([Date(2024, 1, 2), Date(2024, 1, 3)])
    assert calendar.shift(Date(2024, 1, 2), 5) is None


def test_calendar_rejects_a_non_session():
    calendar = TradingCalendar.from_dates([Date(2024, 1, 2)])
    with pytest.raises(CalendarRangeError):
        calendar.index_of(Date(2024, 1, 3))


# ── folds ───────────────────────────────────────────────────────────────────


def test_folds_are_chronological_and_never_overlap():
    calendar = _calendar()
    plan = build_plan(
        calendar, start=calendar.start, end=calendar.end,
        label_horizon_sessions=21, validation_sessions=252, min_train_sessions=756,
    )
    for fold in plan.folds:
        assert fold.train_start <= fold.train_end < fold.validation_start <= fold.validation_end
    for a, b in zip(plan.folds, plan.folds[1:]):
        assert a.validation_end < b.validation_start


def test_expanding_scheme_grows_the_training_window():
    calendar = _calendar()
    plan = build_plan(
        calendar, start=calendar.start, end=calendar.end,
        label_horizon_sessions=21, validation_sessions=252,
        min_train_sessions=756, scheme="expanding",
    )
    starts = {fold.train_start for fold in plan.folds}
    assert len(starts) == 1
    lengths = [
        calendar.count_between(fold.train_start, fold.train_end) for fold in plan.folds
    ]
    assert lengths == sorted(lengths)


def test_rolling_scheme_keeps_the_training_window_fixed():
    calendar = _calendar()
    plan = build_plan(
        calendar, start=calendar.start, end=calendar.end,
        label_horizon_sessions=21, validation_sessions=252,
        min_train_sessions=756, scheme="rolling", train_sessions=756,
    )
    lengths = {
        calendar.count_between(fold.train_start, fold.train_end) for fold in plan.folds
    }
    assert lengths == {756}


def test_rolling_scheme_requires_a_window_length():
    calendar = _calendar()
    with pytest.raises(ValueError, match="train_sessions"):
        build_plan(
            calendar, start=calendar.start, end=calendar.end,
            label_horizon_sessions=21, scheme="rolling",
        )


def test_overlap_verification_and_row_counts_agree():
    calendar = _calendar()
    plan = build_plan(
        calendar, start=calendar.start, end=calendar.end,
        label_horizon_sessions=21, validation_sessions=252, min_train_sessions=756,
    )
    frame = pd.DataFrame(
        {"date": np.repeat(calendar.sessions, 3),
         "symbol": ["A", "B", "C"] * len(calendar.sessions)}
    )
    assert verify_no_overlap(plan, frame)["ok"]
    rows = fold_row_counts(plan, frame)
    assert all(row["train_rows"] > 0 and row["validation_rows"] > 0 for row in rows)


def test_an_insufficient_history_raises_rather_than_producing_one_thin_fold():
    calendar = _calendar(n=400)
    with pytest.raises(ValueError):
        build_plan(
            calendar, start=calendar.start, end=calendar.end,
            label_horizon_sessions=21, validation_sessions=252, min_train_sessions=756,
        )


# ── metrics ─────────────────────────────────────────────────────────────────


def test_directional_accuracy_is_reported_against_the_base_rate():
    """In a rising sample, always saying 'up' scores well above 50%."""
    truth = np.array([0.01] * 80 + [-0.01] * 20)
    always_up = np.ones(100)
    result = directional_accuracy(truth, always_up)
    assert result["directional_accuracy"] == pytest.approx(0.80)
    assert result["base_rate"] == pytest.approx(0.80)
    assert result["directional_edge"] == pytest.approx(0.0)


def test_rmse_vs_zero_exposes_a_model_worse_than_predicting_nothing():
    rng = np.random.default_rng(0)
    truth = rng.normal(0, 0.05, 400)
    noisy = truth * 0.05 + rng.normal(0, 0.09, 400)
    metrics = regression_metrics(truth, noisy)
    assert metrics.values["rmse_vs_zero"] > 1.0


def test_scale_free_predictors_do_not_report_rmse():
    rng = np.random.default_rng(1)
    truth = rng.normal(0, 0.05, 200)
    metrics = regression_metrics(truth, rng.normal(size=200), scale_free=True)
    assert "rmse" not in metrics.values
    assert "spearman" in metrics.values
    assert any("suppressed" in note for note in metrics.notes)


def test_too_few_observations_reports_nothing():
    metrics = regression_metrics(np.arange(5.0), np.arange(5.0))
    assert metrics.values == {}
    assert metrics.notes


def test_newey_west_lags_follow_the_overlap_and_reduce_the_t_stat():
    rng = np.random.default_rng(3)
    base = rng.normal(0.02, 0.1, 200)
    # Overlapping observations: a moving average induces positive autocorrelation.
    overlapping = pd.Series(base).rolling(4, min_periods=1).mean()
    summary = ic_summary(overlapping, horizon_sessions=21, step_sessions=5)
    assert summary["newey_west_lags"] == 4
    assert abs(summary["t_stat"]) < abs(summary["naive_t_stat"])


def test_ic_ignores_dates_with_no_ranking():
    dates = [Date(2024, 1, i + 1) for i in range(3)]
    rows = []
    for index, day in enumerate(dates):
        for name in range(12):
            rows.append(
                {"date": day, "symbol": f"S{name}",
                 "prediction": 1.0 if index == 1 else float(name),
                 "y": float(name)}
            )
    frame = pd.DataFrame(rows)
    ic = per_date_ic(frame, prediction_column="prediction", target_column="y")
    # The flat date produces no IC rather than a zero folded into the mean.
    assert len(ic) == 2


def test_calibration_bins_omit_thin_buckets():
    rng = np.random.default_rng(0)
    proba = np.concatenate([rng.uniform(0.4, 0.6, 300), [0.99, 0.99]])
    truth = (rng.uniform(size=302) < proba).astype(float)
    bins = calibration_bins(truth, proba, min_per_bin=20)
    assert all(row["count"] >= 20 for row in bins)


def test_classification_metrics_compare_brier_against_the_base_rate():
    rng = np.random.default_rng(0)
    truth = (rng.uniform(size=500) < 0.6).astype(float)
    useless = np.full(500, 0.6)
    metrics = classification_metrics(truth, useless)
    assert metrics.values["brier_vs_base_rate"] == pytest.approx(1.0, abs=0.02)


def test_blocked_bootstrap_is_wider_than_iid_on_autocorrelated_data():
    rng = np.random.default_rng(0)
    values = pd.Series(rng.normal(0.02, 0.1, 300)).rolling(10, min_periods=1).mean().to_numpy()
    iid = bootstrap_interval(values, seed=1)
    blocked = bootstrap_interval(values, block=10, seed=1)
    assert (blocked["upper"] - blocked["lower"]) > (iid["upper"] - iid["lower"])


# ── significance ────────────────────────────────────────────────────────────


def test_deflated_sharpe_kills_the_best_of_many_noise_runs():
    """The central defence against multiple comparisons."""
    rng = np.random.default_rng(0)
    noise = rng.normal(0, 0.02, (400, 60))
    sharpes = noise.mean(axis=0) / noise.std(axis=0, ddof=1)
    best = noise[:, int(np.argmax(sharpes))]

    naive = deflated_sharpe_ratio(best, trials=1, periods_per_year=52)
    corrected = deflated_sharpe_ratio(
        best, trials=60, periods_per_year=52, trial_sharpes=sharpes
    )
    assert naive.significant is True
    assert corrected.significant is False
    assert corrected.expected_max_sharpe > 0


def test_deflated_sharpe_threshold_is_in_plausible_sharpe_units():
    """The null threshold must be scaled by Sharpe dispersion, not raw normal quantiles.

    Omitting that scaling produces an expected maximum around 20 annualised,
    which would declare every strategy insignificant.
    """
    rng = np.random.default_rng(1)
    returns = rng.normal(0.003, 0.02, 500)
    result = deflated_sharpe_ratio(returns, trials=200, periods_per_year=52)
    assert 0.0 < result.expected_max_sharpe < 5.0


def test_pbo_is_undefined_for_a_single_configuration():
    """Overfitting is a property of selection; with one candidate there was none."""
    rng = np.random.default_rng(0)
    result = probability_of_backtest_overfitting(rng.normal(size=(200, 1)))
    assert result["pbo"] is None
    assert "selection" in result["note"]


def test_pbo_on_pure_noise_is_near_one_half():
    rng = np.random.default_rng(0)
    result = probability_of_backtest_overfitting(rng.normal(size=(400, 30)), blocks=8)
    assert 0.2 < result["pbo"] < 0.8


def test_minimum_track_record_length_is_reported():
    rng = np.random.default_rng(0)
    result = minimum_track_record_length(rng.normal(0.004, 0.02, 500))
    assert result["required_periods"] > 0
    assert result["observed_periods"] == 500


def test_minimum_track_record_declines_when_the_sharpe_is_negative():
    rng = np.random.default_rng(0)
    result = minimum_track_record_length(rng.normal(-0.004, 0.02, 500))
    assert result["required_periods"] is None
