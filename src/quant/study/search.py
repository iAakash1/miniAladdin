"""
Hyperparameter search spaces and the declared budget.

## The budget is part of the pre-registration, not an implementation detail

Every configuration evaluated is a trial, and every trial inflates the
multiple-testing correction that this project applies against a **cumulative**
count across all studies. A search that quietly grows is a study that quietly
becomes less significant, so the budget is declared here, hashed into the
experiment fingerprint, and reported in the artifact.

That is also why the search is **randomized with a fixed seed** rather than a
grid. A grid's size is a property of the axes and grows multiplicatively the
moment anyone adds a value; a randomized search's size is a number someone chose
on purpose. `sample_configs` is deterministic given `(family, stage, seed, n)`,
so the same budget always produces the same configurations and a resumed run
continues the same search rather than starting a new one.

## Staged, because a flat search wastes its budget

    STAGE 1  screen     every family, few configurations   → which families compete
    STAGE 2  tune       the competitive families, deeply   → the best configuration
    STAGE 3  context    finalists across feature sets and targets
    STAGE 4  robustness neighbours and turnover variants   → is the winner fragile?

Spending the whole budget flat would give every family the same attention
regardless of whether it is competitive, and would answer the tuning question
badly for the families that matter.

## Cost estimates are measured, not guessed

`FAMILY_COST_SECONDS` comes from EXP-006's recorded per-model timings on this
exact panel (27 features, 506,374 rows, 8 folds). It is used only to *estimate*
runtime before the run; nothing scientific depends on it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional

import numpy as np

from src.quant.models.factory import ModelSpec

#: Measured seconds for one configuration across all 8 folds, from EXP-006's
#: artifact on the 27-feature panel. Used for the runtime estimate only.
FAMILY_COST_SECONDS: dict[str, float] = {
    "gradient_boosting": 292.4,
    "random_forest": 504.1,
    "extra_trees": 112.4,
    "hist_gradient_boosting": 17.8,
    "ridge": 2.2,
    "lasso": 2.6,
    "elastic_net": 2.7,
    "ols": 3.2,
}

#: A wider feature set costs roughly in proportion to its column count. EXP-006's
#: timings are for 27 features, so a 57-feature arm is scaled up.
BASELINE_FEATURE_COUNT = 27


@dataclass(frozen=True)
class Axis:
    """One hyperparameter and how to draw it.

    `draw` takes a numpy Generator so sampling is reproducible from the seed.
    """

    name: str
    draw: Callable[[np.random.Generator], Any]
    description: str


def _int_log(low: int, high: int) -> Callable[[np.random.Generator], int]:
    return lambda rng: int(round(float(np.exp(rng.uniform(np.log(low), np.log(high))))))


def _float_log(low: float, high: float) -> Callable[[np.random.Generator], float]:
    return lambda rng: float(np.exp(rng.uniform(np.log(low), np.log(high))))


def _choice(options: list[Any]) -> Callable[[np.random.Generator], Any]:
    return lambda rng: options[int(rng.integers(len(options)))]


def _uniform(low: float, high: float) -> Callable[[np.random.Generator], float]:
    return lambda rng: float(rng.uniform(low, high))


#: The search space per family.
#:
#: Ranges are chosen to bracket the scikit-learn defaults rather than to chase a
#: number — a search that only explores one side of the default is a search that
#: has already decided. Depths stay modest because the panel has 27 features and
#: ~500k rows: a depth-12 tree on that is a memorisation device, and the
#: train/validation gap diagnostic exists precisely because this project has
#: measured that.
SPACES: dict[str, list[Axis]] = {
    "gradient_boosting": [
        Axis("n_estimators", _int_log(60, 600), "boosting rounds"),
        Axis("learning_rate", _float_log(0.01, 0.30), "shrinkage per round"),
        Axis("max_depth", _choice([2, 3, 4, 5, 6]), "interaction depth"),
        Axis("subsample", _uniform(0.5, 1.0), "row subsample per round"),
        Axis("min_samples_leaf", _int_log(5, 500), "leaf size floor"),
    ],
    "hist_gradient_boosting": [
        Axis("max_iter", _int_log(60, 800), "boosting rounds"),
        Axis("learning_rate", _float_log(0.01, 0.30), "shrinkage per round"),
        Axis("max_depth", _choice([2, 3, 4, 5, 6, None]), "interaction depth"),
        Axis("min_samples_leaf", _int_log(10, 500), "leaf size floor"),
        Axis("l2_regularization", _float_log(1e-4, 10.0), "L2 penalty"),
    ],
    "random_forest": [
        Axis("n_estimators", _int_log(100, 600), "trees"),
        Axis("max_depth", _choice([4, 6, 8, 10, 12, None]), "tree depth"),
        Axis("min_samples_leaf", _int_log(5, 500), "leaf size floor"),
        Axis("max_features", _choice(["sqrt", "log2", 0.3, 0.5, 0.8]), "features per split"),
    ],
    "extra_trees": [
        Axis("n_estimators", _int_log(100, 600), "trees"),
        Axis("max_depth", _choice([4, 6, 8, 10, 12, None]), "tree depth"),
        Axis("min_samples_leaf", _int_log(5, 500), "leaf size floor"),
        Axis("max_features", _choice(["sqrt", "log2", 0.3, 0.5, 0.8]), "features per split"),
    ],
    "ridge": [
        Axis("alpha", _float_log(1e-3, 1e4), "L2 strength"),
    ],
    "lasso": [
        Axis("alpha", _float_log(1e-6, 1e-1), "L1 strength"),
    ],
    "elastic_net": [
        Axis("alpha", _float_log(1e-6, 1e-1), "penalty strength"),
        Axis("l1_ratio", _uniform(0.05, 0.95), "L1 share of the penalty"),
    ],
    "ols": [],  # nothing to tune; included as the unregularised reference
}


@dataclass(frozen=True)
class SearchBudget:
    """Configurations per family, per stage. Declared before the run."""

    name: str
    screen: dict[str, int]
    tune: dict[str, int]
    #: Families carried from screen to tune.
    tune_families: int
    #: Finalists carried into the context sweep and the robustness stage.
    finalists: int
    #: Neighbour configurations drawn around each finalist.
    neighbours_per_finalist: int
    description: str

    @property
    def screen_total(self) -> int:
        return sum(self.screen.values())

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "screen": dict(self.screen),
            "tune": dict(self.tune),
            "tune_families": self.tune_families,
            "finalists": self.finalists,
            "neighbours_per_finalist": self.neighbours_per_finalist,
            "screen_total": self.screen_total,
        }


#: Three declared scales. The user picks one; the estimate is printed before the
#: run so the choice is made against measured cost rather than a guess.
BUDGETS: dict[str, SearchBudget] = {
    "standard": SearchBudget(
        name="standard",
        screen={"gradient_boosting": 8, "hist_gradient_boosting": 12, "random_forest": 6,
                "extra_trees": 8, "ridge": 8, "lasso": 8, "elastic_net": 10, "ols": 1},
        tune={"gradient_boosting": 40, "hist_gradient_boosting": 60, "random_forest": 20,
              "extra_trees": 30, "ridge": 20, "lasso": 20, "elastic_net": 25, "ols": 1},
        tune_families=3, finalists=4, neighbours_per_finalist=6,
        description="A few hours. Enough to rank families and tune the leaders.",
    ),
    "deep": SearchBudget(
        name="deep",
        screen={"gradient_boosting": 12, "hist_gradient_boosting": 20, "random_forest": 10,
                "extra_trees": 12, "ridge": 12, "lasso": 12, "elastic_net": 16, "ols": 1},
        tune={"gradient_boosting": 90, "hist_gradient_boosting": 140, "random_forest": 45,
              "extra_trees": 70, "ridge": 40, "lasso": 40, "elastic_net": 50, "ols": 1},
        tune_families=3, finalists=5, neighbours_per_finalist=8,
        description="Most of a night. Substantially deeper tuning of the leaders.",
    ),
    "overnight": SearchBudget(
        name="overnight",
        screen={"gradient_boosting": 16, "hist_gradient_boosting": 28, "random_forest": 14,
                "extra_trees": 18, "ridge": 16, "lasso": 16, "elastic_net": 20, "ols": 1},
        tune={"gradient_boosting": 160, "hist_gradient_boosting": 260, "random_forest": 80,
              "extra_trees": 130, "ridge": 60, "lasso": 60, "elastic_net": 80, "ols": 1},
        tune_families=4, finalists=6, neighbours_per_finalist=10,
        description="A full night. The largest budget this project's trial accounting will carry.",
    ),
}

DEFAULT_BUDGET = "deep"

#: Feature arms the context stage sweeps. Not all seven: each additional arm
#: multiplies the finalist evaluations, and EXP-005 already measured that
#: options, estimates and fundamentals do not add information. These five keep
#: the comparison honest — including the two that lost — without paying for
#: every combination again.
CONTEXT_ARMS: tuple[str, ...] = (
    "A_price", "C_base", "D_base_options", "E_base_estimates", "G_all",
)

CONTEXT_TARGETS: tuple[str, ...] = ("fwd_rank_21", "fwd_ret_21")


def config_id(family: str, stage: str, index: int, params: dict[str, Any]) -> str:
    """A stable identity for one configuration.

    Includes the parameters so a checkpoint cannot be matched to a different
    configuration that happens to share an index after a budget change.
    """
    payload = f"{family}|{stage}|{index}|" + "|".join(
        f"{k}={params[k]!r}" for k in sorted(params)
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def sample_configs(
    family: str,
    count: int,
    *,
    stage: str,
    seed: int = 0,
) -> list[dict[str, Any]]:
    """Draw `count` configurations for a family, deterministically.

    Seeded from `(family, stage, seed)` so a family's draws do not shift when
    another family's budget changes — which matters for resume: a checkpoint
    written before a budget edit still matches its configuration.

    Duplicates are dropped and replaced, so the returned list has `count`
    distinct configurations or the largest distinct set the space supports.
    """
    axes = SPACES.get(family)
    if axes is None:
        raise KeyError(f"no search space for {family!r}; known: {sorted(SPACES)}")
    if not axes:
        return [{}] if count >= 1 else []

    stream = hashlib.sha256(f"{family}|{stage}|{seed}".encode()).digest()[:8]
    rng = np.random.default_rng(int.from_bytes(stream, "big"))

    seen: set[str] = set()
    configs: list[dict[str, Any]] = []
    attempts = 0
    while len(configs) < count and attempts < count * 40:
        attempts += 1
        params = {axis.name: axis.draw(rng) for axis in axes}
        key = "|".join(f"{k}={params[k]!r}" for k in sorted(params))
        if key in seen:
            continue
        seen.add(key)
        configs.append(params)
    return configs


def neighbours(
    family: str, params: dict[str, Any], count: int, *, seed: int = 0
) -> list[dict[str, Any]]:
    """Configurations near `params`, for the robustness stage.

    A candidate that only works at one exact point in the space and collapses
    beside it is fragile, and the only way to find that out is to look beside
    it. Numeric axes are perturbed multiplicatively within ±35%; categorical
    axes are resampled.
    """
    axes = SPACES.get(family) or []
    if not axes:
        return []
    fingerprint = f"neighbours|{family}|{seed}|" + "|".join(
        f"{k}={params[k]!r}" for k in sorted(params)
    )
    rng = np.random.default_rng(
        int.from_bytes(hashlib.sha256(fingerprint.encode()).digest()[:8], "big")
    )

    out: list[dict[str, Any]] = []
    seen = {"|".join(f"{k}={params[k]!r}" for k in sorted(params))}
    for _ in range(count * 20):
        if len(out) >= count:
            break
        candidate = dict(params)
        for axis in axes:
            base = params.get(axis.name)
            if isinstance(base, bool) or base is None or isinstance(base, str):
                candidate[axis.name] = axis.draw(rng)
            elif isinstance(base, (int, np.integer)):
                scaled = int(round(base * float(rng.uniform(0.65, 1.35))))
                candidate[axis.name] = max(1, scaled)
            elif isinstance(base, (float, np.floating)):
                value = float(base) * float(rng.uniform(0.65, 1.35))
                if axis.name in {"subsample", "l1_ratio"}:
                    value = min(max(value, 0.05), 1.0)
                candidate[axis.name] = value
            else:
                candidate[axis.name] = axis.draw(rng)
        key = "|".join(f"{k}={candidate[k]!r}" for k in sorted(candidate))
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
    return out


def to_spec(family: str, params: dict[str, Any], *, name: str, seed: int = 0) -> ModelSpec:
    """A `ModelSpec` the existing runner already understands."""
    return ModelSpec(
        name=name, kind=family,
        params=tuple(sorted(params.items())), seed=seed,
    )


def estimate_seconds(
    family: str, configs: int, *, feature_count: int = BASELINE_FEATURE_COUNT
) -> float:
    """Estimated worker-seconds, from EXP-006's measured per-config cost."""
    per_config = FAMILY_COST_SECONDS.get(family, 60.0)
    scale = max(feature_count, 1) / BASELINE_FEATURE_COUNT
    return per_config * configs * scale


@dataclass
class SearchPlan:
    """The whole search, resolved before anything is fitted."""

    budget: SearchBudget
    seed: int
    screen: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    estimated_seconds: dict[str, float] = field(default_factory=dict)

    @property
    def screen_configs(self) -> int:
        return sum(len(v) for v in self.screen.values())

    def as_dict(self) -> dict[str, Any]:
        return {
            "budget": self.budget.as_dict(),
            "seed": self.seed,
            "screen_configs": self.screen_configs,
            "screen_by_family": {k: len(v) for k, v in self.screen.items()},
            "estimated_seconds": {k: round(v, 1) for k, v in self.estimated_seconds.items()},
        }


def build_plan(budget_name: str = DEFAULT_BUDGET, *, seed: int = 0) -> SearchPlan:
    if budget_name not in BUDGETS:
        raise KeyError(f"unknown budget {budget_name!r}; known: {sorted(BUDGETS)}")
    budget = BUDGETS[budget_name]
    plan = SearchPlan(budget=budget, seed=seed)
    for family, count in budget.screen.items():
        plan.screen[family] = sample_configs(family, count, stage="screen", seed=seed)
        plan.estimated_seconds[family] = estimate_seconds(family, len(plan.screen[family]))
    return plan


def projected_total(
    budget: SearchBudget,
    *,
    tune_families: Optional[list[str]] = None,
    feature_count: int = BASELINE_FEATURE_COUNT,
) -> dict[str, Any]:
    """Worst-case worker-seconds and configuration count for a budget.

    `tune_families` is unknown before the screen runs, so the projection assumes
    the *most expensive* families advance. That makes the estimate an upper
    bound, which is the honest direction for a number someone will plan a night
    around.
    """
    screen_seconds = sum(
        estimate_seconds(f, n, feature_count=feature_count) for f, n in budget.screen.items()
    )
    ranked = sorted(
        budget.tune.items(),
        key=lambda kv: -estimate_seconds(kv[0], kv[1], feature_count=feature_count),
    )
    advancing = (
        [(f, budget.tune[f]) for f in tune_families]
        if tune_families
        else ranked[: budget.tune_families]
    )
    tune_seconds = sum(
        estimate_seconds(f, n, feature_count=feature_count) for f, n in advancing
    )
    tune_configs = sum(n for _, n in advancing)

    # Context: finalists re-evaluated across arms x targets. Costed at the mean
    # advancing-family rate and at the widest arm's feature count.
    mean_rate = (
        sum(FAMILY_COST_SECONDS.get(f, 60.0) for f, _ in advancing) / max(len(advancing), 1)
    )
    context_evaluations = budget.finalists * len(CONTEXT_ARMS) * len(CONTEXT_TARGETS)
    context_seconds = context_evaluations * mean_rate * (57 / BASELINE_FEATURE_COUNT)

    robustness_configs = budget.finalists * budget.neighbours_per_finalist
    robustness_seconds = robustness_configs * mean_rate

    total_configs = (
        budget.screen_total + tune_configs + context_evaluations + robustness_configs
    )
    total_seconds = screen_seconds + tune_seconds + context_seconds + robustness_seconds
    return {
        "stage_1_screen": {"configs": budget.screen_total, "worker_seconds": round(screen_seconds)},
        "stage_2_tune": {"configs": tune_configs, "worker_seconds": round(tune_seconds),
                         "families": [f for f, _ in advancing]},
        "stage_3_context": {"evaluations": context_evaluations,
                            "worker_seconds": round(context_seconds),
                            "arms": list(CONTEXT_ARMS), "targets": list(CONTEXT_TARGETS)},
        "stage_4_robustness": {"configs": robustness_configs,
                               "worker_seconds": round(robustness_seconds)},
        "total_configs": total_configs,
        "total_worker_seconds": round(total_seconds),
        "note": (
            "Upper bound: the projection assumes the most expensive families "
            "advance from the screen. Costs are EXP-006's measured per-config "
            "timings scaled by feature count."
        ),
        "multiple_testing_cost": multiple_testing_cost(total_configs),
    }


def multiple_testing_cost(new_configs: int, *, prior: int = 156) -> dict[str, Any]:
    """What a budget of this size costs in significance, before it is spent.

    This is the number that should actually constrain how large a search may
    honestly be. Every configuration is a trial, and the deflated-Sharpe
    correction runs against the CUMULATIVE count across all studies. Doubling
    the search does not double the chance of finding something real; it raises
    the bar that a real finding has to clear.

    The expected maximum |t| over N zero-skill configurations is reported so the
    tradeoff is visible in advance rather than discovered in the report.
    """
    cumulative = prior + new_configs
    try:
        from scipy import stats

        # E[max] of N standard normals, and the Bonferroni bar at 5%.
        expected_max = float(stats.norm.ppf(1.0 - 1.0 / (cumulative * np.e)))
        bonferroni = float(stats.norm.ppf(1.0 - 0.05 / (2 * cumulative)))
    except Exception:  # noqa: BLE001
        expected_max = bonferroni = float("nan")
    return {
        "prior_trials": prior,
        "new_trials": new_configs,
        "cumulative_trials": cumulative,
        "expected_max_abs_t_under_null": round(expected_max, 2),
        "bonferroni_threshold_5pct": round(bonferroni, 2),
        "interpretation": (
            f"A search of {new_configs} configurations raises the cumulative count to "
            f"{cumulative}. The best of {cumulative} zero-skill configurations would be "
            f"expected to show |t| ~ {expected_max:.2f}, so a finding must clear that "
            "before it is interesting, and ~{:.2f} to clear Bonferroni at 5%."
        ).format(bonferroni),
    }
