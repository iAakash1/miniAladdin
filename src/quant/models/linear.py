"""
Linear models — ridge, lasso, elastic net, and regularised logistic regression.

## Why linear models are first-class here, not a formality

On a feature matrix this size with a signal this weak, a regularised linear
model is frequently the *best* model, not the warm-up act. Forward returns
have a low signal-to-noise ratio, and the flexibility that lets a tree fit
structure also lets it fit noise. Reporting linear results alongside tree
results — rather than as a stepping stone that gets discarded once the tree is
built — is how the comparison stays honest.

They also carry two properties trees do not:

**Coefficients are an explanation with a defined meaning.** A coefficient is
the model's estimated association between one feature and the target holding
the others fixed. Not a cause, not a trading rule, but a statement with
content — and it is stable enough across folds that its *sign* flipping is
itself a finding.

**Regularisation path is a redundancy test.** Lasso driving `mom_63` to zero
while keeping `mom_252_21` is direct evidence about which of two correlated
momentum horizons carries the information, and it agrees or disagrees with
`src/research/redundancy.py`'s participation ratio.

## Scaling, and where it happens

These models are scale-sensitive: an unscaled `log_dollar_volume_21` at ~18 and
a `mom_21` at ~0.02 make the penalty term meaningless. `requires_scaling = True`
tells the pipeline to fit a `FoldImputer(standardise=True)`, which computes its
statistics on the **training fold only**. That is deliberately not the model's
job — a scaler fitted inside `fit` on data the fold also validates against is a
leak that no downstream metric can reveal.

## Dependency

scikit-learn, BSD-3-Clause, listed in `requirements-quant.txt` rather than
`requirements.txt`. The web process does not import it, so a deployment that
serves research pages does not carry scipy. `SKLEARN_AVAILABLE` is exported so
callers can report the capability as `unavailable` rather than failing at
import — the same explicit-degradation pattern the provider fabric uses.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from src.quant.models.base import Explanation, Model

try:  # pragma: no cover - exercised by the availability test
    from sklearn.linear_model import (
        ElasticNet as _ElasticNet,
        Lasso as _Lasso,
        LinearRegression as _LinearRegression,
        LogisticRegression as _LogisticRegression,
        Ridge as _Ridge,
    )

    SKLEARN_AVAILABLE = True
    SKLEARN_IMPORT_ERROR: Optional[str] = None
except ImportError as error:  # pragma: no cover
    SKLEARN_AVAILABLE = False
    SKLEARN_IMPORT_ERROR = str(error)


def _require_sklearn(model_id: str) -> None:
    if not SKLEARN_AVAILABLE:
        raise RuntimeError(
            f"{model_id} needs scikit-learn, which is not installed "
            f"({SKLEARN_IMPORT_ERROR}). Install requirements-quant.txt. "
            "This capability reports as unavailable rather than substituting a "
            "simpler model, because a silently different model is a wrong result."
        )


class _SklearnLinear(Model):
    """Shared plumbing: fit, predict, and coefficients as the explanation."""

    requires_scaling = True

    def __init__(self, *, seed: int = 0, **params: Any) -> None:
        super().__init__(seed=seed, **params)
        self._estimator = None

    def _build(self):  # pragma: no cover - overridden
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
        coefficients = np.ravel(getattr(self._estimator, "coef_", np.array([])))
        values = {
            name: float(value)
            for name, value in zip(self.feature_names, coefficients)
        }
        nonzero = sum(1 for value in values.values() if abs(value) > 1e-12)
        return Explanation(
            kind="linear_coefficients",
            values=values,
            description=(
                f"Fitted coefficients on standardised features; {nonzero} of "
                f"{len(values)} are non-zero."
            ),
            caveat=(
                "A coefficient is the estimated association with the target holding "
                "the other features fixed, on standardised inputs. It is not a causal "
                "effect and not a trading rule, and correlated features share credit "
                "arbitrarily between them."
            ),
        )


class OrdinaryLeastSquares(_SklearnLinear):
    """Unregularised least squares. Included as the overfitting control.

    With 30-odd correlated features it is expected to validate *worse* than
    ridge, and reporting that gap is the cleanest demonstration in the study
    that regularisation is doing real work rather than being assumed to.
    """

    model_id = "ols"
    task = "regression"

    def _build(self):
        return _LinearRegression()


class RidgeRegression(_SklearnLinear):
    """L2-regularised least squares.

    The default for a wide, correlated, low-signal matrix: it shrinks
    coefficients without forcing selection, which suits features that genuinely
    share information rather than substituting for one another.
    """

    model_id = "ridge"
    task = "regression"

    def __init__(self, *, alpha: float = 10.0, seed: int = 0, **params: Any) -> None:
        super().__init__(seed=seed, alpha=alpha, **params)
        self.alpha = alpha

    def _build(self):
        return _Ridge(alpha=self.alpha, random_state=self.seed, solver="cholesky")


class LassoRegression(_SklearnLinear):
    """L1-regularised least squares — selection as well as shrinkage.

    Read as a redundancy diagnostic as much as a predictor: which of several
    correlated features survives the penalty is direct evidence about where the
    information actually sits.
    """

    model_id = "lasso"
    task = "regression"

    def __init__(self, *, alpha: float = 0.0005, seed: int = 0, **params: Any) -> None:
        super().__init__(seed=seed, alpha=alpha, **params)
        self.alpha = alpha

    def _build(self):
        return _Lasso(alpha=self.alpha, random_state=self.seed, max_iter=20000)


class ElasticNetRegression(_SklearnLinear):
    """L1 + L2. The compromise when features are both correlated and numerous.

    Pure lasso picks one of a correlated group essentially at random and the
    choice is unstable across folds — which shows up as a signal that looks
    fragile when the instability is the estimator's, not the market's.
    """

    model_id = "elastic_net"
    task = "regression"

    def __init__(
        self, *, alpha: float = 0.0005, l1_ratio: float = 0.5, seed: int = 0, **params: Any
    ) -> None:
        super().__init__(seed=seed, alpha=alpha, l1_ratio=l1_ratio, **params)
        self.alpha = alpha
        self.l1_ratio = l1_ratio

    def _build(self):
        return _ElasticNet(
            alpha=self.alpha, l1_ratio=self.l1_ratio, random_state=self.seed, max_iter=20000
        )


class LogisticDirection(_SklearnLinear):
    """L2-regularised logistic regression for the direction label.

    Kept because it produces *calibrated-ish* probabilities that can be checked
    against realised frequencies, which a regression cannot. `predict` returns
    the positive-class probability rather than a hard label, so calibration and
    abstention are computable downstream — a hard 0/1 discards exactly the
    information the confidence layer needs.
    """

    model_id = "logistic_direction"
    task = "classification"

    def __init__(self, *, C: float = 0.1, seed: int = 0, **params: Any) -> None:
        super().__init__(seed=seed, C=C, **params)
        self.C = C

    def _build(self):
        return _LogisticRegression(
            C=self.C, random_state=self.seed, max_iter=5000, solver="lbfgs"
        )

    def _fit(self, X: np.ndarray, y: np.ndarray) -> None:
        _require_sklearn(self.model_id)
        classes = np.unique(y)
        if len(classes) < 2:
            raise ValueError(
                f"{self.model_id}: the training fold contains only class {classes.tolist()} — "
                "a classifier fitted on one class predicts a constant and its accuracy is "
                "the base rate, which would be reported as skill"
            )
        self._estimator = self._build()
        self._estimator.fit(X, y)

    def _predict(self, X: np.ndarray) -> np.ndarray:
        return self._estimator.predict_proba(X)[:, 1]


def regression_models(seed: int = 0) -> list[Model]:
    if not SKLEARN_AVAILABLE:
        return []
    return [
        OrdinaryLeastSquares(seed=seed),
        RidgeRegression(alpha=10.0, seed=seed),
        LassoRegression(alpha=0.0005, seed=seed),
        ElasticNetRegression(alpha=0.0005, l1_ratio=0.5, seed=seed),
    ]
