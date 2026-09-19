"""EXP-010B: calendar schedules, alignment, identical inputs, pairing, holdout and the gate."""

import json
import subprocess
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.quant.backtest.engine import run_backtest
from src.quant.pit.calendar import TradingCalendar
from src.quant.study import exp009a, exp009b, exp010a, exp010b as B, prereg
from src.quant.study.firewall import FIREWALL, HoldoutBreach, reset_for_tests

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def clean_firewall():
    reset_for_tests()
    yield
    reset_for_tests()


def world(n_sessions: int = 520, n_symbols: int = 40, seed: int = 0, drop: dict | None = None):
    """A synthetic calendar, a 5-session prediction grid, and a daily returns panel."""
    rng = np.random.default_rng(seed)
    sessions = [d.date() for d in pd.bdate_range("2020-01-01", periods=n_sessions)]
    calendar = TradingCalendar.from_dates(sessions)
    first_pos = 10
    grid_pos = list(range(first_pos, n_sessions - 30, 5))
    first, last = sessions[first_pos], sessions[grid_pos[-1]]
    symbols = [f"S{i:03d}" for i in range(n_symbols)]
    grid = pd.DataFrame([(sessions[p], s, rng.normal()) for p in grid_pos for s in symbols],
                        columns=["date", "symbol", "prediction"])
    days = pd.to_datetime(sessions[: grid_pos[-1] + 1])
    daily = pd.DataFrame([(d, s) for d in days for s in symbols], columns=["date", "symbol"])
    daily["dollar_volume"] = 5e7
    daily["fwd_ret_5"] = rng.normal(0, 0.02, len(daily))
    daily["fwd_ret_21"] = rng.normal(0, 0.04, len(daily))
    daily["in_universe"] = True
    if drop:
        for symbol, positions in drop.items():
            gone = pd.to_datetime([sessions[p] for p in positions])
            daily = daily[~((daily["symbol"] == symbol) & daily["date"].isin(gone))]
            grid = grid[~((grid["symbol"] == symbol) & grid["date"].isin([d.date() for d in gone]))]
    return calendar, grid.reset_index(drop=True), daily.reset_index(drop=True), first, last


# ── definition ──────────────────────────────────────────────────────────────

def test_definition_registers_two_arms_ten_seeds_and_no_sweep():
    assert set(B.ARMS) == {"B0", "B1"}
    assert B.ARMS["B0"]["step_sessions"] == 5 and B.ARMS["B1"]["step_sessions"] == 21
    assert B.SEEDS == tuple(range(10)) and len(B.DEFINITION["inputs"]["prediction_sha256_by_seed"]) == 10
    assert B.COSTS == (1.0, 3.0, 5.0, 10.0, 20.0) and B.PRIMARY_BPS == 10.0
    assert B.DEFINITION["holdout"]["touched"] is False
    assert "no 10/15/20/22/42" in B.DEFINITION["no_sweep"]
    assert B.DEFINITION["inputs"]["retraining"] == "none"


def test_registered_parent_hashes_equal_the_committed_exp010a_artifacts():
    committed = json.loads((REPO / "experiments/EXP-010A/prediction_hashes.json").read_text())
    assert {str(k): v for k, v in B.PARENT_PREDICTION_SHA256.items()} == committed
    check = B.verify_parent_artifacts(REPO)
    assert check["passed"], check["checks"]


# ── calendar schedules ──────────────────────────────────────────────────────

def test_five_session_schedule_is_every_fifth_calendar_session():
    calendar, _, _, first, last = world()
    schedule = B.rebalance_schedule(calendar, 5, first_prediction=first, last_prediction=last)
    positions = [calendar.index_of(d) for d in schedule]
    assert positions[0] == calendar.index_of(first) + 5
    assert {b - a for a, b in zip(positions, positions[1:])} == {5}
    assert schedule[-1] <= last < calendar.sessions[positions[-1] + 5]


def test_twenty_one_session_schedule_is_every_21st_calendar_session():
    calendar, _, _, first, last = world()
    schedule = B.rebalance_schedule(calendar, 21, first_prediction=first, last_prediction=last)
    positions = [calendar.index_of(d) for d in schedule]
    assert positions[0] == calendar.index_of(first) + 5
    assert {b - a for a, b in zip(positions, positions[1:])} == {21}
    assert schedule[-1] <= last < calendar.sessions[positions[-1] + 21]
    # not month ends and not four-week jumps: calendar-day gaps vary with holidays/weekends
    assert not all(d == (pd.Timestamp(d) + pd.offsets.BMonthEnd(0)).date() for d in schedule)


def test_both_arms_start_on_the_same_first_rebalance():
    calendar, _, _, first, last = world()
    b0 = B.rebalance_schedule(calendar, 5, first_prediction=first, last_prediction=last)
    b1 = B.rebalance_schedule(calendar, 21, first_prediction=first, last_prediction=last)
    assert b0[0] == b1[0] and set(b1) <= set(b0) | set(calendar.sessions)


def test_schedule_is_global_and_ignores_which_symbols_have_rows():
    calendar, grid, daily, first, last = world()
    thin, _, thin_daily, _, _ = world(drop={"S001": list(range(50, 400)), "S002": list(range(0, 520, 3))})
    before = {s: B.rebalance_schedule(calendar, s, first_prediction=first, last_prediction=last) for s in (5, 21)}
    universe = daily[daily["in_universe"]]
    thin_universe = thin_daily[thin_daily["in_universe"]]
    for step in (5, 21):
        a = B.align_signals(grid, universe, calendar, before[step])
        b = B.align_signals(grid, thin_universe, calendar, before[step])
        assert set(a["date"]) <= {pd.Timestamp(d) for d in before[step]} and set(b["date"]) <= {pd.Timestamp(d) for d in before[step]}
    assert before[21] == B.rebalance_schedule(calendar, 21, first_prediction=first, last_prediction=last)


def test_a_missing_symbol_never_shifts_the_schedule_or_other_names():
    calendar, grid, daily, first, last = world()
    schedule = B.rebalance_schedule(calendar, 21, first_prediction=first, last_prediction=last)
    full = B.align_signals(grid, daily, calendar, schedule)
    _, grid_thin, daily_thin, _, _ = world(drop={"S007": list(range(0, 520))})
    thin = B.align_signals(grid_thin, daily_thin, calendar, schedule)
    assert sorted(set(full["date"])) == sorted(set(thin["date"]))
    others = full[full["symbol"] != "S007"].reset_index(drop=True)
    pd.testing.assert_frame_equal(others, thin.reset_index(drop=True))


def test_no_symbol_based_drift_for_a_sparse_name():
    calendar, grid, daily, first, last = world()
    _, sparse_grid, sparse_daily, _, _ = world(drop={"S003": [p for p in range(520) if p % 7 == 0]})
    schedule = B.rebalance_schedule(calendar, 5, first_prediction=first, last_prediction=last)
    aligned = B.align_signals(sparse_grid, sparse_daily, calendar, schedule)
    assert set(aligned["date"]) <= {pd.Timestamp(d) for d in schedule}
    assert (aligned["signal_age_sessions"] >= B.INFORMATION_DELAY_SESSIONS).all()


# ── alignment ───────────────────────────────────────────────────────────────

def test_signal_is_the_latest_prediction_at_least_five_sessions_old():
    calendar, grid, daily, first, last = world()
    schedule = B.rebalance_schedule(calendar, 21, first_prediction=first, last_prediction=last)
    aligned = B.align_signals(grid, daily, calendar, schedule)
    source = grid.assign(date=pd.to_datetime(grid["date"])).set_index(["date", "symbol"])["prediction"]
    used = aligned.set_index(["signal_date", "symbol"])["prediction"]
    np.testing.assert_array_equal(used.to_numpy(), source.reindex(used.index).to_numpy())
    assert aligned["signal_age_sessions"].between(5, 9).all()          # grid is 5 sessions: age is 5..9
    b0 = B.align_signals(grid, daily, calendar, B.rebalance_schedule(calendar, 5, first_prediction=first, last_prediction=last))
    assert (b0["signal_age_sessions"] == 5).all()


def test_a_returning_name_uses_its_latest_older_signal_like_the_engine_lag():
    calendar, grid, daily, first, last = world(drop={"S010": list(range(15, 80))})
    schedule = B.rebalance_schedule(calendar, 5, first_prediction=first, last_prediction=last)
    aligned = B.align_signals(grid, daily, calendar, schedule)
    reentry = aligned[(aligned["symbol"] == "S010") & (aligned["date"] >= pd.Timestamp(calendar.sessions[80]))].iloc[0]
    assert reentry["date"] == pd.Timestamp(calendar.sessions[80])
    assert reentry["signal_age_sessions"] == 70  # last scored at position 10: stale, and reported rather than hidden
    assert not ((aligned["symbol"] == "S010") & aligned["date"].between(pd.Timestamp(calendar.sessions[15]), pd.Timestamp(calendar.sessions[79]))).any()


def test_b0_through_the_alignment_equals_the_engine_one_period_lag():
    calendar, grid, daily, first, last = world()
    schedule = B.rebalance_schedule(calendar, 5, first_prediction=first, last_prediction=last)
    aligned = B.align_signals(grid, daily, calendar, schedule)
    result, _, _ = B.run_arm(aligned, daily, "B0", 10.0)
    panel = daily.assign(date=daily["date"].dt.date)[["date", "symbol", "dollar_volume", "fwd_ret_5"]]
    engine = run_backtest(grid[["date", "symbol", "prediction"]], panel, config=exp009a._backtest.__globals__["BacktestConfig"](
        rebalance_step_sessions=5, execution_lag_periods=1,
        cost_model=B.arm_config("B0", 10.0).cost_model, weight_rule=B.arm_config("B0", 10.0).weight_rule),
        forward_return_column="fwd_ret_5")
    for key in ("gross_sharpe", "net_sharpe", "annualised_turnover", "net_max_drawdown"):
        assert result.metrics[key] == pytest.approx(engine.metrics[key], abs=1e-12)


def test_both_arms_are_fed_from_the_same_prediction_frame():
    calendar, grid, daily, first, last = world()
    frames = {arm: B.align_signals(grid, daily, calendar, B.rebalance_schedule(calendar, spec["step_sessions"], first_prediction=first, last_prediction=last))
              for arm, spec in B.ARMS.items()}
    source = set(zip(pd.to_datetime(grid["date"]), grid["symbol"], grid["prediction"]))
    for frame in frames.values():
        assert set(zip(frame["signal_date"], frame["symbol"], frame["prediction"])) <= source


def test_portfolio_configuration_differs_only_in_cadence():
    b0, b1 = B.arm_config("B0", 10.0).as_dict(), B.arm_config("B1", 10.0).as_dict()
    differing = {k for k in b0 if b0[k] != b1[k]}
    assert differing == {"rebalance_step_sessions"}
    assert b0["execution_lag_periods"] == b1["execution_lag_periods"] == 0
    assert set(B.ARMS["B0"]) == set(B.ARMS["B1"]) == {"step_sessions", "forward_return_column"}
    assert B.arm_config("B0", 10.0).weight_rule.__class__ is B.arm_config("B1", 10.0).weight_rule.__class__


# ── arm reports and pairing ─────────────────────────────────────────────────

def _reports(world_args=None):
    calendar, grid, daily, first, last = world(**(world_args or {}))
    fold_by_grid = {d: int(i // 12) for i, d in enumerate(sorted(grid["date"].unique()))}
    out = {}
    for arm, spec in B.ARMS.items():
        schedule = B.rebalance_schedule(calendar, spec["step_sessions"], first_prediction=first, last_prediction=last)
        aligned = B.align_signals(grid, daily, calendar, schedule)
        out[arm] = B.arm_report(0, arm, aligned, daily, fold_by_grid)
    return out


def test_arm_reports_carry_the_requested_metrics_and_are_deterministic():
    one, two = _reports(), _reports()
    for arm in B.ARMS:
        report = one[arm][0]
        assert "cost_share_of_gross" in report  # undefined (None) when random synthetic gross return is not positive
        for key in ("gross_sharpe", "net_sharpe_10bp", "annualised_turnover", "net_max_drawdown",
                    "holding_duration_sessions", "names_changed_per_rebalance", "rebalances", "gross_total_return",
                    "net_total_return", "long_leg_retention", "short_leg_retention", "effective_n_long"):
            assert report[key] is not None, key
        assert set(report["costs"]) == {"1bp", "3bp", "5bp", "10bp", "20bp"}
        assert one[arm][0] == two[arm][0]
        pd.testing.assert_frame_equal(one[arm][2], two[arm][2])
    assert one["B1"][0]["rebalances"] < one["B0"][0]["rebalances"]
    assert one["B1"][0]["annualised_turnover"] < one["B0"][0]["annualised_turnover"]


def test_annualisation_follows_the_cadence():
    reports = _reports()
    assert reports["B0"][2].shape[0] > reports["B1"][2].shape[0]
    calendar, grid, daily, first, last = world()
    schedule = B.rebalance_schedule(calendar, 21, first_prediction=first, last_prediction=last)
    result, _, _ = B.run_arm(B.align_signals(grid, daily, calendar, schedule), daily, "B1", 10.0)
    assert result.metrics["periods_per_year"] == pytest.approx(252 / 21)


def test_paired_differences_are_b1_minus_b0_for_every_seed():
    def make(arm, offset):
        return [{"seed": s, "arm": arm, "net_sharpe_10bp": 0.3 + s * 0.01 + offset, "annualised_turnover": 6.9 - offset * 4,
                 "gross_sharpe": 0.5 + offset, "net_max_drawdown": -0.13 + offset, "cost_share_of_gross": 0.27 - offset,
                 "costs": {}, "step_sessions": 5} for s in B.SEEDS]
    b0, b1 = make("B0", 0.0), make("B1", 0.2)
    rows = B.paired_rows(b0, b1)
    net = [r for r in rows if r["metric"] == "net_sharpe_10bp"]
    assert [r["seed"] for r in net] == list(range(10))
    assert all(r["difference_b1_minus_b0"] == pytest.approx(0.2) for r in net)
    summary = B.paired_summary(rows)["net_sharpe_10bp"]
    assert summary["seeds"] == 10 and summary["seeds_positive"] == 10
    assert set(summary) >= {"mean", "median", "sample_std", "min", "max", "p05", "p95"}
    assert summary["sample_std"] == pytest.approx(0.0, abs=1e-12)
    turnover = B.paired_summary(rows)["annualised_turnover"]
    assert turnover["median"] == pytest.approx(-0.8) and turnover["relative_change_median"] == pytest.approx(-0.8 / 6.9)


def test_pairing_refuses_a_missing_or_reordered_seed():
    rows = [{"seed": s, "arm": "B0", "gross_sharpe": 0.5, "costs": {}, "step_sessions": 5} for s in B.SEEDS]
    with pytest.raises(ValueError, match="all ten seeds"):
        B.paired_rows(rows[:9], rows)
    with pytest.raises(ValueError, match="all ten seeds"):
        B.paired_rows(rows, rows[::-1])


def test_distribution_matches_numpy_and_uses_sample_std():
    values = np.arange(10, dtype=float)
    out = B.distribution(values)
    assert out["sample_std"] == pytest.approx(np.std(values, ddof=1)) and out["median"] == 4.5
    assert out["p05"] == pytest.approx(np.quantile(values, 0.05)) and out["p95"] == pytest.approx(np.quantile(values, 0.95))


def test_pooled_sharpe_helper_matches_the_engine_definition():
    calendar, grid, daily, first, last = world()
    schedule = B.rebalance_schedule(calendar, 5, first_prediction=first, last_prediction=last)
    result, _, _ = B.run_arm(B.align_signals(grid, daily, calendar, schedule), daily, "B0", 10.0)
    assert B._sharpe(result.periods["net_return"].to_numpy(), 252 / 5) == pytest.approx(result.metrics["net_sharpe"])


# ── interpretation ──────────────────────────────────────────────────────────

def _summary(turnover_rel, turnover_neg, net_median, net_pos, gross_median):
    return {
        "annualised_turnover": {"relative_change_median": turnover_rel, "seeds_negative": turnover_neg},
        "net_sharpe_10bp": {"median": net_median, "seeds_positive": net_pos},
        "gross_sharpe": {"median": gross_median},
    }


def _lofo(value):
    return [{"fold_removed": i, "median_difference": value} for i in range(8)]


@pytest.mark.parametrize("summary,lofo,label", [
    (_summary(-0.6, 10, 0.30, 10, 0.2), _lofo(0.2), "ECONOMICALLY_IMPROVED"),
    (_summary(-0.6, 10, 0.30, 10, 0.2), _lofo(0.2)[:7] + [{"fold_removed": 7, "median_difference": -0.01}], "NO_STABLE_ECONOMIC_GAIN"),
    (_summary(-0.6, 10, 0.0, 5, -0.2), _lofo(-0.02), "ECONOMICALLY_IMPROVED"),
    (_summary(-0.6, 10, -0.2, 1, -0.3), _lofo(-0.2), "TURNOVER_REDUCED_SIGNAL_LOST"),
    (_summary(-0.05, 6, 0.01, 6, 0.0), _lofo(0.0), "CADENCE_EQUIVALENT"),
    (_summary(-0.05, 6, -0.2, 2, -0.2), _lofo(-0.2), "NO_STABLE_ECONOMIC_GAIN"),
    (_summary(-0.6, 9, 0.30, 10, 0.2), _lofo(0.2), "NO_STABLE_ECONOMIC_GAIN"),  # turnover not lower in all ten seeds
])
def test_classification_follows_the_preregistered_rules(summary, lofo, label):
    assert B.classify(summary, lofo)["label"] == label


def test_classification_never_promotes_or_selects_a_seed():
    out = B.classify(_summary(-0.6, 10, 0.3, 10, 0.2), _lofo(0.2))
    assert out["promotion"] == "NOT ASSESSED" and out["best_seed_selected"] is False


def test_parent_reproduction_check_detects_a_change():
    parent = json.loads((REPO / "experiments/EXP-010A/metrics.json").read_text())["per_seed"]
    reports = [{"seed": r["seed"], "arm": "B0", "costs": {k: dict(v) for k, v in r["costs"].items()}} for r in parent]
    assert B.check_b0_reproduces_parent(reports, REPO)["passed"]
    reports[3]["costs"]["10bp"]["net_sharpe"] += 1e-6
    bad = B.check_b0_reproduces_parent(reports, REPO)
    assert not bad["passed"] and bad["failures"][0]["seed"] == 3


# ── holdout ─────────────────────────────────────────────────────────────────

def test_holdout_dates_are_rejected_once_the_firewall_is_armed():
    exp009b.arm_firewall(REPO)
    frame = pd.DataFrame({"date": [date(2025, 9, 2)], "symbol": ["AAA"]})
    with pytest.raises(HoldoutBreach):
        FIREWALL.assert_clear(frame, context="test")
    assert B.LAST_PREDICTION_DATE < exp009b.holdout_window(REPO)[0]


def test_the_daily_panel_builder_refuses_a_cap_inside_the_holdout(monkeypatch, tmp_path):
    monkeypatch.setattr(B, "LAST_PREDICTION_DATE", date(2025, 9, 2))
    with pytest.raises(HoldoutBreach):
        B.build_daily_panel(REPO)


def test_holdout_guard_reports_sealed_and_refuses_an_unsealed_state(monkeypatch):
    guard = B.holdout_guard(REPO)
    assert guard["touched"] is False and guard["firewall"]["holdout_state"] == "SEALED"
    monkeypatch.setattr(FIREWALL, "status", lambda: {"holdout_state": "UNSEALED_OVERRIDE"})
    with pytest.raises(HoldoutBreach):
        B.holdout_guard(REPO)


def test_a_tampered_prediction_file_is_refused(tmp_path):
    target = tmp_path / B.PARENT_DIR / "checkpoints"
    target.mkdir(parents=True)
    frame = pd.DataFrame({"date": [date(2024, 1, 2)], "symbol": ["A"], "fold": [0], exp010a.LABEL: [0.1], "prediction": [0.2]})
    frame.to_parquet(target / "seed_00_predictions.parquet")
    with pytest.raises(RuntimeError, match="registered"):
        B.load_seed_predictions(0, tmp_path)
    with pytest.raises(FileNotFoundError, match="never refits"):
        B.load_seed_predictions(1, tmp_path)


# ── the pipeline, on synthetic inputs only ──────────────────────────────────

def _synthetic_study(monkeypatch, tmp_path):
    calendar, grid, daily, first, last = world(n_sessions=620, n_symbols=40)
    dates = sorted(grid["date"].unique())
    fold_of = {d: min(i * 8 // len(dates), 7) for i, d in enumerate(dates)}

    def seed_predictions(seed, root=Path(".")):
        rng = np.random.default_rng(100 + seed)
        frame = grid.copy()
        frame["prediction"] = rng.normal(size=len(frame))
        frame["fold"] = frame["date"].map(fold_of)
        frame[exp010a.LABEL] = rng.uniform(size=len(frame))
        return frame

    schedules = {a: B.rebalance_schedule(calendar, s["step_sessions"], first_prediction=first, last_prediction=last)
                 for a, s in B.ARMS.items()}
    monkeypatch.setattr(B, "FIRST_PREDICTION_DATE", first)
    monkeypatch.setattr(B, "LAST_PREDICTION_DATE", last)
    monkeypatch.setattr(B, "EXPECTED_REBALANCES", {a: len(s) for a, s in schedules.items()})
    monkeypatch.setattr(B, "prereg_gate", lambda *a, **k: {"preregistration_document": "synthetic", "preregistration_sha256": "0" * 64})
    monkeypatch.setattr(B, "verify_parent_artifacts", lambda *a, **k: {"passed": True, "checks": {}})
    monkeypatch.setattr(B, "build_daily_panel", lambda *a, **k: (daily, calendar))
    monkeypatch.setattr(B, "verify_panel", lambda *a, **k: {"passed": True, "checks": {}})
    monkeypatch.setattr(B, "load_seed_predictions", seed_predictions)
    monkeypatch.setattr(B, "check_b0_reproduces_parent", lambda *a, **k: {"passed": True, "max_abs_gap": 0.0, "tolerance": 1e-9, "failures": []})
    return tmp_path / "out"


def test_the_whole_pipeline_runs_on_synthetic_inputs_and_writes_every_output(monkeypatch, tmp_path):
    out = _synthetic_study(monkeypatch, tmp_path)
    result = B.run_study(REPO, output=out)
    assert sorted(p.name for p in out.iterdir()) == sorted(B.DEFINITION["outputs"])
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["holdout"]["touched"] is False and manifest["holdout"]["firewall"]["holdout_state"] == "SEALED"
    assert manifest["seeds"] == list(range(10)) and manifest["retraining"] is False and manifest["parameter_sweep"] is False
    assert manifest["best_seed_selected"] is False and manifest["completion"] == "COMPLETE"
    per_seed = pd.read_csv(out / "per_seed_cadence.csv")
    assert sorted(per_seed["seed"].unique()) == list(range(10)) and set(per_seed["arm"]) == {"B0", "B1"} and len(per_seed) == 20
    paired = pd.read_csv(out / "paired_differences.csv")
    assert set(paired["seed"]) == set(range(10))
    net = paired[paired["metric"] == "net_sharpe_10bp"]
    assert (net["difference_b1_minus_b0"] - (net["b1"] - net["b0"])).abs().max() < 1e-12
    folds = pd.read_csv(out / "fold_cadence.csv")
    assert set(folds["fold"]) == set(range(8)) and set(folds["arm"]) == {"B0", "B1"}
    metrics = json.loads((out / "metrics.json").read_text())
    assert metrics["classification"]["label"] in B.INTERPRETATION["labels"]
    assert len(metrics["leave_one_fold_out"]) == 8 and result["classification"]["promotion"] == "NOT ASSESSED"


def test_the_pipeline_output_is_deterministic(monkeypatch, tmp_path):
    first = _synthetic_study(monkeypatch, tmp_path / "a")
    B.run_study(REPO, output=first)
    second = _synthetic_study(monkeypatch, tmp_path / "b")
    B.run_study(REPO, output=second)
    for name in ("per_seed_cadence.csv", "fold_cadence.csv", "paired_differences.csv", "metrics.json", "config.json", "definition.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


# ── the gate ────────────────────────────────────────────────────────────────

def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
                        "PATH": __import__("os").environ["PATH"], "HOME": str(cwd)})


@pytest.fixture
def sandbox(tmp_path):
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    remote.mkdir(); work.mkdir()
    _git(remote, "init", "--bare", "-b", "main")
    _git(work, "init", "-b", "main")
    _git(work, "remote", "add", "origin", str(remote))
    for name in B.METHOD_SOURCES:
        target = work / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((REPO / name).read_text())
    (work / "docs").mkdir()
    return work


def test_the_gate_refuses_unregistered_unpushed_and_changed_studies(sandbox):
    with pytest.raises(prereg.PreregistrationError, match="does not exist"):
        B.prereg_gate(sandbox)
    fingerprint = B.definition_fingerprint(sandbox)
    (sandbox / B.PREREG_DOC).write_text(f"# prereg\n\nDefinition fingerprint: `{fingerprint}`\n")
    _git(sandbox, "add", "-A"); _git(sandbox, "commit", "-m", "prereg")
    with pytest.raises(prereg.PreregistrationError, match="origin/main"):
        B.prereg_gate(sandbox)
    _git(sandbox, "push", "origin", "main")
    assert B.prereg_gate(sandbox)["pushed_to_origin_main"]
    target = sandbox / "src/quant/backtest/rules.py"
    target.write_text(target.read_text() + "\n# tweak after registration\n")
    with pytest.raises(prereg.PreregistrationError):
        B.prereg_gate(sandbox)


def test_run_calls_the_gate_before_any_data_is_read(sandbox, monkeypatch):
    touched = []
    monkeypatch.setattr(B, "build_daily_panel", lambda *a, **k: touched.append("panel"))
    monkeypatch.setattr(B, "load_seed_predictions", lambda *a, **k: touched.append("predictions"))
    with pytest.raises(prereg.PreregistrationError):
        B.run_study(sandbox)
    assert touched == []


def test_committed_preregistration_embeds_the_current_fingerprint():
    document = REPO / B.PREREG_DOC
    if not document.exists():
        pytest.skip("preregistration not written yet")
    assert f"Definition fingerprint: `{B.definition_fingerprint(REPO)}`" in document.read_text()
