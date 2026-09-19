"""EXP-010A definition, gate ordering, determinism, and synthetic path."""

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.quant.study import exp009b, exp010a as A, prereg
from src.quant.study.firewall import reset_for_tests
from tests.quant.test_exp009b import synthetic_plan, synthetic_world

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def clean_firewall():
    reset_for_tests()
    yield
    reset_for_tests()


def test_definition_is_exactly_the_registered_noise_floor():
    assert A.SEEDS == tuple(range(10))
    assert len(A.FEATURES) == 26 and "max_drawdown_252_xs" not in A.FEATURES
    assert A.HYPERPARAMETERS == {"n_estimators": 200, "learning_rate": 0.03, "max_depth": 3, "subsample": 0.7, "min_samples_leaf": 50}
    assert A.COSTS == (1.0, 3.0, 5.0, 10.0, 20.0)
    assert A.PORTFOLIO == {"rule": "topk_dropout", "quantiles": 5, "drop_fraction": 0.10}
    assert A.DEFINITION["model"]["hyperparameter_search"] == "none"
    assert A.DEFINITION["interpretation"]["no_best_seed"] is True
    assert A.DEFINITION["holdout"]["touched"] is False


def test_real_inputs_are_the_frozen_panel_and_eight_folds():
    dry = A.dry_run(REPO)
    assert dry["dataset_id_matches"] and dry["dataset_hash_matches"] and dry["dataset_rows_match"]
    assert dry["features"] == 26 and dry["folds"] == 8
    assert dry["last_validation_date"] == "2025-05-09" and dry["holdout_start"] == "2025-08-26"
    assert dry["real_training_executed"] is False


def test_run_calls_gate_before_loading_data(tmp_path, monkeypatch):
    touched = []
    monkeypatch.setattr(exp009b, "load_frame", lambda *a, **k: touched.append(1))
    monkeypatch.setattr(A, "prereg_gate", lambda *a, **k: (_ for _ in ()).throw(prereg.PreregistrationError("missing")))
    with pytest.raises(prereg.PreregistrationError):
        A.run_study(tmp_path)
    assert touched == []


def test_synthetic_seed_path_is_deterministic_and_reports_economics():
    frame, dates = synthetic_world(n_symbols=100, n_dates=120)
    plan = synthetic_plan(dates)
    result_one = A._run_seed(frame, plan, 3, params={"n_estimators": 5, "learning_rate": 0.03, "max_depth": 2, "subsample": 0.7, "min_samples_leaf": 10})
    result_two = A._run_seed(frame, plan, 3, params={"n_estimators": 5, "learning_rate": 0.03, "max_depth": 2, "subsample": 0.7, "min_samples_leaf": 10})
    assert len(result_one.folds) == len(plan.folds) and not result_one.errors
    np.testing.assert_array_equal(result_one.predictions["prediction"], result_two.predictions["prediction"])
    panel = frame[["date", "symbol", "dollar_volume", "fwd_ret_5", "fwd_ret_21", "in_universe"]]
    report, folds = A._seed_report(3, result_one.predictions, panel, result_one.predictions)
    assert len(folds) == len(plan.folds) and report["positive_fold_count"] <= len(plan.folds)
    assert set(report["costs"]) == {"1bp", "3bp", "5bp", "10bp", "20bp"}


def test_distribution_has_registered_statistics():
    result = A._distribution(range(10))
    assert set(result) == {"mean", "sample_std", "median", "min", "max", "p05", "p95", "p95_minus_p05"}
    assert result["p95_minus_p05"] == pytest.approx(8.1)


def test_checkpoint_prediction_hash_is_order_invariant():
    frame = pd.DataFrame({"date": [date(2024, 1, 2), date(2024, 1, 2)], "symbol": ["A", "B"],
                          "fold": [0, 0], A.LABEL: [0.1, 0.2], "prediction": [0.3, 0.4]})
    assert A._prediction_hash(frame) == A._prediction_hash(frame.iloc[::-1])
