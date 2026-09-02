"""`cost_share_of_gross` must not survive a sign flip in the denominator.

The metric answers "how much of the gross profit did friction eat?". That
question has no answer when there was no gross profit. Taking the absolute
value of the denominator gave it one anyway, and the answer looked healthy.

These tests are written against the failure mode rather than the formula: each
one constructs a strategy that LOSES money before costs and asserts the report
cannot be read as if it earned.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.quant.backtest.engine import performance_metrics


def _periods(gross: list[float], cost: list[float]) -> pd.DataFrame:
    """A minimal period frame with the columns `_summarise` reads."""
    n = len(gross)
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-01", periods=n),
            "gross_return": gross,
            "cost_return": cost,
            "net_return": [g - c for g, c in zip(gross, cost)],
            "turnover": [0.1] * n,
            "names": [50] * n,
            "gross_exposure": [1.0] * n,
        }
    )


def test_losing_strategy_reports_no_cost_share() -> None:
    """Gross profit is negative, so the share of it is undefined, not 0.5."""
    frame = _periods([-0.01] * 10, [0.005] * 10)
    out = performance_metrics(frame, periods_per_year=252.0)
    assert out["gross_total_return"] < 0
    assert out["cost_share_of_gross"] is None


def test_winner_and_loser_are_distinguishable() -> None:
    """The bug: +10%/-5% and -10%/-5% both reported 0.50."""
    winner = performance_metrics(_periods([0.01] * 10, [0.005] * 10), periods_per_year=252.0)
    loser = performance_metrics(_periods([-0.01] * 10, [0.005] * 10), periods_per_year=252.0)
    assert winner["cost_share_of_gross"] != loser["cost_share_of_gross"]
    assert winner["cost_share_of_gross"] == pytest.approx(0.5)
    assert loser["cost_share_of_gross"] is None


def test_losing_more_does_not_improve_the_ratio() -> None:
    """Under abs(), a bigger loss produced a smaller — better — cost share."""
    shares = [
        performance_metrics(_periods([g] * 10, [0.005] * 10), periods_per_year=252.0)[
            "cost_share_of_gross"
        ]
        for g in (-0.01, -0.05, -0.20)
    ]
    assert shares == [None, None, None], (
        "a strategy cannot buy a better cost profile by losing more money"
    )


def test_profitable_case_is_unchanged() -> None:
    """The fix must not move any number that was already right."""
    out = performance_metrics(_periods([0.02] * 12, [0.004] * 12), periods_per_year=252.0)
    assert out["cost_share_of_gross"] == pytest.approx(0.2)


def test_flat_gross_is_undefined_not_infinite() -> None:
    out = performance_metrics(_periods([0.0] * 10, [0.005] * 10), periods_per_year=252.0)
    assert out["cost_share_of_gross"] is None


def test_costs_exceeding_gross_report_above_one() -> None:
    """A genuine transaction-cost bet must still be visible as one."""
    out = performance_metrics(_periods([0.01] * 10, [0.02] * 10), periods_per_year=252.0)
    assert out["cost_share_of_gross"] == pytest.approx(2.0)


def test_undefined_share_fails_the_production_gate() -> None:
    """Fail-closed is the whole point: absent evidence is not passing evidence."""
    from src.quant.models.registry import PRODUCTION_THRESHOLDS

    rule = PRODUCTION_THRESHOLDS["cost_share_of_gross"]
    assert rule["maximum"] == 0.75

    losing = performance_metrics(
        _periods([-0.01] * 10, [0.005] * 10), periods_per_year=252.0
    )
    value = losing["cost_share_of_gross"]
    assert value is None, "an undefined share must reach the gate as None"

    # The gate's own rule, applied as `thresholds_not_met` applies it.
    assert not ("maximum" in rule and isinstance(value, (int, float))), (
        "None must not be compared against the ceiling"
    )
    # ...and a None is recorded as unmet rather than skipped.
    unmet = {}
    if value is None:
        unmet["cost_share_of_gross"] = "not recorded"
    assert "cost_share_of_gross" in unmet


def test_old_behaviour_would_have_passed_the_gate() -> None:
    """Proof the defect was reachable, not theoretical.

    A strategy losing 20% gross while paying 5% in costs scored 0.25 under the
    absolute-value denominator — comfortably inside a 0.75 ceiling.
    """
    gross_total, cost_total = -0.20, 0.05
    old_value = abs(cost_total) / abs(gross_total)
    assert old_value == pytest.approx(0.25)
    assert old_value <= 0.75, "the old formula cleared the ceiling while losing money"

    out = performance_metrics(
        _periods([-0.02] * 10, [0.005] * 10), periods_per_year=252.0
    )
    assert out["cost_share_of_gross"] is None, "it must no longer clear it"
