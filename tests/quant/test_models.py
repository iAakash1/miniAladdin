"""Model contract: determinism, refusals, and explanations that are never invented."""

from __future__ import annotations

import numpy as np
import pytest

from src.quant.models.base import FoldImputer, Model, ModelNotFitted
from src.quant.models.baselines import (
    FeaturePassthroughBaseline, HistoricalMeanBaseline, PersistenceBaseline,
    ZeroBaseline, momentum_baseline, regression_baselines,
)
from src.quant.models.linear import (
    SKLEARN_AVAILABLE, ElasticNetRegression, LassoRegression, LogisticDirection,
    OrdinaryLeastSquares, RidgeRegression,
)
from src.quant.models.registry import (
    ModelEntry, ModelRegistry, PromotionRefused, dependency_versions,
)
from src.quant.models.trees import GradientBoostedTrees, HistGradientBoosting, RandomForest

requires_sklearn = pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn absent")


@pytest.fixture
def data():
    rng = np.random.default_rng(4)
    X = rng.normal(size=(600, 6))
    y = X[:, 0] * 0.02 + X[:, 1] * X[:, 2] * 0.01 + rng.normal(scale=0.04, size=600)
    names = ["mom_252_21_xs", "reversal_5_xs", "vol_63_xs", "vol_21", "f4", "f5"]
    return X, y, names


ALL_MODELS = [ZeroBaseline, HistoricalMeanBaseline]
if SKLEARN_AVAILABLE:
    ALL_MODELS += [
        OrdinaryLeastSquares, RidgeRegression, LassoRegression, ElasticNetRegression,
        GradientBoostedTrees, RandomForest, HistGradientBoosting,
    ]


@pytest.mark.parametrize("factory", ALL_MODELS)
def test_same_seed_gives_identical_predictions(factory, data):
    """A prediction that cannot be reproduced cannot anchor a research record."""
    X, y, names = data
    first = factory(seed=0).fit(X, y, feature_names=names).predict(X)
    second = factory(seed=0).fit(X, y, feature_names=names).predict(X)
    np.testing.assert_array_equal(first, second)


@pytest.mark.parametrize("factory", ALL_MODELS)
def test_fingerprint_is_stable_and_seed_sensitive(factory, data):
    assert factory(seed=0).fingerprint() == factory(seed=0).fingerprint()
    assert factory(seed=0).fingerprint() != factory(seed=7).fingerprint()


@pytest.mark.parametrize("factory", ALL_MODELS)
def test_predicting_before_fitting_raises(factory, data):
    X, _, _ = data
    with pytest.raises(ModelNotFitted):
        factory().predict(X)


def test_non_finite_input_is_refused_rather_than_imputed_inside_the_model(data):
    """Imputation is the pipeline's job — hiding it in the model hides which fold's
    statistics were used, which is a leak that leaves no trace."""
    X, y, names = data
    dirty = X.copy()
    dirty[0, 0] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        ZeroBaseline().fit(dirty, y, feature_names=names)


def test_feature_count_mismatch_is_refused(data):
    X, y, names = data
    model = ZeroBaseline().fit(X, y, feature_names=names)
    with pytest.raises(ValueError, match="features"):
        model.predict(X[:, :3])


def test_baseline_without_attribution_returns_an_empty_explanation():
    """A model with no attribution must say so, not fabricate importances."""
    explanation = ZeroBaseline().explain()
    assert explanation.kind == "constant"
    assert explanation.values == {}


def test_hist_gradient_boosting_declines_to_invent_importances(data):
    if not SKLEARN_AVAILABLE:
        pytest.skip("scikit-learn absent")
    X, y, names = data
    model = HistGradientBoosting(seed=0).fit(X, y, feature_names=names)
    explanation = model.explain()
    assert explanation.kind == "none"
    assert explanation.values == {}


def test_passthrough_baseline_needs_its_feature_present(data):
    X, y, _ = data
    with pytest.raises(ValueError, match="mom_252_21_xs"):
        momentum_baseline().fit(X, y, feature_names=[f"other{i}" for i in range(6)])


def test_passthrough_baseline_is_marked_scale_free(data):
    """Its output is a factor value, not a return — RMSE against a return is meaningless."""
    X, y, names = data
    model = momentum_baseline().fit(X, y, feature_names=names)
    assert getattr(model, "scale_free", False) is True
    np.testing.assert_allclose(model.predict(X), X[:, 0])


def test_low_volatility_baseline_negates_its_feature(data):
    X, y, names = data
    from src.quant.models.baselines import low_volatility_baseline

    model = low_volatility_baseline().fit(X, y, feature_names=names)
    np.testing.assert_allclose(model.predict(X), -X[:, 2])


def test_historical_mean_predicts_the_training_mean_not_the_full_sample(data):
    X, y, names = data
    model = HistoricalMeanBaseline().fit(X[:100], y[:100], feature_names=names)
    assert model.predict(X[100:])[0] == pytest.approx(float(np.mean(y[:100])))


@requires_sklearn
def test_ridge_shrinks_more_than_ols(data):
    X, y, names = data
    imputer = FoldImputer(standardise=True)
    Xs = imputer.fit_transform(X, feature_names=names)
    ols = OrdinaryLeastSquares().fit(Xs, y, feature_names=names)
    ridge = RidgeRegression(alpha=500.0).fit(Xs, y, feature_names=names)
    ols_norm = sum(abs(v) for v in ols.explain().values.values())
    ridge_norm = sum(abs(v) for v in ridge.explain().values.values())
    assert ridge_norm < ols_norm


@requires_sklearn
def test_lasso_drives_coefficients_to_exactly_zero(data):
    X, y, names = data
    Xs = FoldImputer(standardise=True).fit_transform(X, feature_names=names)
    model = LassoRegression(alpha=0.05).fit(Xs, y, feature_names=names)
    assert any(abs(v) < 1e-12 for v in model.explain().values.values())


@requires_sklearn
def test_logistic_refuses_a_single_class_fold(data):
    """A classifier fitted on one class predicts a constant whose accuracy is the
    base rate — which would be reported as skill."""
    X, _, names = data
    Xs = FoldImputer(standardise=True).fit_transform(X, feature_names=names)
    with pytest.raises(ValueError, match="only class"):
        LogisticDirection().fit(Xs, np.ones(len(Xs)), feature_names=names)


@requires_sklearn
def test_logistic_returns_probabilities_not_hard_labels(data):
    X, y, names = data
    Xs = FoldImputer(standardise=True).fit_transform(X, feature_names=names)
    proba = LogisticDirection().fit(Xs, (y > 0).astype(float), feature_names=names).predict(Xs)
    assert ((proba >= 0) & (proba <= 1)).all()
    assert len(np.unique(proba)) > 2


# ── imputer ─────────────────────────────────────────────────────────────────


def test_imputer_handles_an_all_nan_column_without_producing_nan():
    X = np.array([[1.0, np.nan], [2.0, np.nan], [3.0, np.nan]])
    out = FoldImputer().fit_transform(X, feature_names=["a", "b"])
    assert np.isfinite(out).all()


def test_imputer_does_not_divide_by_a_zero_scale():
    X = np.array([[1.0, 5.0], [2.0, 5.0], [3.0, 5.0]])
    out = FoldImputer(standardise=True).fit_transform(X, feature_names=["a", "b"])
    assert np.isfinite(out).all()


def test_imputer_reports_coverage():
    X = np.array([[1.0, np.nan], [2.0, 4.0]])
    imputer = FoldImputer().fit(X, feature_names=["a", "b"])
    assert imputer.coverage(X) == {"a": 1.0, "b": 0.5}


# ── registry ────────────────────────────────────────────────────────────────


def _entry(**overrides) -> ModelEntry:
    base = dict(model_id="ridge", version="1.0", task="regression", label="fwd_ret_21")
    base.update(overrides)
    return ModelEntry(**base)


def test_promotion_is_refused_without_evidence(tmp_path):
    registry = ModelRegistry(tmp_path)
    entry = registry.register(_entry())
    with pytest.raises(PromotionRefused, match="walk-forward"):
        registry.promote(entry.key, "validated")


def _passing_candidate(**overrides) -> ModelEntry:
    """An entry whose validation numbers clear every candidate threshold."""
    base = dict(
        walk_forward={"mean_ic": 0.02, "ic_t_stat": 2.6},
        validation_methodology="8-fold expanding",
        baseline_comparison={"beat_best_baseline": True},
        backtest={"net_sharpe": 0.9, "gross_sharpe": 1.1},
        factor_attribution={"alpha_t_stat": 2.4},
    )
    base.update(overrides)
    return _entry(**base)


def test_production_needs_holdout_and_regime_evidence(tmp_path):
    registry = ModelRegistry(tmp_path)
    entry = registry.register(_passing_candidate())
    registry.promote(entry.key, "production_candidate")
    with pytest.raises(PromotionRefused, match="holdout"):
        registry.promote(entry.key, "production")


def test_candidacy_is_refused_when_the_model_loses_money(tmp_path):
    """The EXP-004 case: a full evidence bundle that says the model is bad.

    Every `PROMOTION_GATES` requirement is satisfied — the walk-forward, the
    methodology, the baseline comparison, the backtest and the attribution all
    exist. Only the numbers are damning. Before `CANDIDATE_THRESHOLDS` this
    reached `production_candidate`.
    """
    registry = ModelRegistry(tmp_path)
    entry = registry.register(
        _passing_candidate(
            walk_forward={"mean_ic": 0.0238, "ic_t_stat": 1.91},
            backtest={"net_sharpe": -0.598, "gross_sharpe": -0.276},
        )
    )
    with pytest.raises(PromotionRefused, match="candidate thresholds"):
        registry.promote(entry.key, "production_candidate")
    assert entry.status == "experimental"

    unmet = entry.candidate_thresholds_not_met()
    assert unmet["ic_t_stat"] == pytest.approx(1.91)
    assert unmet["net_sharpe"] == pytest.approx(-0.598)
    assert unmet["gross_sharpe"] == pytest.approx(-0.276)


def test_unrecorded_candidate_metric_counts_as_unmet(tmp_path):
    """Absent evidence is not passing evidence — including a nested backtest.

    The study nests its backtest metrics under a ``metrics`` key. If that block
    is stored unflattened the thresholds find nothing, and "not recorded" must
    refuse rather than wave the model through.
    """
    registry = ModelRegistry(tmp_path)
    entry = registry.register(
        _passing_candidate(backtest={"metrics": {"net_sharpe": 2.0, "gross_sharpe": 2.4}})
    )
    assert entry.candidate_thresholds_not_met()["net_sharpe"] == "not recorded"
    with pytest.raises(PromotionRefused, match="candidate thresholds"):
        registry.promote(entry.key, "production_candidate")


def test_eligible_for_never_lists_a_status_promotion_would_refuse(tmp_path):
    registry = ModelRegistry(tmp_path)
    entry = registry.register(
        _passing_candidate(backtest={"net_sharpe": -0.6, "gross_sharpe": -0.3})
    )
    eligible = entry.as_dict()["eligible_for"]
    assert "production_candidate" not in eligible
    assert "production" not in eligible
    assert "validated" in eligible
    for status in eligible:
        registry.promote(entry.key, status, reason="asserting eligibility is honest")


def test_retirement_never_requires_evidence(tmp_path):
    registry = ModelRegistry(tmp_path)
    entry = registry.register(_entry())
    registry.promote(entry.key, "retired", reason="superseded")
    assert entry.status == "retired"
    assert entry.status_history[-1]["reason"] == "superseded"


def test_registry_round_trips(tmp_path):
    registry = ModelRegistry(tmp_path)
    registry.register(_entry(walk_forward={"mean_ic": 0.031}, experiments_run=12))
    registry.save()

    reloaded = ModelRegistry(tmp_path)
    entry = reloaded.get("ridge@1.0:fwd_ret_21")
    assert entry.walk_forward["mean_ic"] == pytest.approx(0.031)
    assert entry.experiments_run == 12


def test_leaderboard_carries_the_experiment_count(tmp_path):
    """The best of N is optimistically biased — N must survive into the table."""
    registry = ModelRegistry(tmp_path)
    registry.register(_entry(walk_forward={"mean_ic": 0.05}, experiments_run=40))
    assert registry.leaderboard()[0]["experiments_run"] == 40


def test_dependency_versions_records_what_can_change_a_prediction():
    versions = dependency_versions()
    assert "numpy" in versions and "pandas" in versions and "python" in versions
