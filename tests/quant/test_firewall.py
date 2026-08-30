"""
Holdout firewall — proving the lock is real.

A guard that has never been shown to fire is a comment. Every test here plants
a breach and asserts the refusal, then asserts the complement: that ordinary
pre-holdout work is untouched. A firewall that blocks everything would pass the
first half and be useless.
"""

from __future__ import annotations

from datetime import date as Date

import numpy as np
import pandas as pd
import pytest

from src.quant.study.firewall import (
    FIREWALL,
    HoldoutBreach,
    HoldoutFirewall,
    HoldoutWindow,
    reset_for_tests,
)


@pytest.fixture(autouse=True)
def _clean():
    reset_for_tests()
    yield
    reset_for_tests()


def _frame(dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame({
        "date": [Date.fromisoformat(d) for d in dates],
        "symbol": ["AAA"] * len(dates),
        "value": np.arange(len(dates), dtype=float),
    })


# ── the guard fires ─────────────────────────────────────────────────────────


def test_a_single_holdout_row_is_refused():
    """One row is a breach. There is no tolerance threshold."""
    FIREWALL.arm_window(Date(2025, 9, 1), Date(2026, 8, 31))
    frame = _frame(["2025-01-02", "2025-06-30", "2025-09-02"])
    with pytest.raises(HoldoutBreach, match="1 row"):
        FIREWALL.assert_clear(frame, context="unit test")


def test_the_refusal_names_the_stage_and_the_dates():
    FIREWALL.arm_window(Date(2025, 9, 1), Date(2026, 8, 31))
    frame = _frame(["2025-09-02", "2026-01-15"])
    with pytest.raises(HoldoutBreach) as excinfo:
        FIREWALL.assert_clear(frame, context="fold 7 TRAIN")
    message = str(excinfo.value)
    assert "fold 7 TRAIN" in message
    assert "2025-09-02" in message and "2026-01-15" in message
    assert "single-use" in message


def test_boundary_dates_are_inside_the_holdout():
    """Inclusive on both ends — an off-by-one here spends a day of the holdout."""
    FIREWALL.arm_window(Date(2025, 9, 1), Date(2026, 8, 31))
    for edge in ("2025-09-01", "2026-08-31"):
        with pytest.raises(HoldoutBreach):
            FIREWALL.assert_clear(_frame([edge]), context="boundary")


def test_the_day_before_and_after_are_clear():
    FIREWALL.arm_window(Date(2025, 9, 1), Date(2026, 8, 31))
    FIREWALL.assert_clear(_frame(["2025-08-31"]), context="before")
    FIREWALL.assert_clear(_frame(["2026-09-01"]), context="after")


def test_ordinary_pre_holdout_work_is_untouched():
    """The complement: a firewall that blocks everything is not a firewall."""
    FIREWALL.arm_window(Date(2025, 9, 1), Date(2026, 8, 31))
    FIREWALL.assert_clear(
        _frame(["2020-01-02", "2022-06-30", "2025-08-29"]), context="development"
    )
    assert FIREWALL.breaches_prevented == 0


# ── it cannot be opened casually ────────────────────────────────────────────


def test_there_is_no_environment_override(monkeypatch):
    """Setting a hopeful variable must error, not silently do nothing."""
    from src.quant.study import firewall as module

    monkeypatch.setenv("QUANT_DISABLE_HOLDOUT_FIREWALL", "1")
    with pytest.raises(RuntimeError, match="no environment override"):
        module._env_override_is_refused()


def test_an_override_requires_a_reason():
    FIREWALL.arm_window(Date(2025, 9, 1), Date(2026, 8, 31))
    with pytest.raises(ValueError, match="needs a reason"):
        with FIREWALL.override(""):
            pass


def test_an_override_lifts_the_guard_and_then_restores_it():
    FIREWALL.arm_window(Date(2025, 9, 1), Date(2026, 8, 31))
    frame = _frame(["2025-09-02"])

    with FIREWALL.override("the pre-registered holdout run"):
        FIREWALL.assert_clear(frame, context="sanctioned")

    with pytest.raises(HoldoutBreach):
        FIREWALL.assert_clear(frame, context="after the override")


def test_an_unarmed_contract_keeps_the_firewall_engaged(tmp_path):
    guard = HoldoutFirewall(contract_path=tmp_path / "CONTRACT.md")
    (tmp_path / "CONTRACT.md").write_text("| Armed | **NO** |", encoding="utf-8")
    guard.arm_window(Date(2025, 9, 1), Date(2026, 8, 31))
    assert not guard.contract_armed()
    assert guard.engaged
    with pytest.raises(HoldoutBreach):
        guard.assert_clear(_frame(["2025-09-02"]), context="unarmed")


def test_an_armed_contract_lifts_it(tmp_path):
    guard = HoldoutFirewall(contract_path=tmp_path / "CONTRACT.md")
    (tmp_path / "CONTRACT.md").write_text("| Armed | **YES** |", encoding="utf-8")
    guard.arm_window(Date(2025, 9, 1), Date(2026, 8, 31))
    assert guard.contract_armed()
    assert not guard.engaged
    guard.assert_clear(_frame(["2025-09-02"]), context="armed")


def test_a_missing_contract_is_treated_as_unarmed(tmp_path):
    """Absence must fail closed."""
    guard = HoldoutFirewall(contract_path=tmp_path / "does-not-exist.md")
    assert not guard.contract_armed()
    assert guard.engaged


# ── the repository's real contract ──────────────────────────────────────────


def test_the_repository_contract_is_not_armed():
    """The standing state of this project. If this fails, something armed it."""
    guard = HoldoutFirewall()
    assert not guard.contract_armed(), (
        "docs/HOLDOUT_CONTRACT.md is ARMED — the holdout is open"
    )


# ── integration: the plan arms the window ───────────────────────────────────


def test_building_a_plan_arms_the_window():
    from src.quant.pit.calendar import TradingCalendar
    from src.quant.validation.walkforward import build_plan

    sessions = pd.bdate_range("2018-01-01", "2026-08-28").date.tolist()
    calendar = TradingCalendar(sessions=list(sessions))
    build_plan(calendar, start=sessions[0], end=sessions[-1],
               min_train_sessions=756, validation_sessions=252,
               holdout_sessions=252, label_horizon_sessions=21, embargo_sessions=5)

    assert FIREWALL.window.active
    assert FIREWALL.window.end == sessions[-1]
    assert FIREWALL.window.start == sessions[-252]


def test_a_fold_reaching_the_holdout_is_refused_at_fit_time():
    """The end-to-end assertion: a wrong plan cannot reach a fit.

    The plan is built correctly and then deliberately corrupted, which is the
    only way to simulate the bug this guard exists for — a planner change that
    lets a validation window slide into the reserved period.
    """
    from dataclasses import replace

    from src.quant.models.baselines import ZeroBaseline
    from src.quant.pit.calendar import TradingCalendar
    from src.quant.validation.runner import run_walk_forward
    from src.quant.validation.walkforward import build_plan

    sessions = pd.bdate_range("2018-01-01", "2026-08-28").date.tolist()
    calendar = TradingCalendar(sessions=list(sessions))
    plan = build_plan(calendar, start=sessions[0], end=sessions[-1],
                      min_train_sessions=756, validation_sessions=252,
                      holdout_sessions=252, label_horizon_sessions=21,
                      embargo_sessions=5)

    last = plan.folds[-1]
    corrupted = replace(last, validation_end=sessions[-1])  # slides into the holdout
    plan.folds[-1] = corrupted

    frame = pd.DataFrame({
        "date": sessions,
        "symbol": "AAA",
        "feature": np.linspace(0.0, 1.0, len(sessions)),
        "fwd_ret_21": np.linspace(0.0, 0.1, len(sessions)),
        "in_universe": True,
    })

    with pytest.raises(HoldoutBreach, match="VALIDATION"):
        run_walk_forward(
            ZeroBaseline, frame, plan, features=["feature"], label="fwd_ret_21",
            step_sessions=1,
        )


# ── status reporting ────────────────────────────────────────────────────────


def test_status_reports_the_lock_for_the_ui():
    FIREWALL.arm_window(Date(2025, 9, 1), Date(2026, 8, 31))
    status = FIREWALL.status()
    assert status["window"]["active"] is True
    assert status["contract_armed"] is False
    assert status["engaged"] is True
    assert status["window"]["start"] == "2025-09-01"
