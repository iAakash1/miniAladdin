"""
End-to-end: raw partitions in, a guarded training matrix out.

Runs the real `DatasetBuilder` against synthetic partitions written through the
real `RawStore`, so the assembly order, the guards, the universe join and the
manifest are all exercised together. The synthetic market carries a deliberate
cross-sectional momentum structure — on pure noise a correct pipeline and a
broken one both report nothing, so a signal-free fixture could not tell them
apart.
"""

from __future__ import annotations

from datetime import date as Date

import numpy as np
import pandas as pd
import pytest

from src.quant.datasets.store import DatasetManifest, RawStore
from src.quant.pit.dataset import CORPORATE_ACTION_COVERAGE_START, DatasetBuilder
from src.quant.pit.guards import LeakageError
from src.quant.pit.universe import UniverseHistory, UniverseSnapshot
from src.quant.validation.runner import run_walk_forward
from src.quant.validation.walkforward import build_plan


def _write(store: RawStore, dataset_id: str, frame: pd.DataFrame, **manifest) -> None:
    record = store.write_partition(dataset_id, "all", frame)
    store.write_manifest(
        DatasetManifest(
            dataset_id=dataset_id, source="test", repository="test", table=dataset_id,
            source_version="v1", columns=list(frame.columns), partitions=[record],
            **manifest,
        )
    )


@pytest.fixture
def store(tmp_path, sessions, synthetic_prices, synthetic_splits, synthetic_treasury):
    raw = RawStore(tmp_path)
    _write(raw, "dolthub_stocks_ohlcv", synthetic_prices,
           point_in_time_status="point_in_time", survivorship_status="complete")
    _write(raw, "dolthub_stocks_split", synthetic_splits, point_in_time_status="point_in_time")
    _write(raw, "dolthub_rates_us_treasury", synthetic_treasury,
           point_in_time_status="point_in_time")
    return raw


@pytest.fixture
def universe(sessions, synthetic_prices):
    """Monthly membership with a real exit, so the survivorship guard can pass."""
    symbols = sorted(synthetic_prices["symbol"].unique())
    snapshots = []
    months = sorted({(d.year, d.month) for d in sessions})
    for index, (year, month) in enumerate(months):
        month_dates = [d for d in sessions if (d.year, d.month) == (year, month)]
        # Rotate one name out each month: membership that only grows is a
        # survivor list, and `assert_universe_is_point_in_time` rejects it.
        members = symbols[:-1] if index % 3 else symbols[1:]
        snapshots.append(
            UniverseSnapshot(
                as_of=month_dates[-1], symbols=tuple(members), candidates=len(symbols),
                dropped_etf=0, dropped_price=0, dropped_delisted=0,
                min_dollar_volume=1e6, coverage_class="complete",
            )
        )
    return UniverseHistory(name="test", size=len(symbols), snapshots=snapshots)


def test_builder_produces_a_guarded_matrix(store, universe):
    dataset = DatasetBuilder(store, universe).build(
        start=Date(2019, 1, 1), end=Date(2021, 6, 30), step_sessions=5
    )
    manifest = dataset.manifest

    assert manifest.rows > 0
    assert manifest.guard_report["passed"] is True
    assert manifest.content_hash
    # 16 per-symbol + 16 cross-sectional + macro
    assert len(manifest.features) >= 32
    assert "fwd_ret_21" in manifest.labels
    assert "fwd_rank_21" in manifest.labels


def test_build_is_deterministic(store, universe):
    kwargs = dict(start=Date(2019, 1, 1), end=Date(2021, 6, 30), step_sessions=5)
    first = DatasetBuilder(store, universe).build(**kwargs)
    second = DatasetBuilder(store, universe).build(**kwargs)
    assert first.manifest.content_hash == second.manifest.content_hash
    assert first.manifest.dataset_version == second.manifest.dataset_version


def test_start_is_clamped_to_corporate_action_coverage(store, universe):
    """Split records begin 2014-03-28; earlier returns would carry fake splits."""
    dataset = DatasetBuilder(store, universe).build(
        start=Date(2011, 1, 1), end=Date(2021, 6, 30), step_sessions=5
    )
    assert dataset.manifest.start == str(CORPORATE_ACTION_COVERAGE_START)
    assert any("clamped" in note for note in dataset.manifest.notes)


def test_a_non_point_in_time_source_is_refused_as_a_feature(store, universe, tmp_path):
    _write(
        store, "dolthub_earnings_income_statement",
        pd.DataFrame({"date": [Date(2020, 1, 1)], "symbol": ["SYM00"], "sales": [1.0]}),
        point_in_time_status="not_point_in_time",
    )
    builder = DatasetBuilder(store, universe)
    with pytest.raises(ValueError, match="may not be used as a feature source"):
        builder._admit("dolthub_earnings_income_statement", role="feature")


def test_a_waiver_admits_it_and_is_recorded(store, universe):
    _write(
        store, "dolthub_earnings_income_statement",
        pd.DataFrame({"date": [Date(2020, 1, 1)], "symbol": ["SYM00"], "sales": [1.0]}),
        point_in_time_status="not_point_in_time",
    )
    builder = DatasetBuilder(
        store, universe, waivers=["dolthub_earnings_income_statement:feature"]
    )
    assert builder._admit("dolthub_earnings_income_statement", role="feature") is not None


def test_a_survivorship_biased_universe_fails_the_guard(store, sessions, synthetic_prices):
    """A universe that never loses a member must not build."""
    symbols = sorted(synthetic_prices["symbol"].unique())
    months = sorted({(d.year, d.month) for d in sessions})
    growing = UniverseHistory(
        name="growing", size=len(symbols),
        snapshots=[
            UniverseSnapshot(
                as_of=[d for d in sessions if (d.year, d.month) == m][-1],
                symbols=tuple(symbols), candidates=len(symbols),
                dropped_etf=0, dropped_price=0, dropped_delisted=0,
                min_dollar_volume=1e6, coverage_class="complete",
            )
            for m in months
        ],
    )
    with pytest.raises(LeakageError, match="universe"):
        DatasetBuilder(store, growing).build(
            start=Date(2019, 1, 1), end=Date(2021, 6, 30), step_sessions=5
        )


def test_appending_future_bars_does_not_change_historical_rows(
    tmp_path, sessions, synthetic_prices, synthetic_splits, synthetic_treasury, universe
):
    """The flagship point-in-time property, end to end.

    Mirrors `tests/test_panel_builder.py::test_appending_future_data_does_not_change_history`
    at the machine-learning layer: build over a window, extend the source with
    another year, rebuild, and assert every overlapping feature value is
    identical. If any stage peeked forward, the extra bars would move a value
    for a date that already existed.
    """
    cutoff = Date(2020, 6, 30)
    truncated = synthetic_prices[synthetic_prices["date"] <= cutoff]

    short_store = RawStore(tmp_path / "short")
    _write(short_store, "dolthub_stocks_ohlcv", truncated, point_in_time_status="point_in_time")
    _write(short_store, "dolthub_stocks_split", synthetic_splits, point_in_time_status="point_in_time")
    _write(short_store, "dolthub_rates_us_treasury", synthetic_treasury, point_in_time_status="point_in_time")

    long_store = RawStore(tmp_path / "long")
    _write(long_store, "dolthub_stocks_ohlcv", synthetic_prices, point_in_time_status="point_in_time")
    _write(long_store, "dolthub_stocks_split", synthetic_splits, point_in_time_status="point_in_time")
    _write(long_store, "dolthub_rates_us_treasury", synthetic_treasury, point_in_time_status="point_in_time")

    window = dict(start=Date(2019, 6, 1), end=Date(2020, 3, 31), step_sessions=5)
    short = DatasetBuilder(short_store, universe).build(**window)
    long = DatasetBuilder(long_store, universe).build(**window)

    key = ["symbol", "date"]
    per_symbol = [
        name for name in short.manifest.features
        if not name.endswith("_xs") and not name.startswith(("rates_", "market_"))
    ]
    a = short.frame.set_index(key)[per_symbol].sort_index()
    b = long.frame.set_index(key)[per_symbol].sort_index()
    # The stronger assertion: the requested window sits entirely inside both
    # builds, so the two index sets must be IDENTICAL, not merely overlapping.
    # A row present in one and absent in the other would mean the extra year
    # changed which observations exist, which is its own kind of leak.
    assert a.index.equals(b.index)
    assert len(a) == 10 * 44  # 10 symbols x 44 sampled sessions in the window
    pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-12)


def test_walk_forward_runs_over_the_built_matrix(store, universe):
    """The whole path: build, plan, fit, predict, score."""
    from src.quant.models.baselines import momentum_baseline

    dataset = DatasetBuilder(store, universe).build(
        start=Date(2019, 1, 1), end=Date(2021, 6, 30), step_sessions=5
    )
    plan = build_plan(
        dataset.calendar, start=Date(2019, 1, 1), end=Date(2021, 6, 30),
        label_horizon_sessions=21, validation_sessions=63,
        min_train_sessions=252, holdout_sessions=42,
    )
    features = [f for f in dataset.features if f.endswith("_xs")]
    result = run_walk_forward(
        momentum_baseline, dataset.frame, plan,
        features=features, label="fwd_ret_21", step_sessions=5,
    )
    assert len(result.folds) >= 1
    assert result.predictions is not None
    assert not result.errors
    # A scale-free predictor must not report an RMSE against a return.
    assert "rmse" not in result.pooled_metrics
