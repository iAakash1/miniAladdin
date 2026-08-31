"""
EXP-007-WIN-GPU — the search space and definition for the Windows CUDA worker.

A **separate registered experiment**, not an extension of EXP-007. It runs on a
different machine, with different floating-point association, over model
families the Mac environment does not have. Merging its numbers into EXP-007's
artifact would be claiming a reproducibility that does not exist.

## What is held identical, and how

The definition is built with `dataclasses.replace` from `exp_007`, so the fold
geometry, embargo, purge, execution lag, cost sweep, primary half-spread,
targets, universe and seed are identical *by construction* rather than by
someone remembering to copy them. Only three fields move: the experiment id, the
model families, and `prior_evaluations`.

## The part that is easy to miss

**This experiment's trials count against EXP-007's bar too.** They share the
same validation folds, so the cumulative multiple-testing budget is shared. A
1,000-configuration Windows search would raise the |t| that EXP-007's Mac winner
has to clear, from 3.39 toward 3.6 — punishing the Mac result for work done on
another machine.

That is why this budget is small: 4 families, ~148 configurations, taking the
cumulative count from 1,035 to 1,183 and the bar from 3.39 to about 3.42. The
Windows machine is here to test whether a genuinely different model class or a
GPU-native booster finds something the CPU families did not. It is not here to
add trials.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from src.quant.study.experiment import ExperimentDefinition, exp_007
from src.quant.study.search import Axis, _choice, _float_log, _int_log, _uniform

#: Configurations per family, per stage. Declared before the run, like every
#: other budget in this project.
GPU_SCREEN: dict[str, int] = {
    "xgboost": 10,
    "lightgbm": 10,
    "catboost": 6,
    "torch_mlp": 6,
}

GPU_TUNE: dict[str, int] = {
    "xgboost": 40,
    "lightgbm": 40,
    "catboost": 18,
    "torch_mlp": 18,
}

#: Families carried from screen to tune, and finalists carried to robustness.
GPU_TUNE_FAMILIES = 2
GPU_FINALISTS = 3
GPU_NEIGHBOURS = 6


#: One `Axis` per hyperparameter that changes what the model can represent.
#:
#: Redundant knobs are deliberately absent. XGBoost's `gamma` and
#: `min_child_weight` both restrict splitting and searching both spends trials
#: to move along one axis twice; `min_child_weight` is kept because it scales
#: with the sample rather than the loss. `n_estimators` is bounded rather than
#: searched wide because with a fixed learning rate the two trade off almost
#: exactly, and searching both is searching one parameter in a rotated frame.
GPU_SPACES: dict[str, list[Axis]] = {
    "xgboost": [
        Axis("max_depth", _int_log(2, 8),
             "Interaction order. Depth 3 on a low signal-to-noise target is the "
             "conservative default; above 6 the model starts fitting the panel's "
             "cross-sectional noise."),
        Axis("learning_rate", _float_log(0.01, 0.2),
             "Shrinkage per round. Trades off against n_estimators almost exactly."),
        Axis("n_estimators", _int_log(150, 800),
             "Rounds. Bounded rather than wide, because with learning_rate free "
             "this axis is largely redundant with it."),
        Axis("subsample", _uniform(0.5, 1.0),
             "Row sampling per round. The main variance-reduction knob."),
        Axis("colsample_bytree", _uniform(0.4, 1.0),
             "Feature sampling. Matters more here than in most settings because "
             "the 27 C_base features are heavily correlated."),
        Axis("min_child_weight", _float_log(1.0, 200.0),
             "Minimum summed hessian in a leaf — an effective minimum leaf size. "
             "The strongest single guard against fitting a handful of names."),
        Axis("reg_lambda", _float_log(0.1, 50.0),
             "L2 on leaf weights."),
    ],
    "lightgbm": [
        Axis("num_leaves", _int_log(8, 128),
             "Capacity under leaf-wise growth. This, not depth, is the control; "
             "depth is left unlimited so one parameter governs capacity."),
        Axis("learning_rate", _float_log(0.01, 0.2), "Shrinkage per round."),
        Axis("n_estimators", _int_log(150, 800), "Rounds."),
        Axis("min_child_samples", _int_log(20, 500),
             "Minimum rows per leaf. Leaf-wise growth will happily build a leaf "
             "for nine observations without it."),
        Axis("subsample", _uniform(0.5, 1.0), "Row sampling (with subsample_freq=1)."),
        Axis("colsample_bytree", _uniform(0.4, 1.0), "Feature sampling per tree."),
        Axis("reg_lambda", _float_log(0.1, 50.0), "L2 on leaf weights."),
    ],
    "catboost": [
        Axis("depth", _int_log(3, 8),
             "Depth of the oblivious trees. CatBoost applies the same split at "
             "every node of a level, so depth buys much less capacity here than "
             "the same number in XGBoost — the bound is not a typo."),
        Axis("learning_rate", _float_log(0.01, 0.2), "Shrinkage per round."),
        Axis("iterations", _int_log(200, 1000), "Rounds."),
        Axis("l2_leaf_reg", _float_log(1.0, 30.0), "L2 on leaf values."),
    ],
    "torch_mlp": [
        Axis("hidden", _choice([32, 64, 128, 256]),
             "Width. 256 on 27 inputs is already generous."),
        Axis("layers", _choice([1, 2, 3]),
             "Depth. Three layers is the point where this stops being a shallow "
             "model on a small feature set."),
        Axis("dropout", _uniform(0.0, 0.5), "The primary regulariser here."),
        Axis("learning_rate", _float_log(1e-4, 1e-2), "AdamW step size."),
        Axis("weight_decay", _float_log(1e-6, 1e-2), "Decoupled L2."),
        Axis("epochs", _choice([20, 40, 80]),
             "Passes over the training fold. No early stopping: an inner "
             "validation split would either eat training data or leak the "
             "outer validation fold."),
    ],
}


def gpu_experiment(seed: int = 0) -> ExperimentDefinition:
    """EXP-007-WIN-GPU, derived from EXP-007 so the folds cannot drift.

    `prior_evaluations` is 1,035 — EXP-001 through EXP-006 (156) plus EXP-007's
    overnight budget (879). The Windows search discounts against everything
    already spent on these folds, including the search running on the Mac.
    """
    base = exp_007(seed)
    return replace(
        base,
        experiment_id="EXP-007-WIN-GPU",
        objective=(
            "Determine whether GPU-native gradient boosting or a small dense "
            "network finds incremental predictive information on the same folds, "
            "features and target that the CPU families of EXP-007 searched, after "
            "costs and a multiple-testing correction that counts EXP-007's trials "
            "as well as its own."
        ),
        prior_evaluations=1035,
        search_budget=None,
        notes=(
            "Runs on a different machine and a different floating-point path. "
            "Results are NOT merged into EXP-007; they are a separate ledger row "
            "with machine provenance attached.",
            "Fold geometry, embargo, purge, execution lag, cost assumptions, "
            "targets, universe and seed are inherited from EXP-007 by "
            "dataclasses.replace rather than restated, so they cannot drift.",
            "These trials count against the shared cumulative budget. A large "
            "Windows search would raise the bar EXP-007's own winner has to "
            "clear, which is why this budget is deliberately small.",
        ),
    )


def total_configurations() -> int:
    """Upper bound: assumes the two most expensive families advance to tune."""
    screen = sum(GPU_SCREEN.values())
    advancing = sorted(GPU_TUNE.values(), reverse=True)[:GPU_TUNE_FAMILIES]
    return screen + sum(advancing) + GPU_FINALISTS * GPU_NEIGHBOURS


def as_dict() -> dict[str, Any]:
    return {
        "screen": dict(GPU_SCREEN),
        "tune": dict(GPU_TUNE),
        "tune_families": GPU_TUNE_FAMILIES,
        "finalists": GPU_FINALISTS,
        "neighbours_per_finalist": GPU_NEIGHBOURS,
        "total_configurations_upper_bound": total_configurations(),
        "families": sorted(GPU_SPACES),
        "axes": {
            family: {axis.name: axis.description for axis in axes}
            for family, axes in GPU_SPACES.items()
        },
    }
