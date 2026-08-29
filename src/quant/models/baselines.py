"""
Baselines — the bar every model has to clear before it is interesting.

## Why these specific baselines

Each encodes a different way of being right for a boring reason, and a model
that fails to beat one of them has not learned the thing it appears to have
learned:

``ZeroBaseline``
    Predicts zero. On a 21-session horizon this is close to optimal in squared
    error, because forward returns are mostly noise around a small mean. It is
    the baseline that embarrasses RMSE comparisons, and it should — a model
    reporting "RMSE 0.081 vs zero's 0.080" is not predicting returns.

``HistoricalMeanBaseline``
    Predicts the training fold's mean. Captures drift and nothing else. The gap
    between it and Zero measures how much of the sample's performance is simply
    the market having gone up.

``MomentumBaseline``
    Predicts the 12-1 momentum feature directly. This is the one that matters
    for ranking: a documented cross-sectional effect, free, requiring no
    fitting. A learned model that cannot beat it has, at best, rediscovered it
    expensively. Its scale is not a return, so it is only meaningful for
    rank-based metrics — and `scale_free = True` records that, so the driver
    does not report a meaningless RMSE for it.

``PersistenceBaseline``
    Predicts the trailing realised value of whatever is being predicted. For
    volatility this is genuinely strong — volatility clusters — and it is the
    baseline a volatility model has to beat to be worth anything.

Every one of them implements the same `Model` interface as the learned models,
so the comparison runs through identical code.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from src.quant.models.base import Explanation, Model


class ZeroBaseline(Model):
    """Predicts zero for every row."""

    model_id = "baseline_zero"
    task = "regression"

    def _fit(self, X: np.ndarray, y: np.ndarray) -> None:  # noqa: D401 - nothing to learn
        return None

    def _predict(self, X: np.ndarray) -> np.ndarray:
        return np.zeros(len(X))

    def explain(self) -> Explanation:
        return Explanation(
            kind="constant",
            values={},
            description="Predicts 0 unconditionally; uses no feature.",
            caveat="No attribution exists because no feature is consulted.",
        )


class HistoricalMeanBaseline(Model):
    """Predicts the training fold's mean target."""

    model_id = "baseline_historical_mean"
    task = "regression"

    def __init__(self, *, seed: int = 0, **params) -> None:
        super().__init__(seed=seed, **params)
        self._mean = 0.0

    def _fit(self, X: np.ndarray, y: np.ndarray) -> None:
        self._mean = float(np.mean(y))

    def _predict(self, X: np.ndarray) -> np.ndarray:
        return np.full(len(X), self._mean)

    def explain(self) -> Explanation:
        return Explanation(
            kind="constant",
            values={"training_mean": self._mean},
            description=(
                f"Predicts the training fold's mean target ({self._mean:.6f}); uses no feature."
            ),
            caveat="Captures drift only. Its edge over zero is the sample's average return.",
        )


class FeaturePassthroughBaseline(Model):
    """Predicts one named feature directly, unfitted.

    The generic form of a "free" signal. `MomentumBaseline` is this with
    `mom_252_21`, and the reversal and low-volatility variants are the same
    object with a different column and sign.
    """

    model_id = "baseline_feature"
    task = "regression"
    #: The output is a feature value, not a return. Scale-dependent metrics
    #: (MAE, RMSE) are meaningless for it and the driver skips them rather than
    #: printing a number that invites a false comparison.
    scale_free = True

    def __init__(self, feature: str, *, sign: float = 1.0, seed: int = 0, **params) -> None:
        super().__init__(seed=seed, feature=feature, sign=sign, **params)
        self.feature = feature
        self.sign = float(sign)
        self._column: Optional[int] = None
        self.model_id = f"baseline_{feature}"

    def _fit(self, X: np.ndarray, y: np.ndarray) -> None:
        if self.feature not in self.feature_names:
            raise ValueError(
                f"{self.model_id} needs feature {self.feature!r}, which is not in the "
                f"matrix ({len(self.feature_names)} columns present)"
            )
        self._column = self.feature_names.index(self.feature)

    def _predict(self, X: np.ndarray) -> np.ndarray:
        return self.sign * X[:, self._column]

    def explain(self) -> Explanation:
        return Explanation(
            kind="passthrough",
            values={self.feature: self.sign},
            description=f"Emits {self.feature} directly (sign {self.sign:+.0f}); nothing is fitted.",
            caveat=(
                "Output is a feature value, not a return forecast. Only rank-based "
                "metrics apply; scale-dependent ones are not reported."
            ),
        )


def momentum_baseline(seed: int = 0) -> FeaturePassthroughBaseline:
    """12-1 momentum, cross-sectionally ranked. The bar for any ranking model."""
    return FeaturePassthroughBaseline("mom_252_21_xs", seed=seed)


def reversal_baseline(seed: int = 0) -> FeaturePassthroughBaseline:
    """Short-horizon reversal, already sign-corrected in the feature."""
    return FeaturePassthroughBaseline("reversal_5_xs", seed=seed)


def low_volatility_baseline(seed: int = 0) -> FeaturePassthroughBaseline:
    """Low-volatility effect: negated volatility rank."""
    return FeaturePassthroughBaseline("vol_63_xs", sign=-1.0, seed=seed)


class PersistenceBaseline(Model):
    """Predicts the trailing realised value of the quantity being predicted.

    For volatility this is a strong baseline rather than a straw man: realised
    volatility is highly autocorrelated, so "tomorrow looks like today" is hard
    to beat. Reporting a volatility model without it would overstate the model
    by the entire size of the clustering effect.
    """

    model_id = "baseline_persistence"
    task = "regression"

    def __init__(self, feature: str = "vol_21", *, seed: int = 0, **params) -> None:
        super().__init__(seed=seed, feature=feature, **params)
        self.feature = feature
        self._column: Optional[int] = None
        self._fallback = 0.0
        self.model_id = f"baseline_persistence_{feature}"

    def _fit(self, X: np.ndarray, y: np.ndarray) -> None:
        if self.feature not in self.feature_names:
            raise ValueError(f"{self.model_id} needs feature {self.feature!r}")
        self._column = self.feature_names.index(self.feature)
        self._fallback = float(np.mean(y))

    def _predict(self, X: np.ndarray) -> np.ndarray:
        return X[:, self._column]

    def explain(self) -> Explanation:
        return Explanation(
            kind="passthrough",
            values={self.feature: 1.0},
            description=f"Predicts the trailing realised value ({self.feature}) unchanged.",
            caveat=(
                "Strong for volatility because volatility clusters. A volatility "
                "model that does not beat this has found nothing."
            ),
        )


def regression_baselines(seed: int = 0) -> list[Model]:
    """The baseline set every regression target is measured against."""
    return [
        ZeroBaseline(seed=seed),
        HistoricalMeanBaseline(seed=seed),
        momentum_baseline(seed),
        reversal_baseline(seed),
        low_volatility_baseline(seed),
    ]
