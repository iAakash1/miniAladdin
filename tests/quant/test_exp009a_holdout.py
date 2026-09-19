"""EXP-009A cannot spend the holdout, and cannot run unregistered.

Two guarantees, both structural rather than conventional:

1. No stage of the study — reading predictions, building the returns panel,
   writing membership or period files — can touch the sealed window; the
   firewall raises before a metric exists.
2. The run is refused unless the preregistration is committed unchanged and
   already pushed. The gate is exercised here against a real temporary git
   repository with a real remote, not mocked.
"""

import json
import subprocess
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.quant.study import exp009a as X
from src.quant.study.firewall import FIREWALL, HoldoutBreach, reset_for_tests

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def clean_firewall():
    reset_for_tests()
    yield
    reset_for_tests()


# ── the holdout ─────────────────────────────────────────────────────────────

def test_the_definition_ends_before_the_recorded_holdout():
    start, end = X.holdout_window(REPO)
    assert date.fromisoformat(X.DEFINITION["input"]["last_prediction_date"]) < start
    assert start < end


def test_the_frozen_predictions_do_not_reach_the_holdout():
    X.arm_firewall(REPO)
    frame, info = X.load_frozen_predictions(REPO)
    start, _ = X.holdout_window(REPO)
    assert frame["date"].max() < start
    assert info["rows"] == X.DEFINITION["input"]["rows"]
    assert len(info["file_sha256"]) == 64


def test_a_panel_ending_inside_the_holdout_is_refused_before_anything_is_built():
    start, _ = X.holdout_window(REPO)
    with pytest.raises(HoldoutBreach):
        X.build_returns_panel(start, root=REPO)
    with pytest.raises(HoldoutBreach):
        X.build_returns_panel(date(2026, 1, 15), root=REPO)


def test_holdout_rows_in_predictions_are_refused(tmp_path):
    start, end = X.arm_firewall(REPO)
    bad = pd.DataFrame({"date": [start], "symbol": ["AAA"], "prediction": [0.1]})
    with pytest.raises(HoldoutBreach):
        FIREWALL.assert_clear(bad, context="test")


def test_holdout_dated_outputs_are_refused():
    start, _ = X.arm_firewall(REPO)
    weights = pd.DataFrame({"date": [start], "symbol": ["AAA"], "weight": [0.01]})
    with pytest.raises(HoldoutBreach):
        FIREWALL.assert_clear(weights, context="membership")


def test_the_study_never_lifts_the_firewall():
    source = (REPO / "src/quant/study/exp009a.py").read_text()
    assert "FIREWALL.override" not in source
    assert "QUANT_ALLOW_HOLDOUT" not in source
    assert "QUANT_DISABLE_HOLDOUT_FIREWALL" not in source
    assert "holdout_sessions" not in source            # it does not build a walk-forward plan


def test_the_contract_is_not_armed_so_the_firewall_is_engaged():
    X.arm_firewall(REPO)
    assert FIREWALL.status()["engaged"] is True


# ── the preregistration gate ────────────────────────────────────────────────

def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
                        "PATH": __import__("os").environ["PATH"], "HOME": str(cwd)})


@pytest.fixture
def sandbox(tmp_path):
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    remote.mkdir()
    work.mkdir()
    _git(remote, "init", "--bare", "-b", "main")
    _git(work, "init", "-b", "main")
    _git(work, "remote", "add", "origin", str(remote))
    for name in X.METHOD_SOURCES:
        target = work / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((REPO / name).read_text())
    (work / "docs").mkdir()
    return work


def _write_doc(work, fingerprint=None):
    fp = fingerprint or X.definition_fingerprint(work)
    (work / X.PREREG_DOC).write_text(f"# prereg\n\nDefinition fingerprint: `{fp}`\n")


def _commit_all(work, message="prereg"):
    _git(work, "add", "-A")
    _git(work, "commit", "-m", message)


def test_the_gate_refuses_when_no_document_exists(sandbox):
    with pytest.raises(X.PreregistrationError, match="does not exist"):
        X.prereg_gate(sandbox)


def test_the_gate_refuses_a_document_with_the_wrong_fingerprint(sandbox):
    _write_doc(sandbox, fingerprint="0" * 64)
    _commit_all(sandbox)
    _git(sandbox, "push", "origin", "main")
    with pytest.raises(X.PreregistrationError, match="fingerprint"):
        X.prereg_gate(sandbox)


def test_the_gate_refuses_a_committed_but_unpushed_document(sandbox):
    _write_doc(sandbox)
    _commit_all(sandbox)
    with pytest.raises(X.PreregistrationError, match="origin/main"):
        X.prereg_gate(sandbox)


def test_the_gate_refuses_a_document_that_was_never_committed(sandbox):
    _write_doc(sandbox)
    with pytest.raises(X.PreregistrationError, match="not tracked"):
        X.prereg_gate(sandbox)


def test_the_gate_passes_only_when_committed_unchanged_and_pushed(sandbox):
    _write_doc(sandbox)
    _commit_all(sandbox)
    _git(sandbox, "push", "origin", "main")
    receipt = X.prereg_gate(sandbox)
    assert receipt["pushed_to_origin_main"] is True
    assert len(receipt["preregistration_commit"]) == 40
    assert receipt["definition_fingerprint"] == X.definition_fingerprint(sandbox)


def test_changing_the_method_after_registration_is_caught_two_ways(sandbox):
    _write_doc(sandbox)
    _commit_all(sandbox)
    _git(sandbox, "push", "origin", "main")
    rules = sandbox / "src/quant/backtest/rules.py"
    rules.write_text(rules.read_text() + "\n# tweak after registration\n")
    with pytest.raises(X.PreregistrationError):           # fingerprint no longer matches the document
        X.prereg_gate(sandbox)


def test_the_fingerprint_moves_with_the_definition_and_the_rules(monkeypatch, sandbox):
    base = X.definition_fingerprint(sandbox)
    altered = json.loads(json.dumps(X.DEFINITION))
    altered["cells"][1]["retain_fraction"] = 0.35
    monkeypatch.setattr(X, "DEFINITION", altered)
    assert X.definition_fingerprint(sandbox) != base
    monkeypatch.undo()
    assert X.definition_fingerprint(sandbox) == base
    engine = sandbox / "src/quant/backtest/engine.py"
    engine.write_text(engine.read_text() + "\n")
    assert X.definition_fingerprint(sandbox) != base


def test_run_study_calls_the_gate_before_reading_any_data(sandbox, monkeypatch):
    called = []
    monkeypatch.setattr(X, "load_frozen_predictions", lambda *a, **k: called.append("read"))
    with pytest.raises(X.PreregistrationError):
        X.run_study(sandbox)
    assert called == []


# ── the statistics the criteria rely on ─────────────────────────────────────

def test_newey_west_matches_the_plain_t_when_there_is_no_autocorrelation():
    rng = np.random.default_rng(0)
    x = rng.normal(0.1, 1.0, 4000)
    out = X.newey_west_mean_t(x, 4)
    plain = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    assert out["hac_t"] == pytest.approx(plain, rel=0.1)


def test_newey_west_widens_the_error_under_positive_autocorrelation():
    rng = np.random.default_rng(1)
    e = rng.normal(size=4000)
    x = np.empty_like(e)
    x[0] = e[0]
    for i in range(1, len(e)):
        x[i] = 0.7 * x[i - 1] + e[i]
    plain_se = x.std(ddof=1) / np.sqrt(len(x))
    assert X.newey_west_mean_t(x, 8)["hac_se"] > 1.5 * plain_se


def test_paired_bootstrap_detects_a_real_difference_and_not_a_null_one():
    rng = np.random.default_rng(2)
    control = rng.normal(0.0002, 0.01, 400)
    better = control + 0.0006 + rng.normal(0, 0.0005, 400)
    real = X.paired_block_bootstrap_sharpe_diff(
        better, control, block=8, draws=2000, seed=0, periods_per_year=50.4, one_sided_level=0.9875)
    assert real["one_sided_lower_bound"] > 0
    null = X.paired_block_bootstrap_sharpe_diff(
        control + rng.normal(0, 0.0005, 400), control, block=8, draws=2000, seed=0,
        periods_per_year=50.4, one_sided_level=0.9875)
    assert null["one_sided_lower_bound"] < 0 < null["ci95_two_sided"][1]


def test_the_bootstrap_is_reproducible_from_its_seed():
    rng = np.random.default_rng(3)
    a, b = rng.normal(0, 0.01, 200), rng.normal(0, 0.01, 200)
    kw = dict(block=8, draws=500, seed=7, periods_per_year=50.4, one_sided_level=0.9875)
    assert X.paired_block_bootstrap_sharpe_diff(a, b, **kw) == X.paired_block_bootstrap_sharpe_diff(a, b, **kw)


CONTROL = {"annualised_turnover": 20.0}


@pytest.mark.parametrize("turnover, retention, lower, folds, label", [
    (10.0, 0.90, 0.5, 7, "MECHANISM_CONFIRMED"),
    (10.0, 0.60, 0.5, 8, "EDGE_LOST"),
    (15.0, 0.95, 0.5, 8, "INSUFFICIENT_TURNOVER_CUT"),
    (10.0, 0.90, -0.1, 8, "NO_RELIABLE_NET_GAIN"),
    (10.0, 0.90, 0.5, 5, "NO_RELIABLE_NET_GAIN"),
    (14.0, 0.75, 0.01, 6, "MECHANISM_CONFIRMED"),          # exactly at every threshold
])
def test_classification_follows_the_preregistered_rules(turnover, retention, lower, folds, label):
    out = X.classify_cell({}, CONTROL, {"annualised_turnover": turnover}, retention,
                          {"one_sided_lower_bound": lower}, folds)
    assert out["classification"] == label
    assert out["promotion"] == "NOT ASSESSED"


def test_a_treatment_cannot_be_called_a_success_on_cost_savings_alone():
    """Turnover cut and net gain without retained gross edge is EDGE_LOST, never a win."""
    out = X.classify_cell({}, CONTROL, {"annualised_turnover": 5.0}, 0.10,
                          {"one_sided_lower_bound": 2.0}, 8)
    assert out["classification"] == "EDGE_LOST"


# ── the runner, exercised end to end on synthetic data ──────────────────────

def test_run_study_end_to_end_on_synthetic_data(tmp_path, monkeypatch):
    """A smoke test of the whole runner. It touches no real prediction and no real return."""
    from tests.quant.test_weight_rules import panel

    pred, ret = panel(n_symbols=100, n_dates=80, rho=0.8, seed=11)
    dates = sorted(pred["date"].unique())
    fold = {d: min(i // 10, 7) for i, d in enumerate(dates)}
    predictions = pred.assign(fold=pred["date"].map(fold), fwd_rank_21=0.0, model="gradient_boosting")
    returns = ret.assign(fwd_ret_21=0.0, in_universe=True)

    monkeypatch.setattr(X, "prereg_gate", lambda root, **k: {
        "preregistration_document": "synthetic", "preregistration_sha256": "0" * 64,
        "preregistration_commit": "0" * 40, "pushed_to_origin_main": True,
        "definition_fingerprint": "0" * 64})
    monkeypatch.setattr(X, "load_frozen_predictions", lambda root: (predictions, {"rows": len(predictions)}))
    monkeypatch.setattr(X, "build_returns_panel", lambda last, **k: returns)
    monkeypatch.setattr(X, "panel_integrity", lambda p, r: {"passed": True})
    monkeypatch.setattr(X, "verify_baseline_reproduction", lambda c, root=None: {"passed": True, "compared": []})
    monkeypatch.setattr(X, "_read_factors", lambda root: None)
    monkeypatch.setattr(X, "arm_firewall", lambda root: (date(2025, 8, 28), date(2026, 8, 28)))
    monkeypatch.setitem(X.DEFINITION["inference"], "draws", 300)

    out = X.run_study(REPO, output=tmp_path / "out")
    cells = out["metrics"]["cells"]
    assert set(cells) == {c["id"] for c in X.DEFINITION["cells"]}
    for cid, entry in cells.items():
        assert (tmp_path / "out" / f"periods_{cid}.parquet").exists()
        assert (tmp_path / "out" / f"membership_{cid}.parquet").exists()
        assert len(entry["cost_sweep"]) == 5
        assert len(entry["fold_metrics"]) == 8
        if entry["cell"]["role"] == "treatment":
            assert entry["criteria"]["classification"] in {
                "MECHANISM_CONFIRMED", "EDGE_LOST", "INSUFFICIENT_TURNOVER_CUT", "NO_RELIABLE_NET_GAIN"}
            assert entry["criteria"]["promotion"] == "NOT ASSESSED"
            assert entry["versus_control"]["annualised_turnover_ratio"] < 1.0
    for name in ("definition.json", "manifest.json", "metrics.json", "summary.parquet"):
        assert (tmp_path / "out" / name).exists()
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text())
    assert manifest["holdout"]["touched"] is False
    assert "/Users/" not in json.dumps(manifest) and "/home/" not in json.dumps(manifest)
    assert out["metrics"]["decision"]["promotion"] == "NOT ASSESSED"

    rob = X.run_robustness(REPO, output=tmp_path / "out")
    assert rob["label"].startswith("EXPLORATORY")
    assert set(rob["cells"]) == set(cells)
    control = rob["cells"]["A_immediate"]
    assert control["long_leg_contribution_bp"] + control["short_leg_contribution_bp"] == pytest.approx(
        control["mean_gross_bp"], abs=1e-6)
    # It changes no classification: the recorded metrics are untouched.
    assert json.loads((tmp_path / "out" / "metrics.json").read_text())["decision"] == out["metrics"]["decision"]


def test_run_study_refuses_to_report_treatments_if_the_control_does_not_reproduce(tmp_path, monkeypatch):
    from tests.quant.test_weight_rules import panel

    pred, ret = panel(n_symbols=100, n_dates=40, seed=12)
    predictions = pred.assign(fold=0, fwd_rank_21=0.0, model="gradient_boosting")
    monkeypatch.setattr(X, "prereg_gate", lambda root, **k: {"definition_fingerprint": "x"})
    monkeypatch.setattr(X, "load_frozen_predictions", lambda root: (predictions, {}))
    monkeypatch.setattr(X, "build_returns_panel", lambda last, **k: ret.assign(fwd_ret_21=0.0, in_universe=True))
    monkeypatch.setattr(X, "panel_integrity", lambda p, r: {"passed": True})
    monkeypatch.setattr(X, "verify_baseline_reproduction", lambda c, root=None: {"passed": False, "compared": []})
    monkeypatch.setattr(X, "arm_firewall", lambda root: (date(2025, 8, 28), date(2026, 8, 28)))
    with pytest.raises(RuntimeError, match="INVALID"):
        X.run_study(REPO, output=tmp_path / "out")
    assert not (tmp_path / "out" / "metrics.json").exists()
    assert (tmp_path / "out" / "manifest.json").exists()
