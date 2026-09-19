"""EXP-011: the design is fixed, the rule is mechanical, receipts are verified, and the pipeline runs (synthetic inputs only)."""

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.quant.pit import rich_panel as R
from src.quant.pit.calendar import TradingCalendar
from src.quant.study import exp009b, exp010a, exp010b, exp011 as E, prereg
from src.quant.study.firewall import reset_for_tests

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def clean_firewall():
    reset_for_tests()
    yield
    reset_for_tests()


# ── the design ──────────────────────────────────────────────────────────────

def test_the_design_is_the_registered_two_by_two_with_ten_seeds():
    assert set(E.ARMS) == {"E0", "E1", "E2", "E3"}
    assert (E.ARMS["E0"]["features"], E.ARMS["E0"]["model"]) == ("baseline", "ridge")
    assert (E.ARMS["E1"]["features"], E.ARMS["E1"]["model"]) == ("rich", "ridge")
    assert (E.ARMS["E2"]["features"], E.ARMS["E2"]["model"]) == ("baseline", "gradient_boosting")
    assert (E.ARMS["E3"]["features"], E.ARMS["E3"]["model"]) == ("rich", "gradient_boosting")
    assert E.ARMS["E3"]["seeds"] == tuple(range(10)) and E.ARMS["E2"]["fit"] is False and E.FIT_ORDER == ("E0", "E1", "E3")
    assert E.LABEL == "fwd_rank_21" and E.DEFINITION["design"]["target_unchanged"] is True
    assert E.ARMS["E2"]["params"] == E.ARMS["E3"]["params"] == exp010a.HYPERPARAMETERS
    assert E.DEFINITION["design"]["no_other_models"] and E.DEFINITION["portfolio"]["cadence_retuned"] is False
    assert E.DEFINITION["holdout"]["touched"] is False and E.ECONOMICS_ARM == "B1"


def test_noise_units_are_exp010a_and_the_rule_states_no_later_threshold():
    assert E.IC_SPAN == pytest.approx(0.004156) and E.IC_SD == pytest.approx(0.001583) and E.SHARPE_SD == pytest.approx(0.081651)
    assert E.INTERPRETATION["no_threshold_invented_later"] is True and E.INTERPRETATION["promotion"] == "NOT ASSESSED"


def test_e2_is_the_frozen_exp010a_and_never_refit():
    assert E.ARMS["E2"]["fit"] is False and "EXP-010A" in E.DEFINITION["design"]["e2_is_exp010a"]


def test_baseline_features_are_exactly_the_frozen_twenty_six():
    assert tuple(E.feature_list("baseline")) == tuple(exp010a.FEATURES) == R.BASELINE_FEATURES


# ── the rule ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("diffs,expected", [
    ([0.006] * 10, "IMPROVES"),
    ([0.006] * 8 + [-0.001, 0.0], "NO_DETECTABLE_CHANGE"),          # only 8 of 10 positive
    ([0.006] * 9 + [-0.002], "IMPROVES"),
    ([0.003] * 10, "NO_DETECTABLE_CHANGE"),                          # consistent but below the reseed range
    ([-0.006] * 10, "DEGRADES"),
    ([0.006, -0.006] * 5, "NO_DETECTABLE_CHANGE"),
])
def test_boosted_pair_status(diffs, expected):
    assert E.pair_status(diffs) == expected


def test_linear_pair_status_uses_folds():
    assert E.pair_status([0.006], [0.01, 0.01, 0.01, 0.01, 0.01, -0.01, -0.01, -0.01]) == "IMPROVES"
    assert E.pair_status([0.006], [0.01, 0.01, -0.01, -0.01, -0.01, -0.01, 0.01, 0.01]) == "NO_DETECTABLE_CHANGE"
    assert E.pair_status([-0.006], [-0.01] * 5 + [0.01] * 3) == "DEGRADES"


@pytest.mark.parametrize("boosted,linear,robust,label", [
    ("IMPROVES", "IMPROVES", True, "RICH_DATA_IMPROVES_ORDERING"),
    ("IMPROVES", "NO_DETECTABLE_CHANGE", True, "IMPROVES_ONLY_WITH_BOOSTING"),
    ("IMPROVES", "NO_DETECTABLE_CHANGE", False, "MIXED"),
    ("IMPROVES", "DEGRADES", True, "MIXED"),
    ("NO_DETECTABLE_CHANGE", "IMPROVES", False, "IMPROVES_ONLY_LINEAR"),
    ("DEGRADES", "IMPROVES", False, "MIXED"),
    ("NO_DETECTABLE_CHANGE", "NO_DETECTABLE_CHANGE", False, "NO_DETECTABLE_ORDERING_GAIN"),
    ("DEGRADES", "NO_DETECTABLE_CHANGE", False, "RICH_DATA_DEGRADES_ORDERING"),
    ("NO_DETECTABLE_CHANGE", "DEGRADES", False, "RICH_DATA_DEGRADES_ORDERING"),
])
def test_label_table(boosted, linear, robust, label):
    assert E.classify(boosted, linear, robust) == label
    assert label in E.INTERPRETATION["labels"]


def test_fold_robustness_needs_five_positive_folds_and_positive_leave_one_out():
    good = np.tile([0.01, 0.01, 0.01, 0.01, 0.01, -0.02, -0.02, 0.0], (10, 1))
    assert E.fold_robust(good, E.leave_one_fold_out_median(good)) is False      # removing one strong fold flips a mean
    spread = np.tile([0.01] * 8, (10, 1))
    assert E.fold_robust(spread, E.leave_one_fold_out_median(spread)) is True
    one_fold = np.tile([0.2, -0.01, -0.01, -0.01, -0.01, -0.01, -0.01, -0.01], (10, 1))
    assert E.fold_robust(one_fold, E.leave_one_fold_out_median(one_fold)) is False


def test_pairing_is_rich_minus_base_and_broadcast_repeats_the_deterministic_fit():
    rows = E.paired([{"seed": 0, "mean_rank_ic": 0.03}], [{"seed": 0, "mean_rank_ic": 0.035}], ["mean_rank_ic"])
    assert rows[0]["difference"] == pytest.approx(0.005)
    assert [r["seed"] for r in E.broadcast({"x": 1}, [0, 1, 2])] == [0, 1, 2]


def test_context_expresses_effects_in_exp010a_noise_units():
    out = E.context(E.IC_SD, E.SHARPE_SD)
    assert out["delta_ic_in_seed_sds"] == pytest.approx(1.0) and out["delta_net_sharpe_in_seed_sds"] == pytest.approx(1.0)


# ── receipts and imports ────────────────────────────────────────────────────

def synthetic_predictions(seed=0, folds=8):
    rng = np.random.default_rng(seed)
    rows = [(date(2018, 1, 1 + i % 28), f"S{j:02d}", i % folds, rng.uniform(-1, 1), rng.normal()) for i in range(80) for j in range(12)]
    return pd.DataFrame(rows, columns=["date", "symbol", "fold", E.LABEL, "prediction"])


def good_receipt(predictions, fingerprint="f" * 64):
    return {"experiment_id": "EXP-011", "arm": "E3", "seed": 4, "definition_fingerprint": fingerprint, "rich_dataset_id": E.RICH_DATASET_ID,
            "rich_content_hash": E.RICH_CONTENT_HASH, "rich_feature_hash": E.RICH_FEATURE_HASH, "folds": 8,
            "prediction_sha256": exp010a._prediction_hash(predictions), "git_commit": "abc", "device": "cpu", "fit_seconds": 1.0,
            "dependency_versions": json.loads((REPO / "experiments/EXP-010A/manifest.json").read_text())["dependency_versions"]}


def test_a_matching_receipt_is_accepted_and_every_mismatch_is_rejected():
    predictions = synthetic_predictions()
    receipt = good_receipt(predictions)
    assert E.verify_receipt(receipt, predictions, arm="E3", seed=4, fingerprint="f" * 64) == []
    for change in ({"definition_fingerprint": "0" * 64}, {"seed": 5}, {"arm": "E1"}, {"rich_content_hash": "0" * 64},
                   {"rich_feature_hash": "0" * 64}, {"prediction_sha256": "0" * 64}, {"git_commit": ""}, {"device": ""}):
        assert E.verify_receipt({**receipt, **change}, predictions, arm="E3", seed=4, fingerprint="f" * 64), change
    drift = {**receipt, "dependency_versions": {**receipt["dependency_versions"], "sklearn": "0.0.1"}}
    assert any("sklearn" in p for p in E.verify_receipt(drift, predictions, arm="E3", seed=4, fingerprint="f" * 64))
    assert E.verify_receipt(drift, predictions, arm="E3", seed=4, fingerprint="f" * 64, strict_versions=False) == []


def test_a_tampered_prediction_file_fails_the_hash_and_missing_folds_fail():
    predictions = synthetic_predictions()
    receipt = good_receipt(predictions)
    tampered = predictions.copy(); tampered.loc[0, "prediction"] += 1e-6
    assert any("hash" in p for p in E.verify_receipt(receipt, tampered, arm="E3", seed=4, fingerprint="f" * 64))
    few = predictions[predictions["fold"] < 6]
    assert any("eight folds" in p for p in E.verify_receipt({**good_receipt(few), "folds": 6}, few, arm="E3", seed=4, fingerprint="f" * 64))


def test_load_checkpoint_refuses_a_mismatched_run(tmp_path):
    predictions = synthetic_predictions()
    parquet, receipt_path = E.checkpoint_paths(tmp_path, "E3", 4)
    exp010a._atomic_parquet(parquet, predictions)
    exp010a._atomic_json(receipt_path, good_receipt(predictions, "a" * 64))
    assert E.load_checkpoint(tmp_path, "E3", 4, "a" * 64) is not None
    with pytest.raises(RuntimeError, match="rejected"):
        E.load_checkpoint(tmp_path, "E3", 4, "b" * 64)
    assert E.load_checkpoint(tmp_path, "E3", 5, "a" * 64) is None


def test_the_gate_precedes_any_data_read(monkeypatch, tmp_path):
    touched = []
    monkeypatch.setattr(E, "load_rich_panel", lambda *a, **k: touched.append(1))
    monkeypatch.setattr(E, "prereg_gate", lambda *a, **k: (_ for _ in ()).throw(prereg.PreregistrationError("missing")))
    with pytest.raises(prereg.PreregistrationError):
        E.run_study(tmp_path)
    assert touched == []


def test_a_missing_rich_panel_is_refused_with_the_rebuild_command(tmp_path):
    with pytest.raises(FileNotFoundError, match="build-rich-panel"):
        E.load_rich_panel(REPO, path=tmp_path / "absent.parquet")


# ── the pipeline on synthetic data ──────────────────────────────────────────

def _synthetic_world(monkeypatch, tmp_path):
    rng = np.random.default_rng(1)
    sessions = [d.date() for d in pd.bdate_range("2014-04-01", "2025-06-30")]
    calendar = TradingCalendar.from_dates(sessions)
    plan = exp009b.recorded_plan(REPO)
    first_validation = plan.folds[0].validation_start
    grid_start = next(i for i, d in enumerate(sessions) if d >= first_validation)
    grid = sessions[grid_start % 5:sessions.index(date(2025, 5, 9)) + 1:5]
    symbols = [f"S{i:02d}" for i in range(30)]
    dates_all = [d for d in grid]
    xs_new = [f"{n}_xs" for n in R.NEW_FEATURES]
    rows = []
    for d in dates_all:
        for s in symbols:
            rows.append((d, s))
    panel = pd.DataFrame(rows, columns=["date", "symbol"])
    for name in R.BASELINE_FEATURES:
        panel[name] = rng.normal(size=len(panel))
    for name in xs_new:
        column = rng.normal(size=len(panel)); column[rng.random(len(panel)) < 0.3] = np.nan
        panel[name] = column
    panel["fwd_rank_21"] = rng.uniform(-1, 1, len(panel)); panel["fwd_ret_5"] = rng.normal(0, .02, len(panel)); panel["fwd_ret_21"] = rng.normal(0, .04, len(panel))
    panel["dollar_volume"] = 1e7; panel["in_universe"] = True; panel["close"] = 50.0
    panel["security_id"] = "sid"; panel["cik"] = 1; panel["identity_grade"] = "A_CONFIRMED"
    panel["ff12"] = "BusEq"; panel["ff17"] = "x"; panel["ff48"] = "y"; panel["sic"] = 3571
    daily = pd.DataFrame([(pd.Timestamp(d), s) for d in sessions for s in symbols], columns=["date", "symbol"])
    daily["dollar_volume"] = 5e7; daily["fwd_ret_5"] = rng.normal(0, .02, len(daily)); daily["fwd_ret_21"] = rng.normal(0, .04, len(daily)); daily["in_universe"] = True
    daily = daily[daily["date"].dt.date <= date(2025, 5, 9)]
    calendar_capped = TradingCalendar.from_dates([d for d in sessions if d <= date(2025, 5, 9)])

    def e2_predictions(seed, root=Path(".")):
        frame = panel[["date", "symbol"]].copy()
        frame["fold"] = [next((f.index for f in plan.folds if f.validation_start <= d <= f.validation_end), -1) for d in frame["date"]]
        frame = frame[frame["fold"] >= 0].copy()
        frame[E.LABEL] = panel.loc[frame.index, E.LABEL].to_numpy()
        frame["prediction"] = np.random.default_rng(50 + seed).normal(size=len(frame))
        return frame

    monkeypatch.setattr(E, "RICH_FEATURES", tuple(xs_new))
    monkeypatch.setattr(E, "load_rich_panel", lambda *a, **k: (panel, {"synthetic": True}))
    monkeypatch.setattr(E, "prereg_gate", lambda *a, **k: {"preregistration_document": "synthetic", "preregistration_sha256": "0" * 64})
    monkeypatch.setattr(exp010b, "verify_parent_artifacts", lambda *a, **k: {"passed": True, "checks": {}})
    monkeypatch.setattr(exp010b, "load_seed_predictions", e2_predictions)
    monkeypatch.setattr(exp010b, "build_daily_panel", lambda *a, **k: (daily, calendar_capped))
    first = e2_predictions(0)["date"].min(); last = e2_predictions(0)["date"].max()
    monkeypatch.setattr(exp010b, "FIRST_PREDICTION_DATE", first)
    monkeypatch.setattr(exp010b, "LAST_PREDICTION_DATE", last)
    tiny = {"n_estimators": 3, "learning_rate": 0.1, "max_depth": 2, "subsample": 0.7, "min_samples_leaf": 20}
    monkeypatch.setitem(E.ARMS["E3"], "params", tiny)
    monkeypatch.setattr(E, "definition_fingerprint", lambda *a, **k: "f" * 64)
    return tmp_path / "out"


def test_the_pipeline_runs_end_to_end_and_writes_only_aggregates(monkeypatch, tmp_path):
    out = _synthetic_world(monkeypatch, tmp_path)
    result = E.run_study(REPO, output=out, workers=1)
    names = sorted(p.name for p in out.iterdir() if p.is_file())
    assert names == sorted(["definition.json", "config.json", "manifest.json", "metrics.json", "per_arm_metrics.csv", "fold_metrics.csv",
                            "paired_differences.csv", "prediction_hashes.json"])
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["holdout"]["touched"] is False and manifest["best_seed_selected"] is False and manifest["completion"] == "COMPLETE"
    per_arm = pd.read_csv(out / "per_arm_metrics.csv")
    assert {(a, s) for a, s in zip(per_arm["arm"], per_arm["seed"])} == {("E0", 0), ("E1", 0), *{("E2", s) for s in range(10)}, *{("E3", s) for s in range(10)}}
    metrics = json.loads((out / "metrics.json").read_text())
    assert metrics["classification"]["label"] in E.INTERPRETATION["labels"] and metrics["classification"]["economics_labelled"] is False
    assert len(metrics["fold_delta_ic"]["boosted_seed_median_by_fold"]) == 8
    paired = pd.read_csv(out / "paired_differences.csv")
    assert {"data_value_boosted", "data_value_linear", "model_value_baseline", "model_value_rich"} <= set(paired["comparison"])
    boosted = paired[(paired["comparison"] == "data_value_boosted") & (paired["metric"] == "mean_rank_ic")]
    assert len(boosted) == 10 and (boosted["difference"] - (boosted["rich"] - boosted["base"])).abs().max() < 1e-12
    assert result["analysis"]["classification"]["promotion"] == "NOT ASSESSED"


def test_a_second_run_resumes_from_verified_checkpoints_without_refitting(monkeypatch, tmp_path):
    out = _synthetic_world(monkeypatch, tmp_path)
    E.run_study(REPO, output=out, workers=1)
    calls = []
    original = E.fit_arm_seed
    monkeypatch.setattr(E, "fit_arm_seed", lambda *a, **k: calls.append(a[:2]) or original(*a, **k))
    E.run_study(REPO, output=out, workers=1)
    assert calls == []
