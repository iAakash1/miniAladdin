"""Reported turnover and the reported cost rate must reconcile.

Both formulas were individually defensible. Costs are charged on the
round-trip notional `sum|dw|`, which is right — replacing a 100%-gross book end
to end really does trade 200% of capital. Turnover was reported one-way,
`sum|dw|/2`, which is also a standard convention. Neither is wrong.

The interface was. A reader multiplying the displayed turnover by the displayed
bps got exactly half the cost actually charged, with nothing on any surface
saying the two numbers sit on different bases.

These tests pin the identity rather than either convention, so a future change
to either one has to keep them reconcilable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.quant.backtest.costs import SimpleCostModel
from src.quant.backtest.engine import performance_metrics


def _full_replacement() -> pd.Series:
    """Exit two half-weight names, enter two others. sum|dw| = 2.0."""
    prev = pd.Series({"A": 0.5, "B": 0.5, "C": 0.0, "D": 0.0})
    now = pd.Series({"A": 0.0, "B": 0.0, "C": 0.5, "D": 0.5})
    return now - prev


def test_full_replacement_trades_twice_the_book() -> None:
    delta = _full_replacement()
    assert float(delta.abs().sum()) == pytest.approx(2.0)
    assert float(delta.abs().sum()) / 2.0 == pytest.approx(1.0)


def test_cost_is_charged_on_the_round_trip_notional() -> None:
    model = SimpleCostModel()
    capital = 1_000_000.0
    breakdown = model.charge(_full_replacement(), capital=capital)
    rate = model.commission_bps + model.half_spread_bps + model.slippage_bps
    assert breakdown.traded_notional == pytest.approx(2.0 * capital)
    assert breakdown.total == pytest.approx(2.0 * capital * rate / 10_000)


def test_the_declared_rate_reproduces_the_charge_on_the_declared_basis() -> None:
    """The contract, stated as an executable identity."""
    model = SimpleCostModel()
    capital = 1_000_000.0
    delta = _full_replacement()
    assumptions = model.assumptions()

    turnover_round_trip = float(delta.abs().sum())
    predicted = turnover_round_trip * assumptions["rate_bps"] / 10_000 * capital
    actual = model.charge(delta, capital=capital).total
    assert predicted == pytest.approx(actual)


def test_the_one_way_figure_alone_understates_the_cost_by_exactly_two() -> None:
    """The defect, kept as a test so it cannot come back silently."""
    model = SimpleCostModel()
    capital = 1_000_000.0
    delta = _full_replacement()
    rate = model.assumptions()["rate_bps"]

    one_way = float(delta.abs().sum()) / 2.0
    naive = one_way * rate / 10_000 * capital
    actual = model.charge(delta, capital=capital).total
    assert actual == pytest.approx(2.0 * naive)


def test_assumptions_state_the_basis_and_the_reconciliation() -> None:
    a = SimpleCostModel().assumptions()
    assert "round-trip" in a["charged_on"]
    assert "one-way" in a["turnover_convention_in_reports"]
    assert "reconciliation" in a
    assert a["rate_bps"] == pytest.approx(
        a["commission_bps"] + a["half_spread_bps"] + a["slippage_bps"]
    )


def test_slippage_is_declared_not_merely_available() -> None:
    """The parameter existed and was absent from the published assumptions."""
    assert "slippage_bps" in SimpleCostModel().assumptions()


# --- the reported aggregates -------------------------------------------------

def _periods(n: int = 12, turnover_one_way: float = 0.25) -> pd.DataFrame:
    rate = SimpleCostModel().assumptions()["rate_bps"]
    cost = 2.0 * turnover_one_way * rate / 10_000
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-01", periods=n),
            "gross_return": [0.01] * n,
            "cost_return": [cost] * n,
            "net_return": [0.01 - cost] * n,
            "turnover": [turnover_one_way] * n,
            "turnover_round_trip": [2.0 * turnover_one_way] * n,
            "names": [40] * n,
            "gross_exposure": [1.0] * n,
        }
    )


def test_report_carries_both_bases_and_names_the_convention() -> None:
    out = performance_metrics(_periods(), periods_per_year=252.0)
    assert out["turnover_convention"] == "one-way (sum|delta_w| / 2)"
    assert out["mean_turnover_round_trip"] == pytest.approx(2.0 * out["mean_turnover"])
    assert out["annualised_turnover_round_trip"] == pytest.approx(
        2.0 * out["annualised_turnover"]
    )


def test_reported_cost_rate_is_recoverable_from_the_reported_turnover() -> None:
    """End to end: the published numbers must reproduce the published rate."""
    out = performance_metrics(_periods(), periods_per_year=252.0)
    declared = SimpleCostModel().assumptions()["rate_bps"]
    assert out["cost_rate_bps_of_traded_notional"] == pytest.approx(declared, rel=1e-9)


def test_the_one_way_basis_does_not_recover_the_rate() -> None:
    """Guards the reason the round-trip figure has to be published at all."""
    out = performance_metrics(_periods(), periods_per_year=252.0)
    declared = SimpleCostModel().assumptions()["rate_bps"]
    frame = _periods()
    wrong = float(frame["cost_return"].sum() / frame["turnover"].sum() * 10_000)
    assert wrong == pytest.approx(2.0 * declared)
    assert out["cost_rate_bps_of_traded_notional"] != pytest.approx(wrong)
