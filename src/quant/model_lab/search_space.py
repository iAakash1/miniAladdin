"""The complete MODEL-LAB-001 universe, declared before results are read."""

from __future__ import annotations

import importlib.util
from dataclasses import asdict, dataclass
from typing import Any

from src.quant.model_lab.models import LabModelSpec


@dataclass(frozen=True)
class Family:
    family: str
    model_name: str
    route: str
    configurations: tuple[dict[str, Any], ...]
    package: str | None = None
    scientific_note: str = ""

    def availability(self) -> dict[str, Any]:
        if self.package and importlib.util.find_spec(self.package) is None:
            return {"status": "BLOCKED", "reason": f"optional dependency `{self.package}` is not installed"}
        if not self.configurations:
            return {"status": "BLOCKED", "reason": self.scientific_note or "no valid specification declared"}
        if self.route == "MAC_CPU" and self.model_name not in CPU_KINDS:
            return {"status": "BLOCKED", "reason": self.scientific_note or "local adapter is not implemented"}
        return {"status": "READY", "reason": "declared search space is executable on its assigned route"}

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "configurations": list(self.configurations), **self.availability()}


FAMILIES: tuple[Family, ...] = (
    Family("linear", "ridge", "MAC_CPU", tuple({"alpha": x} for x in (0.1, 1.0, 10.0, 100.0, 1000.0))),
    Family("linear", "lasso", "MAC_CPU", tuple({"alpha": x} for x in (1e-5, 1e-4, 5e-4, 1e-3))),
    Family("linear", "elastic_net", "MAC_CPU", tuple(
        {"alpha": a, "l1_ratio": r} for a in (1e-4, 5e-4, 1e-3) for r in (0.2, 0.5, 0.8)
    )),
    Family("linear_robust", "huber", "MAC_CPU", tuple(
        {"epsilon": e, "alpha": a} for e in (1.2, 1.5) for a in (1e-4, 1e-3)
    )),
    Family("linear_robust", "sgd_huber", "MAC_CPU", tuple(
        {"epsilon": e, "alpha": a} for e in (0.05, 0.1) for a in (1e-5, 1e-4)
    )),
    Family("linear_dimension_reduced", "pca_ridge", "MAC_CPU", tuple(
        {"variance": v, "alpha": a} for v in (0.80, 0.90, 0.95) for a in (1.0, 10.0, 100.0)
    )),
    Family("linear_dimension_reduced", "pls", "MAC_CPU", tuple({"components": n} for n in (2, 4, 8, 12))),
    Family("bagging", "random_forest", "MAC_CPU", tuple(
        {"n_estimators": 300, "max_depth": d, "min_samples_leaf": leaf, "max_features": mf}
        for d in (6, 10) for leaf in (25, 75) for mf in (0.4, 0.8)
    )),
    Family("bagging", "extra_trees", "MAC_CPU", tuple(
        {"n_estimators": 300, "max_depth": d, "min_samples_leaf": leaf, "max_features": mf}
        for d in (8, 12) for leaf in (25, 75) for mf in (0.4, 0.8)
    )),
    Family("histogram_boosting", "hist_gradient_boosting", "MAC_CPU", tuple(
        {"max_iter": 300, "learning_rate": lr, "max_depth": d,
         "min_samples_leaf": leaf, "l2_regularization": l2}
        for lr in (0.02, 0.05) for d in (3, 5) for leaf in (30, 80) for l2 in (1.0, 10.0)
    )),
    Family("gpu_boosting", "xgboost", "KAGGLE_GPU", ({"budget": 24, "early_stopping": "inner_only"},), "xgboost"),
    Family("gpu_boosting", "lightgbm", "KAGGLE_GPU", ({"budget": 24, "early_stopping": "inner_only"},), "lightgbm"),
    Family("gpu_boosting", "catboost", "KAGGLE_GPU", ({"budget": 18, "early_stopping": "inner_only"},), "catboost"),
    Family("neural", "torch_mlp", "KAGGLE_GPU", ({"architectures": [[128, 64], [128, 64, 32]], "seeds": list(range(10))},), "torch"),
    Family("tabular_transformer", "ft_transformer", "KAGGLE_GPU", (), "torch", "implementation and licence review required after classical families"),
    Family("additive", "explainable_boosting", "MAC_CPU", ({"budget": 8},), "interpret"),
    Family("robust_quantile", "quantile_regression", "MAC_CPU", tuple({"quantile": q, "alpha": a} for q in (0.4, 0.5, 0.6) for a in (0.0, 1e-4)), scientific_note="adapter pending"),
    Family("ranking", "lambdamart_date_query_v2", "KAGGLE_GPU", (), "lightgbm", "materially new date-query formulation must be frozen before execution"),
    Family("ensemble", "rank_average", "POST_OUTER", ({"weights": "equal_by_family"},), scientific_note="only out-of-fold predictions"),
    Family("stacking", "linear_oof_stacker", "POST_OUTER", ({"meta_model": "ridge"},), scientific_note="base inputs must be out-of-fold"),
)

CPU_KINDS = {
    "ridge", "lasso", "elastic_net", "huber", "sgd_huber", "pca_ridge", "pls",
    "random_forest", "extra_trees", "hist_gradient_boosting",
}


def families() -> list[dict[str, Any]]:
    return [family.as_dict() for family in FAMILIES]


def family_for(model_name: str) -> Family:
    matches = [family for family in FAMILIES if family.model_name == model_name]
    if len(matches) != 1:
        raise KeyError(model_name)
    return matches[0]


def build_spec(model_name: str, params: dict[str, Any], seed: int, *, suffix: str) -> LabModelSpec:
    if model_name not in CPU_KINDS:
        raise RuntimeError(f"{model_name} is not executable in the local CPU runner")
    return LabModelSpec(
        name=f"{model_name}_{suffix}", kind=model_name,
        params=tuple(sorted(params.items())), seed=seed,
    )
