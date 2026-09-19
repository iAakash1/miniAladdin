"""
Boosted trees with a swappable objective: point regression, LambdaMART, pairwise.

## Why this is written here instead of imported

The repository's dependency policy (`requirements-quant.txt`) declines a third
boosting library, and LightGBM cannot even be imported on the reference machine
without a system OpenMP runtime. More importantly, the question EXP-009B asks —
*does a ranking loss order a cross-section better than a point-regression loss?* —
is only answered cleanly if **nothing else differs**. Comparing sklearn's exact-split
`GradientBoostingRegressor` with LightGBM's histogram `lambdarank` confounds the
loss with the tree learner, the binning, the regularisation and the bagging.

So the boosting loop is one piece of code and the objective is the only argument:

    "l2"          squared error on the continuous rank label   (the control)
    "lambdamart"  pairwise logistic loss weighted by |delta NDCG|   (Burges 2010)
    "pairwise"    the same pairwise loss with uniform pair weights  (RankNet-style)

All three use the same trees (`DecisionTreeRegressor`, friedman_mse, the same
depth / leaf size / subsample / learning rate / number of rounds as the repository's
`GradientBoostedTrees`), the same Newton leaf update and the same random stream.
With `subsample=1.0` the `l2` objective reproduces sklearn's
`GradientBoostingRegressor` to floating-point precision (asserted in the tests),
which is what licenses calling it a control.

## The queries

A *query* is a prediction date; its *items* are the stocks eligible on that date.
Pairs are formed only inside a query — a stock on 2019-03-01 is never compared with
one on 2021-06-04 — because the model is used to order names on one date. That is
why the loop needs `groups` (the date of every training row) and why the walk-forward
driver passes them only to models that declare `requires_groups`.

## Relevance labels

Ranking objectives need graded relevance, not a continuous return. The label
`fwd_rank_21` is already a within-date rank in [-1, 1]; it is cut into five equal-width
bins — the within-date quintile of the 21-session forward return — the same
five buckets the portfolio holds the extremes of:

    relevance = clip(floor((rank + 1) / 2 * 5), 0, 4)

Fixed before any result was seen, it depends on nothing but the label's own scale.
It discards ordering *within* a quintile, deliberately: the book does not use it.

## The two ranking objectives, and why they are top-weighted differently

`lambdamart` weights every pair by the change in NDCG that swapping the two would
cause (linear gains, log2 position discounts, whole list, no truncation), so it
concentrates learning where the ranking is read most — the top. `pairwise` weights
all pairs equally, so the bottom of the list matters as much as the top, which is what
a dollar-neutral book needs. Neither is normalised per query and neither has a
hyper-parameter search.

## What the gradients are

For a pair (i preferred to j), with `rho = 1 / (1 + exp(sigma (s_i - s_j)))`, the
pseudo-residual (negative gradient of the weighted pairwise logistic loss) is
`+sigma * w_ij * rho` for i and `-sigma * w_ij * rho` for j; the Hessian diagonal is
`sigma^2 * w_ij * rho * (1 - rho)` for both. Leaves take the Newton step
`sum(residual) / (sum(hessian) + reg)`.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from src.quant.models.base import Explanation, Model

try:  # pragma: no cover
    from sklearn.tree import DecisionTreeRegressor as _Tree

    SKLEARN_AVAILABLE = True
except ImportError:  # pragma: no cover
    SKLEARN_AVAILABLE = False

OBJECTIVES = ("l2", "lambdamart", "pairwise")

#: Ordinal relevance levels the rank label is cut into (the portfolio's quintiles).
RELEVANCE_LEVELS = 5

#: Logistic slope of the pairwise loss. 1.0 is the conventional value.
SIGMA = 1.0

#: Guards the exponent; a score gap this large already saturates the sigmoid.
_CLIP = 50.0


def relevance_from_rank(rank_label: np.ndarray, levels: int = RELEVANCE_LEVELS) -> np.ndarray:
    """Cut a within-date rank in [-1, 1] into `levels` ordinal relevance bins."""
    scaled = np.floor((np.asarray(rank_label, dtype=float) + 1.0) / 2.0 * levels)
    return np.clip(scaled, 0, levels - 1).astype(np.int64)


def _max_dcg_inverse(gains: np.ndarray) -> float:
    ideal = np.sort(gains)[::-1]
    dcg = float((ideal / np.log2(np.arange(len(ideal)) + 2.0)).sum())
    return 1.0 / dcg if dcg > 0 else 0.0


def query_gradients(
    scores: np.ndarray,
    relevance: np.ndarray,
    *,
    mode: str,
    sigma: float = SIGMA,
    truncation: Optional[int] = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Pseudo-residuals and Hessian diagonal for ONE query. Pure function of its arguments.

    Only pairs with `relevance_i > relevance_j` contribute. `mode` is
    "lambdamart" (pairs weighted by |delta NDCG|) or "pairwise" (uniform).
    `truncation`, if set, keeps only pairs with at least one item in the current
    top `truncation` positions; the preregistered value is None (whole list).
    """
    m = len(scores)
    residual = np.zeros(m)
    hessian = np.zeros(m)
    preferred = relevance[:, None] > relevance[None, :]
    if m < 2 or not preferred.any():
        return residual, hessian

    gap = np.clip(sigma * (scores[:, None] - scores[None, :]), -_CLIP, _CLIP)
    rho = 1.0 / (1.0 + np.exp(gap))

    if mode == "lambdamart":
        order = np.argsort(-scores, kind="stable")
        position = np.empty(m, dtype=np.int64)
        position[order] = np.arange(m)
        discount = 1.0 / np.log2(position + 2.0)
        gains = relevance.astype(float)                     # linear gains
        weight = np.abs(
            (gains[:, None] - gains[None, :]) * (discount[:, None] - discount[None, :])
        ) * _max_dcg_inverse(gains)
        if truncation is not None:
            weight = weight * (np.minimum(position[:, None], position[None, :]) < truncation)
    elif mode == "pairwise":
        weight = 1.0
    else:
        raise ValueError(f"unknown pair-weighting mode {mode!r}")

    pair = np.where(preferred, weight, 0.0)
    lam = sigma * rho * pair
    residual = lam.sum(axis=1) - lam.sum(axis=0)
    curvature = (sigma**2) * rho * (1.0 - rho) * pair
    hessian = curvature.sum(axis=1) + curvature.sum(axis=0)
    return residual, hessian


class BoostedTrees(Model):
    """Gradient-boosted regression trees, objective chosen by `objective`."""

    model_id = "boosted_trees"
    task = "regression"
    requires_scaling = False
    requires_groups = True

    def __init__(
        self,
        *,
        objective: str = "l2",
        n_estimators: int = 200,
        learning_rate: float = 0.03,
        max_depth: int = 3,
        subsample: float = 0.7,
        min_samples_leaf: int = 50,
        relevance_levels: int = RELEVANCE_LEVELS,
        sigma: float = SIGMA,
        truncation: Optional[int] = None,
        seed: int = 0,
        **params: Any,
    ) -> None:
        if objective not in OBJECTIVES:
            raise ValueError(f"objective must be one of {OBJECTIVES}, got {objective!r}")
        super().__init__(
            seed=seed, objective=objective, n_estimators=n_estimators,
            learning_rate=learning_rate, max_depth=max_depth, subsample=subsample,
            min_samples_leaf=min_samples_leaf, relevance_levels=relevance_levels,
            sigma=sigma, truncation=truncation, **params,
        )
        self.objective = objective
        #: Ranker scores have no scale; only scale-free metrics are meaningful.
        self.scale_free = objective != "l2"
        self._trees: list[Any] = []
        self._leaf_values: list[np.ndarray] = []
        self._init = 0.0
        self._groups: Optional[np.ndarray] = None

    # ── fitting ──────────────────────────────────────────────────────────

    def _query_slices(self, groups: np.ndarray) -> list[np.ndarray]:
        order = np.argsort(groups, kind="stable")
        sorted_groups = groups[order]
        boundaries = np.flatnonzero(sorted_groups[1:] != sorted_groups[:-1]) + 1
        return np.split(order, boundaries)

    def _gradients(self, y: np.ndarray, relevance: Optional[np.ndarray], scores: np.ndarray,
                   slices: Optional[list[np.ndarray]]) -> tuple[np.ndarray, np.ndarray]:
        if self.objective == "l2":
            return y - scores, np.ones_like(scores)
        residual = np.zeros_like(scores)
        hessian = np.zeros_like(scores)
        for index in slices:
            r, h = query_gradients(
                scores[index], relevance[index], mode=self.objective,
                sigma=self.params["sigma"], truncation=self.params["truncation"],
            )
            residual[index] = r
            hessian[index] = h
        return residual, hessian

    def _fit(self, X: np.ndarray, y: np.ndarray) -> None:
        if not SKLEARN_AVAILABLE:  # pragma: no cover
            raise RuntimeError("boosted trees need scikit-learn")
        n = len(X)
        slices = relevance = None
        if self.objective != "l2":
            if self._groups is None:
                raise ValueError(f"{self.objective} needs `groups` (the date of each row)")
            slices = self._query_slices(self._groups)
            relevance = relevance_from_rank(y, self.params["relevance_levels"])

        p = self.params
        random_state = np.random.RandomState(self.seed)
        self._init = float(np.mean(y)) if self.objective == "l2" else 0.0
        scores = np.full(n, self._init)
        in_bag = max(int(p["subsample"] * n), 1)
        self._trees, self._leaf_values = [], []

        for _ in range(p["n_estimators"]):
            residual, hessian = self._gradients(y, relevance, scores, slices)
            if p["subsample"] < 1.0:
                bag = np.zeros(n, dtype=bool)
                bag[np.argsort(random_state.uniform(size=n))[:in_bag]] = True
            else:
                bag = np.ones(n, dtype=bool)

            tree = _Tree(
                criterion="friedman_mse", splitter="best", max_depth=p["max_depth"],
                min_samples_leaf=p["min_samples_leaf"], random_state=random_state,
            )
            tree.fit(X[bag], residual[bag])

            # Newton leaf values on the in-bag rows. For `l2` (hessian 1, no
            # regularisation) this is exactly the tree's own leaf mean.
            leaves = tree.apply(X)
            values = np.zeros(tree.tree_.node_count)
            if self.objective == "l2":
                values[:] = tree.tree_.value[:, 0, 0]
            else:
                reg = float(hessian[bag].mean()) if bag.any() else 1.0
                num = np.bincount(leaves[bag], weights=residual[bag], minlength=len(values))
                den = np.bincount(leaves[bag], weights=hessian[bag], minlength=len(values))
                values = num / (den + reg + 1e-12)
            scores = scores + p["learning_rate"] * values[leaves]
            self._trees.append(tree)
            self._leaf_values.append(values)

    def _predict(self, X: np.ndarray) -> np.ndarray:
        out = np.full(len(X), self._init)
        rate = self.params["learning_rate"]
        for tree, values in zip(self._trees, self._leaf_values):
            out += rate * values[tree.apply(X)]
        return out

    def explain(self) -> Explanation:
        if not self._trees:
            return super().explain()
        total = np.zeros(len(self.feature_names))
        for tree in self._trees:
            total += tree.feature_importances_
        total = total / max(total.sum(), 1e-12)
        return Explanation(
            kind="split_gain_importance",
            values={name: float(v) for name, v in zip(self.feature_names, total)},
            description=(
                f"Mean impurity reduction per feature across the {self.objective} ensemble."
            ),
            caveat=(
                "Split-gain importance is magnitude without direction, biased toward "
                "continuous features, and divides credit between correlated features "
                "arbitrarily. Not a causal ranking."
            ),
        )


class BoostedL2(BoostedTrees):
    model_id = "boosted_l2"

    def __init__(self, **params: Any) -> None:
        super().__init__(objective="l2", **params)


class BoostedLambdaMART(BoostedTrees):
    model_id = "boosted_lambdamart"

    def __init__(self, **params: Any) -> None:
        super().__init__(objective="lambdamart", **params)


class BoostedPairwise(BoostedTrees):
    model_id = "boosted_pairwise"

    def __init__(self, **params: Any) -> None:
        super().__init__(objective="pairwise", **params)
