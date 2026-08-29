"""
Model interface — one contract every predictor satisfies, including the trivial ones.

## Why baselines implement the same interface as gradient boosting

Because otherwise they are not really compared. A baseline that lives in a
different code path, is evaluated by different code and reports different
metrics is a rhetorical baseline, not a measured one. Here `ZeroBaseline` and
a gradient-boosted forest are both `Model`s: same `fit`, same `predict`, same
walk-forward driver, same metrics, same registry entry. When the forest fails
to beat "predict zero" — which happens, and is reported — the comparison is
apples to apples by construction.

## What every model must supply

``fit(X, y)`` / ``predict(X)``
    NumPy in, NumPy out. Feature assembly, NaN policy and standardisation
    belong to the pipeline, not to the model, so two models see identical
    inputs.

``explain()``
    Coefficients for a linear model, split-gain importances for a tree, and an
    explicit statement of *what kind of explanation it is*. The product renders
    these as MODEL EXPLANATION, never as a causal claim — a coefficient is a
    conditional association in a fitted model and nothing more.

``fingerprint()``
    Hyperparameters and seed, hashed. Two runs with the same fingerprint on the
    same data must produce the same predictions, and `tests/quant/test_models.py`
    asserts it.

## NaN policy, stated once

Financial feature matrices are sparse by nature: a 252-session momentum does
not exist in a name's first year. The pipeline imputes missing features with
the **training fold's** median and passes a mask. Training-fold, not the whole
sample — computing the median over data the model will be tested on is a small,
real leak that is easy to introduce and invisible afterwards.
"""

from __future__ import annotations

import hashlib
import json
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

import numpy as np


class ModelNotFitted(RuntimeError):
    """Raised when prediction is requested before fitting."""


@dataclass
class Explanation:
    """What a model attributes its output to, and what kind of claim that is."""

    kind: str
    values: dict[str, float]
    description: str
    caveat: str = (
        "An association within a fitted model, conditional on the other features "
        "present. Not a causal statement, and not stable across refits."
    )

    def top(self, n: int = 10) -> list[tuple[str, float]]:
        return sorted(self.values.items(), key=lambda kv: abs(kv[1]), reverse=True)[:n]

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "description": self.description,
            "caveat": self.caveat,
            "values": {k: round(float(v), 6) for k, v in self.values.items()},
            "top": [[name, round(float(value), 6)] for name, value in self.top()],
        }


class Model(ABC):
    """The contract. Deliberately small."""

    #: Stable identifier used by the registry and the provenance chain.
    model_id: str = "unnamed"
    #: Bumped when the implementation changes in a way that alters predictions.
    version: str = "1.0"
    #: "regression" or "classification". Drives which metrics are computed.
    task: str = "regression"
    #: Whether this model needs standardised inputs.
    requires_scaling: bool = False

    def __init__(self, *, seed: int = 0, **params: Any) -> None:
        self.seed = seed
        self.params = dict(params)
        self.feature_names: list[str] = []
        self._fitted = False

    @abstractmethod
    def _fit(self, X: np.ndarray, y: np.ndarray) -> None: ...

    @abstractmethod
    def _predict(self, X: np.ndarray) -> np.ndarray: ...

    def fit(self, X: np.ndarray, y: np.ndarray, *, feature_names: Optional[Sequence[str]] = None) -> "Model":
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        if X.ndim != 2:
            raise ValueError(f"X must be 2-D, got shape {X.shape}")
        if len(X) != len(y):
            raise ValueError(f"X has {len(X)} rows and y has {len(y)}")
        if not np.isfinite(X).all():
            raise ValueError(
                "X contains non-finite values — imputation is the pipeline's job, "
                "and doing it inside the model would hide which fold's statistics were used"
            )
        if not np.isfinite(y).all():
            raise ValueError("y contains non-finite values")
        if len(X) == 0:
            raise ValueError("cannot fit on an empty training fold")
        self.feature_names = list(feature_names or [f"f{i}" for i in range(X.shape[1])])
        self._fit(X, y)
        self._fitted = True
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if not self._fitted:
            raise ModelNotFitted(f"{self.model_id} has not been fitted")
        X = np.asarray(X, dtype=float)
        if X.ndim != 2:
            raise ValueError(f"X must be 2-D, got shape {X.shape}")
        if X.shape[1] != len(self.feature_names):
            raise ValueError(
                f"{self.model_id} was fitted on {len(self.feature_names)} features, "
                f"received {X.shape[1]}"
            )
        out = np.asarray(self._predict(X), dtype=float)
        if out.shape[0] != X.shape[0]:
            raise ValueError("prediction length does not match input rows")
        return out

    def explain(self) -> Explanation:
        """Default: the model offers no attribution.

        Returning an empty explanation is the honest answer for a model that
        has none. Fabricating importances so the UI has something to render is
        precisely the "fake explanation" the brief forbids.
        """
        return Explanation(
            kind="none",
            values={},
            description=f"{self.model_id} exposes no per-feature attribution.",
            caveat="No attribution is available; none is shown.",
        )

    def fingerprint(self) -> str:
        payload = {
            "model_id": self.model_id,
            "version": self.version,
            "seed": self.seed,
            "params": {k: _jsonable(v) for k, v in sorted(self.params.items())},
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]

    def describe(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "version": self.version,
            "task": self.task,
            "seed": self.seed,
            "params": {k: _jsonable(v) for k, v in sorted(self.params.items())},
            "fingerprint": self.fingerprint(),
            "requires_scaling": self.requires_scaling,
        }


@dataclass
class FoldImputer:
    """Median imputation and standardisation fitted on the training fold only.

    Separate from the models on purpose. Fitting a scaler on the full sample is
    one of the easiest leaks to introduce and one of the hardest to notice: the
    features look unchanged, the metrics improve slightly, and nothing in the
    output says why. Keeping it here means one object is fitted per fold and
    reused for that fold's validation, and `tests/quant/test_leakage.py` checks
    the statistics come from training rows alone.
    """

    medians: Optional[np.ndarray] = None
    means: Optional[np.ndarray] = None
    scales: Optional[np.ndarray] = None
    standardise: bool = False
    feature_names: list[str] = field(default_factory=list)

    def fit(self, X: np.ndarray, *, feature_names: Optional[Sequence[str]] = None) -> "FoldImputer":
        X = np.asarray(X, dtype=float)
        self.feature_names = list(feature_names or [])
        # An all-NaN column is an expected state, not an anomaly: a feature can
        # be entirely absent within one fold (a 252-session lookback early in a
        # symbol's history). `nanmedian` warns on it; the warning is suppressed
        # and the condition is handled explicitly on the next line instead.
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            medians = np.nanmedian(X, axis=0)
        # A column that is entirely NaN in the training fold has no median. Zero
        # is the neutral value AFTER standardisation and is used only because
        # the column carries no information in this fold either way — the
        # coverage report names such columns rather than letting them pass
        # unnoticed.
        self.medians = np.where(np.isfinite(medians), medians, 0.0)

        if self.standardise:
            filled = self._fill(X)
            self.means = filled.mean(axis=0)
            scales = filled.std(axis=0, ddof=1)
            # A zero-variance column cannot be standardised. Dividing by a tiny
            # epsilon would turn rounding noise into a large feature value.
            self.scales = np.where(np.isfinite(scales) & (scales > 1e-12), scales, 1.0)
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        if self.medians is None:
            raise ModelNotFitted("FoldImputer has not been fitted")
        out = self._fill(np.asarray(X, dtype=float))
        if self.standardise and self.means is not None and self.scales is not None:
            out = (out - self.means) / self.scales
        return out

    def fit_transform(self, X: np.ndarray, *, feature_names: Optional[Sequence[str]] = None) -> np.ndarray:
        return self.fit(X, feature_names=feature_names).transform(X)

    def _fill(self, X: np.ndarray) -> np.ndarray:
        out = X.copy()
        missing = ~np.isfinite(out)
        if missing.any():
            out[missing] = np.take(self.medians, np.where(missing)[1])
        return out

    def coverage(self, X: np.ndarray) -> dict[str, float]:
        X = np.asarray(X, dtype=float)
        present = np.isfinite(X).mean(axis=0)
        names = self.feature_names or [f"f{i}" for i in range(X.shape[1])]
        return {name: round(float(value), 4) for name, value in zip(names, present)}


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return str(value)
