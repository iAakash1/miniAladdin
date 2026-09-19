"""EXP-009C: the folds that can speak, the data gate, and the criteria."""

import json
import subprocess
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.quant.features import analyst_pit
from src.quant.study import exp009a
from src.quant.study import exp009b
from src.quant.study import exp009c as C
from src.quant.study import prereg
from src.quant.study.firewall import reset_for_tests

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def clean_firewall():
    reset_for_tests()
    yield
    reset_for_tests()


# ── structure ───────────────────────────────────────────────────────────────

def test_the_arm_adds_exactly_the_eight_analyst_features_to_the_frozen_base():
    assert len(C.ANALYST_XS) == 8
    assert C.ANALYST_XS == [f"{n}_xs" for n in analyst_pit.FEATURE_NAMES]
    assert not set(C.ANALYST_XS) & set(exp009b.FEATURES)
    assert C.DEFINITION["data"]["base_features"] == exp009b.FEATURES


def test_only_folds_with_two_years_of_analyst_history_are_evaluable():
    plan = exp009b.recorded_plan(REPO)
    assert C.evaluable_folds(plan) == C.DEFINITION["evaluable_folds"]["expected"] == [3, 4, 5, 6, 7]


def test_the_rule_is_a_function_of_the_plan_not_of_any_result():
    plan = exp009b.recorded_plan(REPO)
    early = [f for f in plan.folds if f.index not in C.evaluable_folds(plan)]
    assert early and all(
        (f.train_end.year - C.ANALYST_STARTS.year) * 12 + (f.train_end.month - C.ANALYST_STARTS.month) < 24
        for f in early)


def test_the_study_reads_no_holdout_and_never_lifts_the_firewall():
    source = (REPO / "src/quant/study/exp009c.py").read_text()
    for forbidden in ("FIREWALL.override", "QUANT_ALLOW_HOLDOUT", ".holdout("):
        assert forbidden not in source
    assert C.DEFINITION["holdout"]["read"] is False


# ── the data gate, on a synthetic estimate table ────────────────────────────

def make_estimates(n_symbols=6, weeks=80, seed=0):
    rng = np.random.default_rng(seed)
    rows_eps, rows_sales = [], []
    dates = pd.to_datetime("2018-01-07") + pd.to_timedelta(np.arange(weeks) * 7, unit="D")
    for i in range(n_symbols):
        eps = 1.0 + np.cumsum(rng.normal(0, 0.02, weeks))
        for d, e in zip(dates, eps):
            common = dict(symbol=f"S{i}", date=d, period="Current Year", period_end_date=pd.Timestamp("2099-12-31"))
            rows_eps.append({**common, "consensus": e, "high": e + 0.1, "low": e - 0.1, "count": 4, "year_ago": 0.9})
            rows_sales.append({**common, "consensus": 100 * e, "high": 110 * e, "low": 90 * e, "count": 4, "year_ago": 90.0})
    return pd.DataFrame(rows_eps), pd.DataFrame(rows_sales), dates


def test_the_synthetic_gates_pass_and_a_deliberate_leak_is_caught(monkeypatch):
    eps, sales, dates = make_estimates()
    monkeypatch.setattr(C, "_estimates", lambda root, until: (eps.copy(), sales.copy()))
    monkeypatch.setattr(C, "GATE_CUTOFF", date(2018, 12, 31))
    panel_dates = [d.date() for d in pd.date_range("2018-03-01", "2019-06-30", freq="7D")]
    frame = pd.DataFrame([(d, f"S{i}") for d in panel_dates for i in range(6)], columns=["date", "symbol"])
    gates = C.pit_gates(frame, REPO, {})
    assert gates["passed"], gates

    # A leak: an attach that allows exact matches would break strictness; emulate by making the
    # feature table's availability earlier than its vintage.
    real_build = analyst_pit.build_analyst_features

    def leaky(eps_table, sales_table, **kw):
        out = real_build(eps_table, sales_table, **kw)
        out["available_from"] = out["available_from"] - pd.Timedelta(days=30)
        return out

    monkeypatch.setattr(analyst_pit, "build_analyst_features", leaky)
    assert not C.pit_gates(frame, REPO, {})["passed"]


# ── criteria ────────────────────────────────────────────────────────────────

GOOD = {"mean_difference": 0.004, "one_sided_lower_bound": 0.001}


@pytest.mark.parametrize("paired, folds, worst, econ, gates, label", [
    (GOOD, 5, True, {"turnover_ratio": 1.0, "net_sharpe_lower_bound": 0.1}, True, "ANALYST_VALUE_CONFIRMED"),
    (GOOD, 4, True, {"turnover_ratio": 1.0, "net_sharpe_lower_bound": 0.1}, True, "ANALYST_VALUE_CONFIRMED"),
    (GOOD, 3, True, {"turnover_ratio": 1.0, "net_sharpe_lower_bound": 0.1}, True, "ANALYST_NO_RELIABLE_VALUE"),
    (GOOD, 5, False, {"turnover_ratio": 1.0, "net_sharpe_lower_bound": 0.1}, True, "ANALYST_NO_RELIABLE_VALUE"),
    (GOOD, 5, True, {"turnover_ratio": 1.0, "net_sharpe_lower_bound": -0.1}, True, "ANALYST_ORDERING_ONLY"),
    (GOOD, 5, True, {"turnover_ratio": 1.3, "net_sharpe_lower_bound": 0.5}, True, "ANALYST_ORDERING_ONLY"),
    ({"mean_difference": 0.004, "one_sided_lower_bound": -0.001}, 5, True,
     {"turnover_ratio": 1.0, "net_sharpe_lower_bound": 0.5}, True, "ANALYST_NO_RELIABLE_VALUE"),
    ({"mean_difference": -0.004, "one_sided_lower_bound": -0.01}, 1, False,
     {"turnover_ratio": 1.0, "net_sharpe_lower_bound": 0.5}, True, "ANALYST_NO_RELIABLE_VALUE"),
    (GOOD, 5, True, {"turnover_ratio": 1.0, "net_sharpe_lower_bound": 0.5}, False, "BLOCKED_DATA_QUALITY"),
])
def test_classification_follows_the_preregistered_rules(paired, folds, worst, econ, gates, label):
    out = C.classify(paired, folds, 5, worst, econ, gates)
    assert out["classification"] == label
    assert out["promotion"] == "NOT ASSESSED"


def test_a_failed_data_gate_blocks_regardless_of_how_good_the_numbers_look():
    out = C.classify({"mean_difference": 1.0, "one_sided_lower_bound": 1.0}, 5, 5, True,
                     {"turnover_ratio": 0.5, "net_sharpe_lower_bound": 9.0}, gates_passed=False)
    assert out["classification"] == "BLOCKED_DATA_QUALITY"


# ── the gate and the run ────────────────────────────────────────────────────

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
    for name in C.METHOD_SOURCES:
        target = work / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((REPO / name).read_text())
    (work / "docs").mkdir()
    return work


def test_the_gate_refuses_unpushed_and_changed_registrations(sandbox):
    fp = C.definition_fingerprint(sandbox)
    (sandbox / C.PREREG_DOC).write_text(f"# prereg\n\nDefinition fingerprint: `{fp}`\n")
    _git(sandbox, "add", "-A"); _git(sandbox, "commit", "-m", "prereg")
    with pytest.raises(prereg.PreregistrationError, match="origin/main"):
        C.prereg_gate(sandbox)
    _git(sandbox, "push", "origin", "main")
    assert C.prereg_gate(sandbox)["pushed_to_origin_main"]
    target = sandbox / "src/quant/features/analyst_pit.py"
    target.write_text(target.read_text() + "\n# tweak after registration\n")
    with pytest.raises(prereg.PreregistrationError):
        C.prereg_gate(sandbox)


def test_run_study_calls_the_gate_before_touching_data(sandbox, monkeypatch):
    touched = []
    monkeypatch.setattr(exp009b, "load_frame", lambda *a, **k: touched.append("frame"))
    with pytest.raises(prereg.PreregistrationError):
        C.run_study(sandbox)
    assert touched == []


def test_paired_one_sided_detects_a_real_gain_only():
    rng = np.random.default_rng(1)
    idx = pd.RangeIndex(300)
    base = pd.Series(rng.normal(0.03, 0.1, 300), index=idx)
    assert C.paired_ic_one_sided(base, base + 0.03 + rng.normal(0, 0.02, 300))["one_sided_lower_bound"] > 0
    assert C.paired_ic_one_sided(base, base + rng.normal(0, 0.02, 300))["one_sided_lower_bound"] < 0


# ── the runner, end to end on synthetic data ────────────────────────────────

def test_run_study_end_to_end_on_synthetic_data(tmp_path, monkeypatch):
    from datetime import timedelta
    from src.quant.pit import universe as universe_module
    from tests.quant.test_exp009b import synthetic_world, synthetic_plan

    frame, dates = synthetic_world(n_symbols=120, n_dates=120)
    symbols = sorted(frame["symbol"].unique())
    eps_rows, sales_rows = [], []
    rng = np.random.default_rng(3)
    vintage_dates = pd.date_range(pd.Timestamp(dates[0]) - pd.Timedelta(days=200),
                                  pd.Timestamp(dates[-1]), freq="7D")
    for s in symbols:
        level = 1.0 + np.cumsum(rng.normal(0, 0.02, len(vintage_dates)))
        for d, e in zip(vintage_dates, level):
            base = dict(symbol=s, date=d, period="Current Year", period_end_date=pd.Timestamp("2099-12-31"))
            eps_rows.append({**base, "consensus": e, "high": e + 0.1, "low": e - 0.1, "count": 5, "year_ago": 0.9})
            sales_rows.append({**base, "consensus": 100 * e, "high": 110 * e, "low": 90 * e, "count": 5, "year_ago": 90.0})
    eps, sales = pd.DataFrame(eps_rows), pd.DataFrame(sales_rows)

    small = (("n_estimators", 10), ("learning_rate", 0.1), ("max_depth", 3), ("min_samples_leaf", 20))
    monkeypatch.setitem(C.BASE_MODEL, "params", small)
    monkeypatch.setitem(C.DEFINITION["inference"], "bootstrap_draws", 200)
    monkeypatch.setattr(C, "prereg_gate", lambda root, **k: {
        "preregistration_document": "synthetic", "preregistration_sha256": "0" * 64,
        "preregistration_commit": "0" * 40, "pushed_to_origin_main": True, "definition_fingerprint": "0" * 64})
    monkeypatch.setattr(exp009b, "arm_firewall", lambda root: (date(2030, 1, 1), date(2030, 12, 31)))
    monkeypatch.setattr(exp009b, "load_frame", lambda root: (frame, {
        "dataset_version": C.DEFINITION["data"]["dataset_id"], "content_hash": "x", "rows": len(frame), "end": "2025-05-09"}))
    monkeypatch.setattr(exp009a, "panel_content_hash", lambda p: C.DEFINITION["data"]["returns_panel_sha256"])
    plan = synthetic_plan(dates)
    monkeypatch.setattr(exp009b, "recorded_plan", lambda root: plan)
    monkeypatch.setitem(C.DEFINITION["evaluable_folds"], "expected", [f.index for f in plan.folds])
    monkeypatch.setattr(C, "evaluable_folds", lambda p: [f.index for f in p.folds])
    monkeypatch.setattr(C, "_estimates", lambda root, until: (eps.copy(), sales.copy()))
    monkeypatch.setattr(C, "GATE_CUTOFF", dates[60])
    monkeypatch.setattr(universe_module.UniverseHistory, "load", classmethod(lambda cls, *a, **k: object()))
    monkeypatch.setattr(C.xs, "universe_map", lambda history, ds: {d: set(symbols) for d in ds})

    # the BASE reference: the same model on the same folds, computed independently
    from src.quant.models.factory import ModelSpec
    from src.quant.validation.parallel import evaluate_specs
    ref = evaluate_specs([ModelSpec("ref", "gradient_boosting", small, 0)], frame, plan,
                         features=exp009b.FEATURES, label=C.LABEL, step_sessions=5, workers=1)[0][0].predictions
    monkeypatch.setattr(C, "_reference_predictions", lambda root: ref[["date", "symbol", "prediction"]])

    out = C.run_study(REPO, output=tmp_path / "out", workers=1)
    assert out["manifest"]["analyst_pit_gates"]["passed"] is True
    assert out["manifest"]["base_reproduction"]["passed"] is True
    assert out["criteria"]["classification"] in {"ANALYST_VALUE_CONFIRMED", "ANALYST_ORDERING_ONLY",
                                                 "ANALYST_NO_RELIABLE_VALUE"}
    assert out["decision"]["promotion"] == "NOT ASSESSED"
    for name in ("definition.json", "manifest.json", "metrics.json", "predictions_BASE.parquet", "predictions_ARM.parquet",
                 "periods_BASE_A_immediate.parquet", "periods_ARM_C_topk_dropout_10.parquet"):
        assert (tmp_path / "out" / name).exists(), name
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text())
    assert manifest["holdout"]["touched"] is False and "/Users/" not in json.dumps(manifest)
    assert "analyst_feature_coverage_by_year" in manifest


def test_a_failed_pit_gate_blocks_the_run_and_trains_nothing(tmp_path, monkeypatch):
    from tests.quant.test_exp009b import synthetic_world
    frame, dates = synthetic_world(n_dates=30)
    monkeypatch.setattr(C, "prereg_gate", lambda root, **k: {"definition_fingerprint": "x"})
    monkeypatch.setattr(exp009b, "arm_firewall", lambda root: (date(2030, 1, 1), date(2030, 12, 31)))
    monkeypatch.setattr(exp009b, "load_frame", lambda root: (frame, {
        "dataset_version": C.DEFINITION["data"]["dataset_id"], "content_hash": "x", "rows": len(frame), "end": "2025-05-09"}))
    monkeypatch.setattr(exp009a, "panel_content_hash", lambda p: C.DEFINITION["data"]["returns_panel_sha256"])
    monkeypatch.setattr(C, "pit_gates", lambda *a, **k: {"passed": False, "strict_attach": False})
    from src.quant.pit import universe as universe_module
    monkeypatch.setattr(universe_module.UniverseHistory, "load", classmethod(lambda cls, *a, **k: object()))
    monkeypatch.setattr(C.xs, "universe_map", lambda history, ds: {})
    trained = []
    monkeypatch.setattr(C, "evaluate_specs", lambda *a, **k: trained.append(1))
    out = C.run_study(REPO, output=tmp_path / "out", workers=1)
    assert out["decision"]["classification"] == "BLOCKED_DATA_QUALITY"
    assert trained == []
    assert not (tmp_path / "out" / "metrics.json").exists()
