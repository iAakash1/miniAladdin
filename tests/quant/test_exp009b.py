"""EXP-009B: the split is EXP-006's split, the gate holds, and the criteria mean what they say."""

import json
import subprocess
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.quant.study import exp009a
from src.quant.study import exp009b as B
from src.quant.study import prereg
from src.quant.study.firewall import FIREWALL, HoldoutBreach, reset_for_tests
from src.quant.validation.walkforward import Fold, WalkForwardPlan

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def clean_firewall():
    reset_for_tests()
    yield
    reset_for_tests()


# ── the split and the holdout ───────────────────────────────────────────────

def test_the_recorded_plan_is_exp006s_eight_folds_and_ends_before_the_holdout():
    plan = B.recorded_plan(REPO)
    assert len(plan) == 8
    assert str(plan.folds[0].validation_start) == "2017-05-05"
    assert str(plan.folds[-1].validation_end) == "2025-05-09"
    assert plan.folds[-1].validation_end < plan.holdout_start
    assert all(f.gap_sessions == 26 for f in plan.folds)


def test_the_holdout_window_is_the_widest_recorded_anywhere():
    start, end = B.holdout_window(REPO)
    assert start == date(2025, 8, 26)          # the plan's two-session-earlier start, not the contract's 08-28
    assert end == date(2026, 8, 28)


def test_the_dataset_end_and_every_fold_precede_the_window():
    start, _ = B.holdout_window(REPO)
    assert date.fromisoformat(B.DEFINITION["data"]["dataset_end"]) < start
    assert B.recorded_plan(REPO).folds[-1].validation_end < start


def test_a_frame_with_holdout_rows_is_refused():
    B.arm_firewall(REPO)
    start, _ = B.holdout_window(REPO)
    bad = pd.DataFrame({"date": [start + timedelta(days=1)], "symbol": ["A"]})
    with pytest.raises(HoldoutBreach):
        FIREWALL.assert_clear(bad, context="test")


def test_the_study_never_lifts_the_firewall_or_reads_a_holdout_plan():
    source = (REPO / "src/quant/study/exp009b.py").read_text()
    for forbidden in ("FIREWALL.override", "QUANT_ALLOW_HOLDOUT", "QUANT_DISABLE_HOLDOUT_FIREWALL", ".holdout("):
        assert forbidden not in source


def test_the_definition_freezes_the_features_and_hyperparameters():
    assert len(B.FEATURES) == 27 and len(set(B.FEATURES)) == 27
    h = B.DEFINITION["shared_hyperparameters"]
    assert (h["n_estimators"], h["learning_rate"], h["max_depth"], h["subsample"], h["min_samples_leaf"]) == (
        200, 0.03, 3, 0.7, 50)
    assert B.DEFINITION["hyperparameter_search"] == "none"
    assert B.DEFINITION["trials"]["cumulative_evaluations"] == 163
    ids = [c["id"] for c in B.DEFINITION["cells"]]
    assert ids == ["R0_sklearn_gb", "R1_boosted_l2", "R2_boosted_lambdamart", "R3_boosted_pairwise"]


def test_the_features_match_the_frozen_exp006_feature_list():
    frozen = json.loads((REPO / exp009a.FROZEN_METRICS).read_text())["features_used"]
    assert B.FEATURES == frozen


def test_every_cell_uses_identical_boosting_hyperparameters_except_the_objective():
    built = {s.name: s for s in B.specs()}
    reference = dict(built["R1_boosted_l2"].params)
    for name in ("R2_boosted_lambdamart", "R3_boosted_pairwise"):
        assert dict(built[name].params) == reference
        assert built[name].seed == built["R1_boosted_l2"].seed


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


def _write_doc(work, fingerprint=None):
    fp = fingerprint or B.definition_fingerprint(work)
    (work / B.PREREG_DOC).write_text(f"# prereg\n\nDefinition fingerprint: `{fp}`\n")


def _commit(work):
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "prereg")


def test_the_gate_refuses_a_missing_wrong_or_unpushed_registration(sandbox):
    with pytest.raises(prereg.PreregistrationError, match="does not exist"):
        B.prereg_gate(sandbox)
    _write_doc(sandbox, "0" * 64)
    _commit(sandbox)
    _git(sandbox, "push", "origin", "main")
    with pytest.raises(prereg.PreregistrationError, match="fingerprint"):
        B.prereg_gate(sandbox)


def test_the_gate_refuses_a_committed_but_unpushed_registration(sandbox):
    _write_doc(sandbox)
    _commit(sandbox)
    with pytest.raises(prereg.PreregistrationError, match="origin/main"):
        B.prereg_gate(sandbox)


def test_the_gate_passes_only_when_committed_unchanged_and_pushed(sandbox):
    _write_doc(sandbox)
    _commit(sandbox)
    _git(sandbox, "push", "origin", "main")
    receipt = B.prereg_gate(sandbox)
    assert receipt["pushed_to_origin_main"] and len(receipt["preregistration_commit"]) == 40


@pytest.mark.parametrize("path", ["src/quant/models/ranking.py", "src/quant/study/exp009b.py",
                                  "src/quant/backtest/ordering.py", "src/quant/validation/runner.py"])
def test_changing_any_method_file_after_registration_breaks_the_gate(sandbox, path):
    _write_doc(sandbox)
    _commit(sandbox)
    _git(sandbox, "push", "origin", "main")
    target = sandbox / path
    target.write_text(target.read_text() + "\n# tweak after registration\n")
    with pytest.raises(prereg.PreregistrationError):
        B.prereg_gate(sandbox)


def test_run_study_calls_the_gate_before_touching_any_data(sandbox, monkeypatch):
    touched = []
    monkeypatch.setattr(B, "load_frame", lambda *a, **k: touched.append("frame"))
    with pytest.raises(prereg.PreregistrationError):
        B.run_study(sandbox)
    assert touched == []


# ── the criteria ────────────────────────────────────────────────────────────

def report(ics, worst=None, corr=0.70, top=0.62, bottom=0.62):
    return {"fold_ic": {"values": ics, "worst": min(ics) if worst is None else worst},
            "stability": {"mean_rank_correlation_between_consecutive_dates": corr,
                          "top_group_retention": top, "bottom_group_retention": bottom}}


CONTROL = report([0.03] * 8)


@pytest.mark.parametrize("name, ranker, paired, econ, label", [
    ("all pass", report([0.04] * 8), {"mean_difference": 0.01, "one_sided_lower_bound": 0.002},
     {"turnover_ratio": 1.0, "net_sharpe_lower_bound": 0.05}, "ORDERING_AND_NET_IMPROVED"),
    ("economics fail", report([0.04] * 8), {"mean_difference": 0.01, "one_sided_lower_bound": 0.002},
     {"turnover_ratio": 1.0, "net_sharpe_lower_bound": -0.05}, "ORDERING_IMPROVED_NOT_ECONOMIC"),
    ("turnover too high", report([0.04] * 8), {"mean_difference": 0.01, "one_sided_lower_bound": 0.002},
     {"turnover_ratio": 1.2, "net_sharpe_lower_bound": 0.5}, "ORDERING_IMPROVED_NOT_ECONOMIC"),
    ("unstable", report([0.04] * 8, corr=0.5), {"mean_difference": 0.01, "one_sided_lower_bound": 0.002},
     {"turnover_ratio": 1.0, "net_sharpe_lower_bound": 0.5}, "ORDERING_IMPROVED_UNSTABLE"),
    ("only 5 folds better", report([0.04] * 5 + [0.02] * 3), {"mean_difference": 0.01, "one_sided_lower_bound": 0.002},
     {"turnover_ratio": 1.0, "net_sharpe_lower_bound": 0.5}, "ORDERING_IMPROVED_UNSTABLE"),
    ("worst fold much worse", report([0.05] * 7 + [0.01], worst=0.01), {"mean_difference": 0.01, "one_sided_lower_bound": 0.002},
     {"turnover_ratio": 1.0, "net_sharpe_lower_bound": 0.5}, "ORDERING_IMPROVED_UNSTABLE"),
    ("no significant gain", report([0.04] * 8), {"mean_difference": 0.01, "one_sided_lower_bound": -0.001},
     {"turnover_ratio": 1.0, "net_sharpe_lower_bound": 0.5}, "NO_ORDERING_GAIN"),
    ("worse ordering", report([0.02] * 8), {"mean_difference": -0.01, "one_sided_lower_bound": -0.02},
     {"turnover_ratio": 1.0, "net_sharpe_lower_bound": 0.5}, "NO_ORDERING_GAIN"),
])
def test_classification_follows_the_preregistered_rules(name, ranker, paired, econ, label):
    out = B.classify_ranker(CONTROL, ranker, paired, econ)
    assert out["classification"] == label, name
    assert out["promotion"] == "NOT ASSESSED"


def test_an_ic_gain_bought_by_churn_is_not_a_success():
    churny = report([0.06] * 8, corr=0.30, top=0.30, bottom=0.30)
    out = B.classify_ranker(CONTROL, churny, {"mean_difference": 0.03, "one_sided_lower_bound": 0.02},
                            {"turnover_ratio": 2.0, "net_sharpe_lower_bound": -1.0})
    assert out["classification"] == "ORDERING_IMPROVED_UNSTABLE"


def test_paired_ic_detects_a_real_gain_and_not_a_null_one():
    rng = np.random.default_rng(0)
    dates = pd.RangeIndex(400)
    control = pd.Series(rng.normal(0.03, 0.1, 400), index=dates)
    better = control + 0.03 + rng.normal(0, 0.02, 400)
    same = control + rng.normal(0, 0.02, 400)
    assert B.paired_ic(control, better)["one_sided_lower_bound"] > 0
    assert B.paired_ic(control, same)["one_sided_lower_bound"] < 0


# ── the runner, end to end on synthetic data ────────────────────────────────

def synthetic_world(n_symbols=120, n_dates=120, seed=0):
    rng = np.random.default_rng(seed)
    dates = [date(2020, 1, 3) + timedelta(days=7 * i) for i in range(n_dates)]
    symbols = [f"S{i:03d}" for i in range(n_symbols)]
    rows = []
    for d in dates:
        x = rng.normal(size=(n_symbols, len(B.FEATURES)))
        latent = 0.5 * x[:, 0] - 0.3 * x[:, 1] + rng.normal(size=n_symbols)
        rank = np.argsort(np.argsort(latent)) / (n_symbols - 1) * 2 - 1
        for i, s in enumerate(symbols):
            rows.append([d, s, True, rank[i], rng.normal(0, 0.03), rng.normal(0, 0.06),
                         1e8, *x[i]])
    return pd.DataFrame(rows, columns=["date", "symbol", "in_universe", B.LABEL, "fwd_ret_5", "fwd_ret_21",
                                       "dollar_volume", *B.FEATURES]), dates


def synthetic_plan(dates):
    folds = []
    for k in range(8):
        v0 = 60 + 7 * k
        folds.append(Fold(index=k, train_start=dates[0], train_end=dates[v0 - 6], purge_end=dates[v0 - 2],
                          validation_start=dates[v0], validation_end=dates[v0 + 5],
                          label_horizon_sessions=21, embargo_sessions=5, gap_sessions=26))
    return WalkForwardPlan(folds=folds, holdout_start=date(2030, 1, 1), holdout_end=date(2030, 12, 31),
                           scheme="expanding", label_horizon_sessions=21, embargo_sessions=5,
                           train_sessions=None, validation_sessions=6)


def test_run_study_end_to_end_on_synthetic_data(tmp_path, monkeypatch):
    frame, dates = synthetic_world()
    monkeypatch.setattr(B, "prereg_gate", lambda root, **k: {
        "preregistration_document": "synthetic", "preregistration_sha256": "0" * 64,
        "preregistration_commit": "0" * 40, "pushed_to_origin_main": True, "definition_fingerprint": "0" * 64})
    monkeypatch.setattr(B, "arm_firewall", lambda root: (date(2030, 1, 1), date(2030, 12, 31)))
    monkeypatch.setattr(B, "load_frame", lambda root: (frame, {
        "dataset_version": B.DEFINITION["data"]["dataset_id"], "content_hash": "x", "rows": len(frame),
        "features": B.FEATURES, "end": "2025-05-09"}))
    monkeypatch.setattr(exp009a, "panel_content_hash", lambda p: B.DEFINITION["data"]["returns_panel_sha256"])
    monkeypatch.setattr(B, "recorded_plan", lambda root: synthetic_plan(dates))
    monkeypatch.setattr(B, "reproduce_frozen", lambda root, refit: {"passed": True, "max_abs_prediction_difference": 0.0})
    small = (("n_estimators", 12), ("learning_rate", 0.1), ("max_depth", 3), ("subsample", 0.7), ("min_samples_leaf", 20))
    monkeypatch.setattr(B, "_COMMON", small)
    monkeypatch.setattr(B, "specs", lambda: [
        B.ModelSpec("R0_sklearn_gb", "gradient_boosting", (("n_estimators", 12), ("min_samples_leaf", 20)), 0),
        B.ModelSpec("R1_boosted_l2", "boosted_l2", small, 0),
        B.ModelSpec("R2_boosted_lambdamart", "boosted_lambdamart", small, 0),
        B.ModelSpec("R3_boosted_pairwise", "boosted_pairwise", small, 0)])
    monkeypatch.setitem(B.DEFINITION["inference"], "bootstrap_draws", 200)

    out = B.run_study(REPO, output=tmp_path / "out", workers=1)
    cmp = out["comparisons"]
    assert set(cmp) == {"R2_boosted_lambdamart", "R3_boosted_pairwise"}
    for entry in cmp.values():
        assert entry["criteria"]["classification"] in {
            "ORDERING_AND_NET_IMPROVED", "ORDERING_IMPROVED_NOT_ECONOMIC",
            "ORDERING_IMPROVED_UNSTABLE", "NO_ORDERING_GAIN"}
        assert entry["criteria"]["promotion"] == "NOT ASSESSED"
    for cid in ("R0_sklearn_gb", "R1_boosted_l2", "R2_boosted_lambdamart", "R3_boosted_pairwise"):
        assert (tmp_path / "out" / f"predictions_{cid}.parquet").exists()
        assert (tmp_path / "out" / f"periods_{cid}_A_immediate.parquet").exists()
        assert (tmp_path / "out" / f"periods_{cid}_C_topk_dropout_10.parquet").exists()
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text())
    assert manifest["holdout"]["touched"] is False
    assert "/Users/" not in json.dumps(manifest)
    assert set(manifest["output_sha256"]) >= {"metrics.json", "definition.json"}
    assert out["decision"]["promotion"] == "NOT ASSESSED"
    metrics = json.loads((tmp_path / "out" / "metrics.json").read_text())
    assert "_ic_series" not in json.dumps(metrics) and "_periods" not in json.dumps(metrics)


def test_run_study_refuses_when_the_baseline_does_not_reproduce(tmp_path, monkeypatch):
    frame, dates = synthetic_world(n_dates=120)
    monkeypatch.setattr(B, "prereg_gate", lambda root, **k: {"definition_fingerprint": "x"})
    monkeypatch.setattr(B, "arm_firewall", lambda root: (date(2030, 1, 1), date(2030, 12, 31)))
    monkeypatch.setattr(B, "load_frame", lambda root: (frame, {
        "dataset_version": B.DEFINITION["data"]["dataset_id"], "content_hash": "x", "rows": len(frame),
        "features": B.FEATURES, "end": "2025-05-09"}))
    monkeypatch.setattr(exp009a, "panel_content_hash", lambda p: B.DEFINITION["data"]["returns_panel_sha256"])
    monkeypatch.setattr(B, "recorded_plan", lambda root: synthetic_plan(dates))
    monkeypatch.setattr(B, "reproduce_frozen", lambda root, refit: {"passed": False})
    small = (("n_estimators", 5), ("learning_rate", 0.1), ("max_depth", 2), ("subsample", 0.7), ("min_samples_leaf", 20))
    monkeypatch.setattr(B, "specs", lambda: [
        B.ModelSpec("R0_sklearn_gb", "gradient_boosting", (("n_estimators", 5),), 0),
        B.ModelSpec("R1_boosted_l2", "boosted_l2", small, 0),
        B.ModelSpec("R2_boosted_lambdamart", "boosted_lambdamart", small, 0),
        B.ModelSpec("R3_boosted_pairwise", "boosted_pairwise", small, 0)])
    with pytest.raises(RuntimeError, match="INVALID"):
        B.run_study(REPO, output=tmp_path / "out", workers=1)
    assert not (tmp_path / "out" / "metrics.json").exists()
