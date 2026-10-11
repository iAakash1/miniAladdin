"""EXP-012: placebo construction, interactions, statistics, the saved-model contract and the registration guard."""

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.quant.study import exp012

ROOT = Path(__file__).resolve().parents[2]


def synthetic(n_dates=60, n_names=40, seed=3):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2018-01-01", periods=n_dates, freq="7D").date
    rows = [(d, f"S{i:02d}") for d in dates for i in range(n_names)]
    frame = pd.DataFrame(rows, columns=["date", "symbol"])
    for col in [*exp012.FUNDAMENTALS, *exp012.EXISTING_RELIABILITY, *exp012.NEW_BLOCK, *exp012.BASELINE]:
        frame[col] = rng.uniform(-1, 1, len(frame))
    frame["in_universe"] = True
    frame[exp012.LABEL] = 0.1 * frame[exp012.BASELINE[0]] + rng.normal(0, 1, len(frame))
    return frame


def test_permutation_keeps_each_dates_values_and_breaks_the_firm_alignment():
    frame = synthetic()
    out = exp012.permute_within_date(frame, exp012.NEW_BLOCK, seed=1)
    for _, idx in frame.groupby("date").indices.items():
        assert sorted(out["rel_u_xs"].iloc[idx]) == pytest.approx(sorted(frame["rel_u_xs"].iloc[idx]))
    assert not np.allclose(out["rel_u_xs"], frame["rel_u_xs"])
    # one permutation is shared by all columns: the rows of the block stay intact
    joint_before = set(map(tuple, frame[exp012.NEW_BLOCK].round(9).to_numpy()))
    joint_after = set(map(tuple, out[exp012.NEW_BLOCK].round(9).to_numpy()))
    assert joint_after == joint_before


def test_permutation_is_deterministic_in_its_seed():
    frame = synthetic()
    a = exp012.permute_within_date(frame, exp012.NEW_BLOCK, seed=4)
    b = exp012.permute_within_date(frame, exp012.NEW_BLOCK, seed=4)
    c = exp012.permute_within_date(frame, exp012.NEW_BLOCK, seed=5)
    pd.testing.assert_frame_equal(a, b)
    assert not a.equals(c)


def test_shift_takes_each_firms_value_from_exactly_k_rows_earlier():
    frame = synthetic(n_dates=70)
    out = exp012.shift_within_security(frame, ["rel_u_xs"], rows=10)
    one = frame[frame["symbol"] == "S03"].sort_values("date")
    shifted = out.loc[one.index, "rel_u_xs"].to_numpy()
    assert np.isnan(shifted[:10]).all()
    assert shifted[10:] == pytest.approx(one["rel_u_xs"].to_numpy()[:-10])


def test_placebo_rebuilds_the_interactions_from_the_placebo_block_only():
    frame = synthetic()
    real = exp012.placebo_frame(frame.assign(**{f"int_{f}": 0.0 for f in exp012.FUNDAMENTALS}), "permute", 2, "new")
    f = exp012.FUNDAMENTALS[0]
    assert real[f"int_{f}"].to_numpy() == pytest.approx((real[f] * real["rel_u_xs"]).to_numpy())
    existing = exp012.placebo_frame(frame, "permute", 2, "existing")
    assert (existing["rel_u_xs"] == frame["rel_u_xs"]).all()
    assert not np.allclose(existing[exp012.EXISTING_RELIABILITY[0]], frame[exp012.EXISTING_RELIABILITY[0]])


def test_every_arm_resolves_to_columns_the_frame_can_hold():
    for arm in exp012.ARMS:
        cols = exp012.arm_features(arm)
        assert cols and len(cols) == len(set(cols)), arm
    assert set(exp012.arm_features("P1")) == set(exp012.arm_features("A6"))
    assert set(exp012.arm_features("A0")) <= set(exp012.arm_features("A1"))
    assert set(exp012.arm_features("A2")).isdisjoint(exp012.EXISTING_RELIABILITY)


def test_holm_adjustment():
    adjusted = exp012.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adjusted == pytest.approx({"a": 0.03, "c": 0.06, "b": 0.06})
    assert all(0 <= v <= 1 for v in exp012.holm({"x": 0.9, "y": 0.8}).values())


def test_block_bootstrap_is_reproducible_and_brackets_the_mean():
    rng = np.random.default_rng(0)
    series = 0.02 + rng.normal(0, 0.1, 400)
    lo, hi = exp012.block_bootstrap_ci(series, draws=800)
    assert (lo, hi) == exp012.block_bootstrap_ci(series, draws=800)
    assert lo < series.mean() < hi


def test_support_rule_needs_significance_folds_and_a_surviving_placebo():
    base = {"mean_diff": 0.004, "positive_folds": 7}
    assert exp012.classify(base, 0.01, 0.002) == "SUPPORTED"
    assert exp012.classify(base, 0.20, 0.002) == "NOT_SUPPORTED"
    assert exp012.classify({"mean_diff": -0.001, "positive_folds": 8}, 0.01, 0.002) == "NOT_SUPPORTED"
    assert exp012.classify({"mean_diff": 0.004, "positive_folds": 4}, 0.01, 0.002) == "FRAGILE"
    assert exp012.classify(base, 0.01, -0.001) == "FRAGILE"          # a placebo reproduced it


def test_saved_artifact_reloads_in_a_fresh_process_and_scores_finite_numbers(tmp_path):
    frame = synthetic()
    path = exp012.train_artifact(frame, "A0", tmp_path, fingerprint="test-fingerprint")
    code = (
        "import sys, numpy as np, pandas as pd;"
        "from src.quant.study import exp012;"
        f"b = exp012.load_artifact(r'{path}');"
        "f = pd.DataFrame(np.random.default_rng(0).uniform(-1, 1, (5, len(b['features']))), columns=b['features']);"
        "s = exp012.predict_with_artifact(b, f);"
        "assert len(s) == 5 and np.isfinite(s).all() and b['status'].startswith('RESEARCH ARTIFACT');"
        "print('ok', b['trained_rows'])"
    )
    done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0 and "ok" in done.stdout, done.stderr[-400:]


def test_inference_refuses_missing_columns_and_infinite_values(tmp_path):
    frame = synthetic()
    bundle = exp012.load_artifact(exp012.train_artifact(frame, "A0", tmp_path, fingerprint="t"))
    with pytest.raises(ValueError, match="missing"):
        exp012.predict_with_artifact(bundle, frame.drop(columns=[exp012.BASELINE[0]]))
    bad = frame.copy()
    bad.loc[bad.index[0], exp012.BASELINE[0]] = np.inf
    with pytest.raises(ValueError, match="infinite"):
        exp012.predict_with_artifact(bundle, bad)
    ok = frame.copy()
    ok.loc[ok.index[0], exp012.BASELINE[0]] = np.nan                 # missing values are imputed as in training
    assert np.isfinite(exp012.predict_with_artifact(bundle, ok)).all()


def _gate_inputs(tmp_path, *, a0=0.005, a1=0.015, parent=(0.005, 0.015)):
    """A frame, predictions and reports shaped like run_study's, with a parent metrics file on disk."""
    (tmp_path / "experiments" / "EXP-011").mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"arm": ["E0", "E1", "E3"], "seed": [0, 0, 0], "mean_rank_ic": [parent[0], parent[1], 0.02]}).to_csv(tmp_path / exp012.PARENT_METRICS, index=False)
    frame = synthetic(n_dates=4, n_names=3)
    pred = frame[["date", "symbol"]].assign(prediction=np.linspace(-1, 1, len(frame)))
    predictions = {("A0", 0): pred, ("A1", 0): pred.copy()}
    reports = {("A0", 0): {"mean_rank_ic": a0}, ("A1", 0): {"mean_rank_ic": a1}}
    return frame, predictions, reports


def test_acceptance_gate_passes_when_the_parent_numbers_are_reproduced(tmp_path):
    frame, predictions, reports = _gate_inputs(tmp_path, a0=0.005 + 3e-17, a1=0.015 - 4e-17)
    checks = exp012.acceptance_checks(tmp_path, frame, predictions, reports)
    assert checks["predictions_finite"] and max(checks["reproduction_abs_difference"].values()) < 1e-9


def test_acceptance_gate_aborts_on_a_reproduction_difference(tmp_path):
    frame, predictions, reports = _gate_inputs(tmp_path, a1=0.015 + 1e-6)
    with pytest.raises(RuntimeError, match="do not reproduce"):
        exp012.acceptance_checks(tmp_path, frame, predictions, reports)


def test_acceptance_gate_aborts_on_a_non_finite_prediction_or_a_late_row(tmp_path):
    frame, predictions, reports = _gate_inputs(tmp_path)
    predictions[("A1", 0)].loc[predictions[("A1", 0)].index[0], "prediction"] = np.nan
    with pytest.raises(RuntimeError, match="non-finite"):
        exp012.acceptance_checks(tmp_path, frame, predictions, reports)
    frame, predictions, reports = _gate_inputs(tmp_path)
    frame.loc[frame.index[-1], "date"] = (exp012.LAST_PANEL_DATE + pd.Timedelta(days=1)).date()
    with pytest.raises(RuntimeError, match="after the registered end"):
        exp012.acceptance_checks(tmp_path, frame, predictions, reports)


def test_acceptance_gate_skips_reproduction_in_a_rehearsal_but_still_checks_finiteness(tmp_path):
    frame, predictions, reports = _gate_inputs(tmp_path, a0=0.9, a1=-0.9)          # would fail a real run
    assert exp012.acceptance_checks(tmp_path, frame, predictions, reports, rehearsal=True)["reproduction"].startswith("skipped")
    predictions[("A0", 0)].loc[predictions[("A0", 0)].index[0], "prediction"] = np.inf
    with pytest.raises(RuntimeError, match="non-finite"):
        exp012.acceptance_checks(tmp_path, frame, predictions, reports, rehearsal=True)


def test_the_registration_document_embeds_the_current_fingerprint():
    doc = ROOT / exp012.PREREG_DOC
    if not doc.exists():
        pytest.skip("not registered yet")
    assert f"Definition fingerprint: `{exp012.definition_fingerprint(ROOT)}`" in doc.read_text(encoding="utf-8")
