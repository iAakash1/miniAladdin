"""Corporate-action adjustment: the property that makes returns point-in-time."""

from __future__ import annotations

from datetime import date as Date

import numpy as np
import pandas as pd
import pytest

from src.quant.pit.adjust import (
    MAX_SPLIT_RATIO,
    point_in_time_returns,
    split_ratios,
    total_return_index,
)


def _bars(closes, start=Date(2024, 1, 1)):
    dates = pd.bdate_range(start, periods=len(closes)).date
    return pd.DataFrame(
        {"date": dates, "close": closes, "volume": [1_000_000.0] * len(closes)}
    )


def test_split_does_not_create_a_fake_return():
    """A 4:1 split must read as 0%, not -75%.

    This is the single most damaging unhandled corporate action: without it the
    largest reversal signal and the largest volatility observation in the whole
    sample are both fabrications.
    """
    bars = _bars([400.0, 404.0, 101.0, 102.0])
    splits = pd.DataFrame(
        {"symbol": ["X"], "date": [bars["date"].iloc[2]], "to_factor": [4.0], "for_factor": [1.0]}
    )
    result = point_in_time_returns(bars, symbol="X", splits=splits)
    split_day_return = result.frame["total_return"].iloc[2]
    assert split_day_return == pytest.approx(0.0, abs=1e-12)
    assert result.applied_splits == 1


def test_unadjusted_split_would_fabricate_a_crash():
    """Proves the previous test is not vacuous: without the split record, -75%."""
    bars = _bars([400.0, 404.0, 101.0, 102.0])
    result = point_in_time_returns(bars, symbol="X", splits=None)
    assert result.frame["total_return"].iloc[2] == pytest.approx(-0.75, abs=1e-9)


def test_dividend_enters_total_return_but_not_price_return():
    bars = _bars([100.0, 100.0, 99.0])
    dividends = pd.DataFrame(
        {"symbol": ["X"], "date": [bars["date"].iloc[2]], "amount": [1.0]}
    )
    result = point_in_time_returns(bars, symbol="X", dividends=dividends)
    assert result.frame["total_return"].iloc[2] == pytest.approx(0.0, abs=1e-12)
    assert result.frame["price_return"].iloc[2] == pytest.approx(-0.01, abs=1e-12)


def test_returns_use_only_actions_dated_on_or_before_the_bar():
    """Extending the series with a FUTURE split must not change any past return.

    This is the point-in-time property stated as a test. A back-adjusted price
    series fails it by construction, which is why this module computes returns.
    """
    bars = _bars([100.0, 101.0, 102.0, 103.0, 104.0])
    baseline = point_in_time_returns(bars, symbol="X", splits=None).frame["total_return"]

    future_split = pd.DataFrame(
        {"symbol": ["X"], "date": [Date(2030, 1, 1)], "to_factor": [4.0], "for_factor": [1.0]}
    )
    with_future = point_in_time_returns(bars, symbol="X", splits=future_split).frame["total_return"]

    pd.testing.assert_series_equal(baseline, with_future, check_names=False)


def test_absurd_split_ratio_is_quarantined_not_applied():
    bars = _bars([100.0, 101.0, 102.0])
    bad = pd.DataFrame(
        {"symbol": ["X"], "date": [bars["date"].iloc[1]],
         "to_factor": [MAX_SPLIT_RATIO * 10], "for_factor": [1.0]}
    )
    result = point_in_time_returns(bars, symbol="X", splits=bad)
    assert result.applied_splits == 0
    assert len(result.quarantined_splits) == 1
    assert result.frame["total_return"].iloc[1] == pytest.approx(0.01, abs=1e-9)


def test_first_return_is_null_not_zero():
    """The return into the first observed bar is unobservable, so it is NULL.

    Writing 0.0 would make an unknown indistinguishable from a flat day, which
    biases realised volatility downward at the start of every symbol's history.
    """
    result = point_in_time_returns(_bars([100.0, 101.0]), symbol="X")
    assert pd.isna(result.frame["total_return"].iloc[0])


def test_dollar_volume_is_continuous_through_a_split():
    bars = pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-01", periods=3).date,
            "close": [400.0, 400.0, 100.0],
            "volume": [1_000_000.0, 1_000_000.0, 4_000_000.0],
        }
    )
    splits = pd.DataFrame(
        {"symbol": ["X"], "date": [bars["date"].iloc[2]], "to_factor": [4.0], "for_factor": [1.0]}
    )
    result = point_in_time_returns(bars, symbol="X", splits=splits)
    values = result.frame["dollar_volume"].to_numpy()
    assert values[1] == pytest.approx(values[2], rel=1e-12)


def test_total_return_index_breaks_at_a_gap_rather_than_bridging_it():
    """A NULL return must not be silently treated as a flat day."""
    returns = pd.Series([np.nan, 0.01, 0.01, np.nan, 0.01])
    index = total_return_index(returns)
    assert not pd.isna(index.iloc[2])
    assert pd.isna(index.iloc[3])
    assert pd.isna(index.iloc[4])


def test_split_ratio_drops_no_op_rows():
    frame = pd.DataFrame(
        {"symbol": ["A", "B"], "date": [Date(2024, 1, 1)] * 2,
         "to_factor": [1.0, 2.0], "for_factor": [1.0, 1.0]}
    )
    assert list(split_ratios(frame)["symbol"]) == ["B"]


def test_duplicate_sessions_are_collapsed_and_reported():
    dates = list(pd.bdate_range("2024-01-01", periods=3).date)
    bars = pd.DataFrame(
        {"date": dates + [dates[1]], "close": [100.0, 101.0, 102.0, 101.5],
         "volume": [1e6] * 4}
    )
    result = point_in_time_returns(bars, symbol="X")
    assert len(result.frame) == 3
    assert any("duplicate" in warning for warning in result.warnings)
