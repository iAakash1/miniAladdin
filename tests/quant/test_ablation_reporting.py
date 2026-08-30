"""
Ablation reporting — the metric names have to agree with the leaderboard's.

`pooled_ic` stores the Newey-West t-statistic under `t_stat`, while the
leaderboard row that renders it is called `ic_t_stat`. Reading the row's name
off `pooled_ic` returns None rather than raising, so an ablation table can be
written with every IC populated and every significance figure blank — which is
exactly what EXP-005's first pass did.

That failure is invisible in the artifact unless someone looks at the right
field, so it is pinned here instead.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.quant.models.baselines import momentum_baseline
from src.quant.pit.calendar import TradingCalendar
from src.quant.study.firewall import reset_for_tests
from src.quant.validation.runner import ExperimentLog, run_walk_forward
from src.quant.validation.walkforward import build_plan


@pytest.fixture(autouse=True)
def _clean():
    reset_for_tests()
    yield
    reset_for_tests()


@pytest.fixture(scope="module")
def result():
    rng = np.random.default_rng(0)
    sessions = pd.bdate_range("2016-01-01", "2024-12-31").date.tolist()
    symbols = [f"S{i:02d}" for i in range(20)]
    rows = []
    for day in sessions:
        signal = rng.normal(size=len(symbols))
        rows.append(pd.DataFrame({
            "date": day,
            "symbol": symbols,
            "mom_252_21_xs": signal,
            "fwd_ret_21": 0.3 * signal + rng.normal(scale=1.0, size=len(symbols)),
            "in_universe": True,
        }))
    frame = pd.concat(rows, ignore_index=True)

    calendar = TradingCalendar(sessions=list(sessions))
    plan = build_plan(
        calendar, start=sessions[0], end=sessions[-1],
        label_horizon_sessions=21, validation_sessions=252,
        min_train_sessions=504, embargo_sessions=5, holdout_sessions=252,
    )
    return run_walk_forward(
        momentum_baseline, frame, plan,
        features=["mom_252_21_xs"], label="fwd_ret_21", step_sessions=1,
    )


def test_pooled_ic_stores_the_t_statistic_under_t_stat(result):
    """Pin the name. A rename must break here, not silently blank a column."""
    assert "t_stat" in result.pooled_ic
    assert result.pooled_ic["t_stat"] is not None
    assert "ic_t_stat" not in result.pooled_ic


def test_train_ic_and_fold_rate_come_from_stability_not_pooled_ic(result):
    assert result.stability("train_mean_ic").get("mean") is not None
    assert result.stability("spearman").get("fold_positive_rate") is not None
    assert result.pooled_ic.get("train_mean_ic") is None
    assert result.pooled_ic.get("fold_ic_positive_rate") is None


def test_the_ablation_row_matches_the_leaderboard_row(result):
    """The two readers must produce the same numbers for the same result.

    This is the assertion that would have caught the EXP-005 reporting defect:
    the ablation built its rows from `pooled_ic` using the leaderboard's field
    names, and got None for every one of them.
    """
    from src.quant.study.run import _gap_of

    log = ExperimentLog()
    log.add(result)
    leader = log.leaderboard()[0]

    ablation_row = {
        "mean_ic": result.pooled_ic.get("mean_ic"),
        "ic_t_stat": result.pooled_ic.get("t_stat"),
        "train_mean_ic": result.stability("train_mean_ic").get("mean"),
        "train_ic_gap": _gap_of(result),
        "fold_ic_positive_rate": result.stability("spearman").get("fold_positive_rate"),
    }

    for field, value in ablation_row.items():
        assert value is not None, f"{field} is None — the ablation would report a blank"
        assert value == pytest.approx(leader[field]), (
            f"{field}: ablation {value} != leaderboard {leader[field]}"
        )
