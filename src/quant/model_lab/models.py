"""Model Lab adapters not present in the frozen historical model factory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from src.quant.models.base import Explanation, Model
from src.quant.models.factory import ModelSpec


class _EstimatorModel(Model):
    requires_scaling = True
    task = "regression"

    def __init__(self, *, seed: int = 0, **params: Any) -> None:
        super().__init__(seed=seed, **params)
        self._estimator = None

    def _build(self):  # pragma: no cover - subclasses provide the estimator
        raise NotImplementedError

    def _fit(self, X: np.ndarray, y: np.ndarray) -> None:
        self._estimator = self._build()
        self._estimator.fit(X, y)

    def _predict(self, X: np.ndarray) -> np.ndarray:
        return np.asarray(self._estimator.predict(X), dtype=float).reshape(-1)


class HuberModel(_EstimatorModel):
    model_id = "huber"

    def _build(self):
        from sklearn.linear_model import HuberRegressor

        return HuberRegressor(
            epsilon=float(self.params["epsilon"]), alpha=float(self.params["alpha"]),
            max_iter=500,
        )

    def explain(self) -> Explanation:
        values = dict(zip(self.feature_names, np.ravel(self._estimator.coef_)))
        return Explanation(
            kind="linear_coefficients", values={key: float(value) for key, value in values.items()},
            description="Huber coefficients on fold-local standardised features.",
            caveat="Robust association, not causation; correlated features share credit arbitrarily.",
        )


class SGDHuberModel(_EstimatorModel):
    model_id = "sgd_huber"

    def _build(self):
        from sklearn.linear_model import SGDRegressor

        return SGDRegressor(
            loss="huber", alpha=float(self.params["alpha"]),
            epsilon=float(self.params["epsilon"]), max_iter=3000, tol=1e-5,
            random_state=self.seed, shuffle=True,
        )


class PCARidgeModel(_EstimatorModel):
    model_id = "pca_ridge"

    def _build(self):
        from sklearn.decomposition import PCA
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import Pipeline

        # The pipeline is constructed and fitted inside one inner or outer
        # training split. PCA never sees its validation rows.
        return Pipeline([
            ("pca", PCA(n_components=float(self.params["variance"]), svd_solver="full")),
            ("ridge", Ridge(alpha=float(self.params["alpha"]), solver="cholesky")),
        ])

    def explain(self) -> Explanation:
        return Explanation(
            kind="none", values={},
            description="PCA + Ridge does not expose coefficients in the original feature basis.",
            caveat="Component loadings and Ridge coefficients are not presented as direct feature effects.",
        )


class PLSModel(_EstimatorModel):
    model_id = "pls"

    def _build(self):
        from sklearn.cross_decomposition import PLSRegression

        return PLSRegression(n_components=int(self.params["components"]), scale=False, max_iter=1000)


LAB_MODELS: dict[str, type[Model]] = {
    "huber": HuberModel,
    "sgd_huber": SGDHuberModel,
    "pca_ridge": PCARidgeModel,
    "pls": PLSModel,
}


@dataclass(frozen=True)
class LabModelSpec:
    name: str
    kind: str
    params: tuple[tuple[str, Any], ...]
    seed: int

    def build(self) -> Model:
        if self.kind not in LAB_MODELS:
            return ModelSpec(self.name, self.kind, self.params, self.seed).build()
        model = LAB_MODELS[self.kind](seed=self.seed, **dict(self.params))
        model.model_id = self.name
        return model
