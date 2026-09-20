from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.quant.model_lab.aggregate import complete_outer_records, load_outer_predictions
from src.quant.model_lab.ensemble import equal_weight_rank_average, prediction_rank_correlation
from src.quant.model_lab.evaluation import prediction_hash
from src.quant.model_lab.inner_cv import assert_outer_isolation, build_inner_plan
from src.quant.model_lab.registry import TrialRecord, TrialRegistry, TrialStatus
from src.quant.model_lab.report import build_summary
from src.quant.model_lab.robustness import distribution, overfit_flag
from src.quant.model_lab.runner import load_dataset
from src.quant.model_lab.search_space import FAMILIES, build_spec, families
from src.quant.study.firewall import FIREWALL, HoldoutBreach


def _frame(dates: int = 180, names: int = 4) -> pd.DataFrame:
    days = pd.bdate_range("2018-01-01", periods=dates)
    return pd.DataFrame([
        {"date": day, "symbol": f"S{name}", "fwd_rank_21": name / names}
        for day in days for name in range(names)
    ])


def _record(trial_id: str = "MLT-ONE", status: TrialStatus = TrialStatus.COMPLETE) -> TrialRecord:
    return TrialRecord(
        trial_id=trial_id, phase="INNER_SELECTION", model_family="linear",
        model_name="ridge", dataset_id="ds", dataset_hash="hash",
        data_integrity_status="VALIDATED_UNAFFECTED_BLOCK",
        feature_set_id="F0", feature_hash="fh", hyperparameters={"alpha": 1.0},
        seed=0, outer_fold=0, inner_cv_scheme="temporal", git_commit="abc",
        device="MAC_CPU", status=status,
    )


def test_inner_temporal_splits_are_ordered_purged_and_outer_isolated():
    frame = _frame()
    outer_validation = _frame(20).assign(date=lambda x: x["date"] + pd.Timedelta(days=1000))
    plan = build_inner_plan(frame, validation_dates=20, gap_observation_dates=6, min_train_dates=80)
    assert len(plan.splits) == 3
    for split in plan:
        train, validation = split.split(frame)
        assert pd.to_datetime(train.date).max() < pd.to_datetime(validation.date).min()
        unique = pd.DatetimeIndex(sorted(pd.to_datetime(frame.date).unique()))
        train_pos = unique.get_loc(split.train_end)
        validation_pos = unique.get_loc(split.validation_start)
        assert validation_pos - train_pos - 1 == 6
    assert_outer_isolation(plan, outer_validation)


def test_real_outer_fold_zero_supports_exactly_three_inner_splits():
    from src.quant.study import exp009b

    frame, _ = load_dataset()
    outer_train, _ = exp009b.recorded_plan().folds[0].split(frame)
    assert len(build_inner_plan(outer_train).splits) == 3


def test_outer_overlap_is_rejected():
    frame = _frame()
    plan = build_inner_plan(frame, validation_dates=20, gap_observation_dates=6, min_train_dates=80)
    outer = pd.DataFrame({"date": [plan.splits[-1].validation_end], "symbol": ["X"]})
    with pytest.raises(RuntimeError, match="overlaps"):
        assert_outer_isolation(plan, outer)


def test_trial_registry_is_resume_safe_and_retains_failures(tmp_path):
    registry = TrialRegistry(tmp_path / "trials.sqlite")
    complete = _record()
    failed = _record("MLT-TWO", TrialStatus.FAILED)
    registry.put(complete)
    registry.put(failed)
    assert registry.completed(complete.trial_id)
    assert not registry.completed(failed.trial_id)
    assert registry.summary()["statuses"]["FAILED"] == 1
    registry.put(complete.model_copy(update={"metrics": {"mean_inner_rank_ic": 0.01}}))
    assert len(registry.records()) == 2
    assert registry.get(complete.trial_id).metrics["mean_inner_rank_ic"] == 0.01


def test_commit_invalidation_is_one_way_and_requires_a_reason(tmp_path):
    registry = TrialRegistry(tmp_path / "trials.sqlite")
    registry.put(_record("MLT-OLD"))
    assert registry.invalidate_commit("abc", reason="outer fold consumed by smoke") == 1
    invalid = registry.get("MLT-OLD")
    assert invalid is not None and invalid.status is TrialStatus.INVALID
    assert invalid.error == "outer fold consumed by smoke"
    assert registry.invalidate_commit("abc", reason="repeat audit") == 0
    with pytest.raises(ValueError, match="reason"):
        registry.invalidate_commit("abc", reason="  ")


def test_campaign_aggregation_refuses_partial_outer_folds(tmp_path):
    registry = TrialRegistry(tmp_path / "trials.sqlite")
    for fold in range(7):
        registry.put(_record(f"MLT-OUTER-{fold}").model_copy(update={
            "phase": "OUTER_EVALUATION", "outer_fold": fold,
        }))
    with pytest.raises(RuntimeError, match="all eight"):
        complete_outer_records(registry, "ridge", method_commit="abc")


def test_outer_prediction_loader_verifies_hashes_and_fold_identity(tmp_path):
    registry = TrialRegistry(tmp_path / "trials.sqlite")
    prediction_root = tmp_path / "data/research/model_lab/predictions"
    prediction_root.mkdir(parents=True)
    for fold in range(8):
        trial_id = f"MLT-OUTER-{fold}"
        frame = pd.DataFrame({
            "date": pd.to_datetime([f"2020-{fold + 1:02d}-03"]),
            "symbol": ["A"], "outer_fold": [fold],
            "prediction": [float(fold)], "fwd_rank_21": [0.0],
        })
        digest = prediction_hash(frame)
        frame.to_parquet(prediction_root / f"{trial_id}.parquet", index=False)
        registry.put(_record(trial_id).model_copy(update={
            "phase": "OUTER_EVALUATION", "outer_fold": fold,
            "prediction_hash": digest,
        }))
    records = complete_outer_records(registry, "ridge", method_commit="abc")
    combined = load_outer_predictions(records, root=tmp_path)
    assert len(combined) == 8
    assert sorted(combined["outer_fold"].unique()) == list(range(8))


def test_published_summary_keeps_noncomplete_trial_provenance(tmp_path):
    registry = TrialRegistry(tmp_path / "trials.sqlite")
    registry.put(_record("MLT-COMPLETE"))
    registry.put(_record("MLT-INVALID", TrialStatus.INVALID).model_copy(update={
        "error": "superseded implementation smoke",
    }))
    summary = build_summary(registry)
    assert summary["statuses"]["INVALID"] == 1
    assert summary["retained_noncomplete_trials"][0]["trial_id"] == "MLT-INVALID"
    assert summary["retained_noncomplete_trials"][0]["error"] == "superseded implementation smoke"


def test_trial_identity_is_deterministic_and_parameter_sensitive():
    one = TrialRecord.identity(model="ridge", params={"alpha": 1.0}, fold=0)
    same = TrialRecord.identity(fold=0, params={"alpha": 1.0}, model="ridge")
    other = TrialRecord.identity(model="ridge", params={"alpha": 10.0}, fold=0)
    assert one == same
    assert one != other


def test_prediction_hash_is_order_invariant_and_value_sensitive():
    rows = pd.DataFrame({
        "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
        "symbol": ["A", "B"], "outer_fold": [0, 0],
        "prediction": [0.1, 0.2], "fwd_rank_21": [-0.5, 0.5],
    })
    assert prediction_hash(rows) == prediction_hash(rows.iloc[::-1])
    changed = rows.copy(); changed.loc[0, "prediction"] = 0.11
    assert prediction_hash(rows) != prediction_hash(changed)


def test_declared_search_space_has_no_duplicate_model_names_and_routes_every_family():
    names = [family.model_name for family in FAMILIES]
    assert len(names) == len(set(names))
    assert {row["route"] for row in families()} >= {"MAC_CPU", "KAGGLE_GPU", "POST_OUTER"}
    assert all(row["status"] in {"READY", "BLOCKED"} for row in families())


def test_local_factory_refuses_a_gpu_family_instead_of_falling_back():
    with pytest.raises(RuntimeError, match="not executable"):
        build_spec("xgboost", {}, 0, suffix="test")


@pytest.mark.parametrize("name,params", [
    ("huber", {"epsilon": 1.2, "alpha": 1e-4}),
    ("sgd_huber", {"epsilon": 0.1, "alpha": 1e-4}),
    ("pca_ridge", {"variance": 0.9, "alpha": 10.0}),
    ("pls", {"components": 2}),
])
def test_model_lab_adapters_are_reproducible(name, params):
    rng = np.random.default_rng(7)
    X = rng.normal(size=(120, 6)); y = rng.normal(size=120)
    first = build_spec(name, params, 3, suffix="a").build().fit(X, y).predict(X)
    second = build_spec(name, params, 3, suffix="b").build().fit(X, y).predict(X)
    assert np.all(np.isfinite(first))
    assert np.allclose(first, second)


def test_ensemble_requires_oof_inputs_and_preserves_keys():
    base = pd.DataFrame({
        "date": pd.to_datetime(["2020-01-01"] * 3), "symbol": ["A", "B", "C"],
        "outer_fold": [0] * 3, "fwd_rank_21": [-1.0, 0.0, 1.0],
    })
    a = base.assign(prediction=[-0.2, 0.1, 0.3])
    b = base.assign(prediction=[-0.1, 0.2, 0.4])
    out = equal_weight_rank_average({"a": a, "b": b})
    assert list(out.columns) == ["date", "symbol", "outer_fold", "fwd_rank_21", "prediction"]
    assert prediction_rank_correlation({"a": a, "b": b}).loc["a", "b"] == pytest.approx(1.0)
    with pytest.raises(ValueError):
        equal_weight_rank_average({"a": a})


def test_robustness_reports_full_distribution_and_overfit_gap():
    result = distribution(range(10))
    assert result["n"] == 10 and result["min"] == 0 and result["max"] == 9
    assert overfit_flag(0.20, 0.01)["overfit_warning"] is True


def test_model_lab_dataset_is_revenue_unaffected_and_holdout_excluded():
    frame, metadata = load_dataset()
    assert metadata["integrity_status"] == "VALIDATED_UNAFFECTED_BLOCK"
    assert metadata["revenue_affected_feature_sets"] == "BLOCKED"
    assert frame["date"].max() < date(2025, 8, 26)
    assert metadata["holdout_touched"] is False


def test_holdout_rows_raise_with_no_model_lab_override():
    FIREWALL.arm_window(date(2025, 8, 26), date(2026, 8, 28))
    with pytest.raises(HoldoutBreach):
        FIREWALL.assert_clear(
            pd.DataFrame({"date": pd.to_datetime(["2025-08-26"])}),
            context="MODEL-LAB test",
        )
