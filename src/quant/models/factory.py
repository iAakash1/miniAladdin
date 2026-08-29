"""
Model construction from a picklable spec.

## Why a spec instead of a lambda

The study runs one walk-forward per model, and those runs are independent — the
obvious way to use a 12-core machine. But a process pool has to pickle what it
sends to a worker, and a `lambda: RidgeRegression(alpha=10.0, seed=0)` is not
picklable.

The alternative most codebases reach for is `n_jobs=-1` inside each estimator.
That is rejected here: threaded histogram construction and parallel tree
building reorder floating-point accumulation, so two runs with the same seed
differ in the last bits and `tests/quant/test_models.py::
test_same_seed_gives_identical_predictions` fails. A prediction that cannot be
reproduced cannot anchor a research record.

So parallelism goes **across** models, each still single-threaded:

    12 models x 1 thread  ->  deterministic, ~10 cores busy
     1 model  x 12 threads ->  faster per model, not reproducible

`ModelSpec` is a frozen dataclass of primitives, which pickles cleanly and
doubles as the registry's record of what was built.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.quant.models.base import Model


@dataclass(frozen=True)
class ModelSpec:
    """A picklable description of one model configuration."""

    name: str
    kind: str
    params: tuple[tuple[str, Any], ...] = ()
    seed: int = 0

    @property
    def kwargs(self) -> dict[str, Any]:
        return dict(self.params)

    def build(self) -> Model:
        """Construct the model. Imports live here so workers stay light."""
        from src.quant.models.baselines import (
            FeaturePassthroughBaseline, HistoricalMeanBaseline,
            PersistenceBaseline, ZeroBaseline,
        )
        from src.quant.models.linear import (
            ElasticNetRegression, LassoRegression, LogisticDirection,
            OrdinaryLeastSquares, RidgeRegression,
        )
        from src.quant.models.trees import (
            ExtraTrees, GradientBoostedTrees, HistGradientBoosting, RandomForest,
        )

        registry: dict[str, Any] = {
            "zero": ZeroBaseline,
            "historical_mean": HistoricalMeanBaseline,
            "passthrough": FeaturePassthroughBaseline,
            "persistence": PersistenceBaseline,
            "ols": OrdinaryLeastSquares,
            "ridge": RidgeRegression,
            "lasso": LassoRegression,
            "elastic_net": ElasticNetRegression,
            "logistic": LogisticDirection,
            "gradient_boosting": GradientBoostedTrees,
            "random_forest": RandomForest,
            "hist_gradient_boosting": HistGradientBoosting,
            "extra_trees": ExtraTrees,
        }
        if self.kind not in registry:
            raise KeyError(f"unknown model kind {self.kind!r}; known: {sorted(registry)}")
        model = registry[self.kind](seed=self.seed, **self.kwargs)
        # The spec's name is the leaderboard identity, so a second
        # configuration of the same algorithm is a distinct row rather than an
        # overwrite of the first.
        model.model_id = self.name
        return model

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "kind": self.kind,
            "params": self.kwargs, "seed": self.seed,
        }


def default_specs(seed: int = 0) -> list[ModelSpec]:
    """The model ladder, fixed before any result is seen.

    Ordered by complexity so the leaderboard can be read as a ladder: each rung
    has to earn its place over the one below it.
    """
    return [
        # Level 0-1: no features consulted.
        ModelSpec("baseline_zero", "zero", seed=seed),
        ModelSpec("baseline_historical_mean", "historical_mean", seed=seed),
        # Level 2: free factors, unfitted.
        ModelSpec("baseline_momentum", "passthrough",
                  (("feature", "mom_252_21_xs"),), seed),
        ModelSpec("baseline_reversal", "passthrough",
                  (("feature", "reversal_5_xs"),), seed),
        ModelSpec("baseline_low_volatility", "passthrough",
                  (("feature", "vol_63_xs"), ("sign", -1.0)), seed),
        ModelSpec("baseline_earnings_surprise", "passthrough",
                  (("feature", "earn_surprise_pct_xs"),), seed),
        ModelSpec("baseline_iv_premium", "passthrough",
                  (("feature", "opt_iv_minus_hv_xs"),), seed),
        # Level 3: linear.
        ModelSpec("ols", "ols", seed=seed),
        ModelSpec("ridge", "ridge", (("alpha", 10.0),), seed),
        ModelSpec("ridge_strong", "ridge", (("alpha", 200.0),), seed),
        ModelSpec("lasso", "lasso", (("alpha", 0.0005),), seed),
        ModelSpec("elastic_net", "elastic_net",
                  (("alpha", 0.0005), ("l1_ratio", 0.5)), seed),
        # Level 4: trees.
        ModelSpec("gradient_boosting", "gradient_boosting", seed=seed),
        ModelSpec("random_forest", "random_forest", seed=seed),
        ModelSpec("hist_gradient_boosting", "hist_gradient_boosting", seed=seed),
        ModelSpec("extra_trees", "extra_trees", seed=seed),
        # The overfitting control on the tree side, mirroring OLS on the linear
        # side. Expected to show a large train-versus-validation gap; that gap
        # is the demonstration that the diagnostic works on a model built to
        # trigger it, which is what makes it trustworthy on the others.
        #
        # 150 trees, not 500. Measured: at 500 trees, depth 8 and no subsampling
        # this single configuration took longer than the other sixteen combined
        # — sklearn's exact-split boosting is O(trees x features x rows x log
        # rows) and single-threaded by our determinism rule. Depth 8 with
        # `min_samples_leaf=5` and no subsampling already overfits decisively;
        # the extra 350 trees bought runtime, not a clearer demonstration.
        ModelSpec("gradient_boosting_deep", "gradient_boosting",
                  (("max_depth", 8), ("n_estimators", 150), ("learning_rate", 0.1),
                   ("subsample", 1.0), ("min_samples_leaf", 5)), seed),
    ]
