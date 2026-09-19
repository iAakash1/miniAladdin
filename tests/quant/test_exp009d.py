"""EXP-009D: the duplicate-axis hygiene study."""

from pathlib import Path

import pytest

from src.quant.study import exp009b
from src.quant.study import exp009d as D
from src.quant.study import prereg

REPO = Path(__file__).resolve().parents[2]


def test_it_drops_exactly_one_feature_and_keeps_its_twin():
    full, dedup = exp009b.FEATURES, D.DEFINITION["data"]["features_dedup"]
    assert len(full) == 27 and len(dedup) == 26
    assert set(full) - set(dedup) == {D.DROPPED}
    assert D.KEPT in dedup and D.DROPPED not in dedup


def test_the_frozen_experiments_keep_their_27_features():
    assert len(exp009b.FEATURES) == 27 and D.DROPPED in exp009b.FEATURES


@pytest.mark.parametrize("d_ic, se, d_sharpe, ratio, label", [
    (0.0005, 0.0003, 0.02, 1.00, "EQUIVALENT"),
    (0.0040, 0.0010, 0.02, 1.00, "EQUIVALENT"),          # inside the noise-floor margins
    (0.0060, 0.0003, 0.02, 1.00, "DIFFERENT"),          # mean outside +-0.005
    (0.0010, 0.0055, 0.02, 1.00, "DIFFERENT"),          # interval too wide to call equivalent
    (0.0005, 0.0003, 0.25, 1.00, "DIFFERENT"),          # economics moved
    (0.0005, 0.0003, 0.02, 1.25, "DIFFERENT"),          # turnover moved
])
def test_equivalence_needs_both_ordering_and_economics(d_ic, se, d_sharpe, ratio, label):
    out = D.classify({"mean_difference": d_ic, "hac_se": se}, {"net_sharpe_difference": d_sharpe, "turnover_ratio": ratio})
    assert out["classification"] == label
    assert out["promotion"] == "NOT ASSESSED"


def test_the_margins_are_wider_than_the_noise_exp009b_measured_for_a_no_information_change():
    """EXP-009B: a different bagging implementation moved IC by 0.0031 and net Sharpe by 0.067."""
    assert 0.005 > 0.0031 and 0.20 > 0.067


def test_the_seed_reference_arm_enters_no_criterion():
    arms = {a["id"]: a for a in D.DEFINITION["arms"]}
    assert arms["NOISE"]["seed"] == 1 and arms["FULL"]["seed"] == arms["DEDUP"]["seed"] == 0
    assert "enters no criterion" in arms["NOISE"]["role"]
    assert D.DEFINITION["trials"]["cumulative_evaluations"] == 166


def test_run_study_calls_the_gate_first(tmp_path, monkeypatch):
    for name in D.METHOD_SOURCES:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((REPO / name).read_text())
    touched = []
    monkeypatch.setattr(exp009b, "load_frame", lambda *a, **k: touched.append(1))
    with pytest.raises(prereg.PreregistrationError):
        D.run_study(tmp_path)
    assert touched == []


def test_the_frozen_panel_really_holds_a_perfect_anticorrelation():
    import pandas as pd
    path = REPO / exp009b.FRAME_CACHE
    if not path.exists():
        pytest.skip("frozen panel not built locally")
    frame = pd.read_parquet(path, columns=["in_universe", D.DROPPED, D.KEPT])
    rows = frame[frame["in_universe"]]
    assert abs(float(rows[[D.DROPPED, D.KEPT]].corr().iloc[0, 1])) >= 0.99999


def test_run_study_end_to_end_on_synthetic_data(tmp_path, monkeypatch):
    import json
    from datetime import date
    from src.quant.study import exp009a
    from tests.quant.test_exp009b import synthetic_world, synthetic_plan

    frame, dates = synthetic_world(n_symbols=120, n_dates=120)
    frame[D.DROPPED] = -frame[D.KEPT]                      # an exact anti-duplicate, as in the real panel
    monkeypatch.setattr(D, "prereg_gate", lambda root, **k: {"definition_fingerprint": "0" * 64})
    monkeypatch.setattr(exp009b, "arm_firewall", lambda root: (date(2030, 1, 1), date(2030, 12, 31)))
    monkeypatch.setattr(exp009b, "load_frame", lambda root: (frame, {
        "dataset_version": D.DEFINITION["data"]["dataset_id"], "content_hash": "x"}))
    monkeypatch.setattr(exp009a, "panel_content_hash", lambda p: D.DEFINITION["data"]["returns_panel_sha256"])
    monkeypatch.setattr(exp009b, "recorded_plan", lambda root: synthetic_plan(dates))
    monkeypatch.setattr(exp009b, "reproduce_frozen", lambda root, refit: {"passed": True, "max_abs_prediction_difference": 0.0})
    real_spec = D.ModelSpec
    monkeypatch.setattr(D, "ModelSpec", lambda name, kind, params, seed: real_spec(
        name, kind, (("n_estimators", 8), ("min_samples_leaf", 20)), seed))
    out = D.run_study(REPO, output=tmp_path / "out")
    assert out["criteria"]["classification"] in {"EQUIVALENT", "DIFFERENT"}
    metrics = json.loads((tmp_path / "out" / "metrics.json").read_text())
    assert set(metrics["cells"]) == {"FULL", "DEDUP", "NOISE"}
    assert "noise_reference" in metrics and "paired_ic" in metrics["noise_reference"]
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text())
    assert manifest["holdout"]["touched"] is False and "/Users/" not in json.dumps(manifest)
    assert manifest["validity_checks"]["duplicate_is_exact"] is True


def test_a_panel_without_the_duplicate_is_refused(tmp_path, monkeypatch):
    from datetime import date
    from src.quant.study import exp009a
    from tests.quant.test_exp009b import synthetic_world

    frame, _ = synthetic_world(n_symbols=120, n_dates=20)            # the two columns are independent noise
    monkeypatch.setattr(D, "prereg_gate", lambda root, **k: {"definition_fingerprint": "0" * 64})
    monkeypatch.setattr(exp009b, "arm_firewall", lambda root: (date(2030, 1, 1), date(2030, 12, 31)))
    monkeypatch.setattr(exp009b, "load_frame", lambda root: (frame, {
        "dataset_version": D.DEFINITION["data"]["dataset_id"], "content_hash": "x"}))
    monkeypatch.setattr(exp009a, "panel_content_hash", lambda p: D.DEFINITION["data"]["returns_panel_sha256"])
    with pytest.raises(RuntimeError, match="INVALID"):
        D.run_study(REPO, output=tmp_path / "out")
