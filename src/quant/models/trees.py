"""
Tree ensembles — gradient boosting and random forests.

## Where these are expected to help, and where they are not

Trees capture interactions and non-monotone effects a linear model cannot: "low
volatility *and* high momentum" is a different regime from either alone, and a
linear model can only add the two. That is a real hypothesis about markets and
it is worth testing.

The counter-pressure is equally real. Forward returns have a very low
signal-to-noise ratio, and a model flexible enough to find a genuine
interaction is flexible enough to memorise noise. So the defaults here are
deliberately conservative — shallow trees, heavy subsampling, high
`min_samples_leaf` — and `docs/modeling-methodology.md` records that these were
set *before* seeing validation results rather than tuned until they looked
good. Tuning depth against the validation fold and then reporting that fold is
the single most common way a backtest becomes fiction.

## `n_jobs=1`, deliberately

Determinism outranks speed here. Threaded histogram construction can reorder
floating-point accumulation, which makes two runs with the same seed differ in
the last bits — enough to break the reproducibility test in
`tests/quant/test_models.py`. A model whose predictions cannot be reproduced
cannot anchor a research record, and these datasets are small enough that the
single-threaded cost is seconds.

## Importances are split gains, and that is a narrower claim than it looks

`feature_importances_` measures how much each feature reduced impurity across
the ensemble. It is biased toward high-cardinality continuous features, it
splits credit arbitrarily between correlated features, and it says nothing
about direction. The `Explanation.caveat` says so, and the UI renders it —
because an importance bar chart presented without that is read as a causal
ranking, which it is not.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from src.quant.models.base import Explanation, Model

try:  # pragma: no cover
    from sklearn.ensemble import (
        ExtraTreesRegressor as _ETR,
        GradientBoostingRegressor as _GBR,
        HistGradientBoostingRegressor as _HGBR,
        RandomForestRegressor as _RFR,
    )

    SKLEARN_AVAILABLE = True
    SKLEARN_IMPORT_ERROR = None
except ImportError as error:  # pragma: no cover
    SKLEARN_AVAILABLE = False
    SKLEARN_IMPORT_ERROR = str(error)


def _require_sklearn(model_id: str) -> None:
    if not SKLEARN_AVAILABLE:
        raise RuntimeError(
            f"{model_id} needs scikit-learn ({SKLEARN_IMPORT_ERROR}). "
            "Install requirements-quant.txt. The capability reports unavailable "
            "rather than falling back to a different model."
        )


class _SklearnTree(Model):
    """Shared plumbing for tree ensembles."""

    #: Trees are scale-invariant — a split on a raw value and on a standardised
    #: one partition identically — so standardisation is skipped rather than
    #: applied for symmetry. Imputation still happens; trees need finite input.
    requires_scaling = False

    def __init__(self, *, seed: int = 0, **params: Any) -> None:
        super().__init__(seed=seed, **params)
        self._estimator = None

    def _build(self):  # pragma: no cover
        raise NotImplementedError

    def _fit(self, X: np.ndarray, y: np.ndarray) -> None:
        _require_sklearn(self.model_id)
        self._estimator = self._build()
        self._estimator.fit(X, y)

    def _predict(self, X: np.ndarray) -> np.ndarray:
        return self._estimator.predict(X)

    def explain(self) -> Explanation:
        if self._estimator is None:
            return super().explain()
        importances = getattr(self._estimator, "feature_importances_", None)
        if importances is None:
            return Explanation(
                kind="none",
                values={},
                description=f"{self.model_id} exposes no importances in this configuration.",
                caveat="No attribution is available; none is shown.",
            )
        return Explanation(
            kind="split_gain_importance",
            values={
                name: float(value) for name, value in zip(self.feature_names, importances)
            },
            description="Mean impurity reduction attributable to each feature across the ensemble.",
            caveat=(
                "Split-gain importance is magnitude without direction: it says a "
                "feature was used, not which way. It is biased toward continuous "
                "high-cardinality features, and correlated features divide credit "
                "arbitrarily between them. Not a causal ranking."
            ),
        )


class GradientBoostedTrees(_SklearnTree):
    """Shallow, heavily-subsampled gradient boosting.

    Depth 3 and `subsample=0.7` are not tuned values. They are the standard
    conservative starting point for a low signal-to-noise target, fixed in
    advance so the validation fold is not consumed by a search.
    """

    model_id = "gradient_boosting"
    task = "regression"

    def __init__(
        self,
        *,
        n_estimators: int = 200,
        learning_rate: float = 0.03,
        max_depth: int = 3,
        subsample: float = 0.7,
        min_samples_leaf: int = 50,
        seed: int = 0,
        **params: Any,
    ) -> None:
        super().__init__(
            seed=seed,
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            max_depth=max_depth,
            subsample=subsample,
            min_samples_leaf=min_samples_leaf,
            **params,
        )

    def _build(self):
        return _GBR(
            n_estimators=self.params["n_estimators"],
            learning_rate=self.params["learning_rate"],
            max_depth=self.params["max_depth"],
            subsample=self.params["subsample"],
            min_samples_leaf=self.params["min_samples_leaf"],
            random_state=self.seed,
        )


class HistGradientBoosting(_SklearnTree):
    """Histogram-based boosting — the fast path for larger matrices.

    Native NaN handling is *not* relied on: the pipeline imputes before the
    model sees the data, so every model in the comparison receives an identical
    matrix. Letting one model handle missingness its own way would confound
    "better model" with "better missing-data policy".
    """

    model_id = "hist_gradient_boosting"
    task = "regression"

    def __init__(
        self,
        *,
        max_iter: int = 300,
        learning_rate: float = 0.03,
        max_depth: int = 4,
        min_samples_leaf: int = 50,
        l2_regularization: float = 1.0,
        seed: int = 0,
        **params: Any,
    ) -> None:
        super().__init__(
            seed=seed,
            max_iter=max_iter,
            learning_rate=learning_rate,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            l2_regularization=l2_regularization,
            **params,
        )

    def _build(self):
        return _HGBR(
            max_iter=self.params["max_iter"],
            learning_rate=self.params["learning_rate"],
            max_depth=self.params["max_depth"],
            min_samples_leaf=self.params["min_samples_leaf"],
            l2_regularization=self.params["l2_regularization"],
            random_state=self.seed,
            early_stopping=False,
        )

    def explain(self) -> Explanation:
        # HistGradientBoosting deliberately exposes no `feature_importances_`.
        # Reporting nothing is correct; synthesising a proxy and labelling it
        # "importance" would be a fabricated explanation.
        return Explanation(
            kind="none",
            values={},
            description=(
                "HistGradientBoosting exposes no split-gain importances. Permutation "
                "importance would be available but is not computed inline, because it "
                "must be evaluated out-of-sample to mean anything."
            ),
            caveat="No attribution is available for this model; none is shown.",
        )


class RandomForest(_SklearnTree):
    """Bagged deep trees. The variance-reduction counterpoint to boosting.

    Boosting reduces bias and can chase noise; bagging reduces variance and
    tends to underfit. Running both says something about which failure mode the
    data actually punishes, which one model alone cannot.
    """

    model_id = "random_forest"
    task = "regression"

    def __init__(
        self,
        *,
        n_estimators: int = 300,
        max_depth: int = 8,
        min_samples_leaf: int = 50,
        max_features: float = 0.5,
        seed: int = 0,
        **params: Any,
    ) -> None:
        super().__init__(
            seed=seed,
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            max_features=max_features,
            **params,
        )

    def _build(self):
        return _RFR(
            n_estimators=self.params["n_estimators"],
            max_depth=self.params["max_depth"],
            min_samples_leaf=self.params["min_samples_leaf"],
            max_features=self.params["max_features"],
            random_state=self.seed,
            # Determinism over speed — see the module docstring.
            n_jobs=1,
        )


class ExtraTrees(_SklearnTree):
    """Extremely randomised trees — the maximum-variance-reduction end of bagging.

    Split thresholds are drawn at random rather than optimised, which reduces
    variance further than a random forest at the cost of bias. On a target with
    this little signal that trade is worth testing rather than assuming: if the
    optimised splits in a random forest are mostly fitting noise, randomising
    them should *help*, and the comparison says which.
    """

    model_id = "extra_trees"
    task = "regression"

    def __init__(
        self,
        *,
        n_estimators: int = 300,
        max_depth: int = 10,
        min_samples_leaf: int = 50,
        max_features: float = 0.5,
        seed: int = 0,
        **params: Any,
    ) -> None:
        super().__init__(
            seed=seed, n_estimators=n_estimators, max_depth=max_depth,
            min_samples_leaf=min_samples_leaf, max_features=max_features, **params,
        )

    def _build(self):
        return _ETR(
            n_estimators=self.params["n_estimators"],
            max_depth=self.params["max_depth"],
            min_samples_leaf=self.params["min_samples_leaf"],
            max_features=self.params["max_features"],
            random_state=self.seed,
            n_jobs=1,
        )


def tree_models(seed: int = 0) -> list[Model]:
    if not SKLEARN_AVAILABLE:
        return []
    return [
        GradientBoostedTrees(seed=seed),
        RandomForest(seed=seed),
        HistGradientBoosting(seed=seed),
        ExtraTrees(seed=seed),
    ]
