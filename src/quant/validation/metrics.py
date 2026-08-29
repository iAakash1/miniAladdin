"""
Evaluation metrics — including the ones that make a model look bad.

## Why several, and why they disagree

A single number cannot say whether a return model is useful, and the
disagreements between these are usually the finding:

**RMSE / MAE** measure magnitude accuracy. On forward returns they are
dominated by variance the model cannot predict, so almost every model scores
*worse* than predicting zero. That is a true statement about the problem, and
reporting it prevents a model from being described as accurate when it is not.

**Directional accuracy** measures sign. It must always be read against the
**base rate**, never against 50%: in a sample where 56% of 21-day returns are
positive, a model scoring 56% has learned to say "up". `directional_accuracy`
returns the base rate alongside the score so the comparison cannot be skipped.

**Rank IC** measures ordering within each date's cross-section. It is the
metric that matters for a long/short book, and it is the one where a model can
succeed while failing RMSE — because getting the ordering right does not
require getting the magnitude right at all.

**Calibration** measures whether stated confidence matches realised frequency.
A model that is 70% confident and right 55% of the time is not a good model
with a scaling issue; it is miscalibrated, and its confidence should not be
shown to anyone.

## Significance, with the correction that matters

Overlapping labels make daily IC observations dependent, and the naive
t-statistic on them is inflated — often by around 2x. `ic_summary` therefore
reports a Newey-West t-statistic using `src/research/cross_section.py`'s
existing implementation, reused rather than rewritten so the two research
surfaces in this repository cannot report different significance for the same
series.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

import numpy as np
import pandas as pd

from src.research.cross_section import newey_west_tstat, spearman_ic

#: Below this a fold's metric is not reported. A directional accuracy computed
#: on 12 observations has a standard error near 15 percentage points.
MIN_OBSERVATIONS = 30


@dataclass
class MetricSet:
    """One model's performance on one evaluation set."""

    observations: int
    values: dict[str, Optional[float]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def get(self, name: str) -> Optional[float]:
        return self.values.get(name)

    def as_dict(self) -> dict[str, Any]:
        return {
            "observations": self.observations,
            **{
                name: (round(value, 6) if isinstance(value, float) else value)
                for name, value in self.values.items()
            },
            "notes": list(self.notes),
        }


def _clean(y_true: Sequence[float], y_pred: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    true = np.asarray(y_true, dtype=float)
    pred = np.asarray(y_pred, dtype=float)
    both = np.isfinite(true) & np.isfinite(pred)
    return true[both], pred[both]


def regression_metrics(
    y_true: Sequence[float],
    y_pred: Sequence[float],
    *,
    scale_free: bool = False,
) -> MetricSet:
    """Magnitude and sign accuracy for a continuous target.

    `scale_free=True` suppresses MAE, RMSE and R² for a predictor whose output
    is not in the target's units — a raw factor value, for instance. Printing
    an RMSE for those would invite a comparison that means nothing, and a
    metric that means nothing is worse than a missing one.
    """
    true, pred = _clean(y_true, y_pred)
    metrics = MetricSet(observations=len(true))
    if len(true) < MIN_OBSERVATIONS:
        metrics.notes.append(f"fewer than {MIN_OBSERVATIONS} paired observations")
        return metrics

    if not scale_free:
        errors = pred - true
        metrics.values["mae"] = float(np.mean(np.abs(errors)))
        metrics.values["rmse"] = float(np.sqrt(np.mean(errors**2)))
        variance = float(np.var(true, ddof=0))
        metrics.values["r2"] = (
            float(1.0 - np.mean(errors**2) / variance) if variance > 0 else None
        )
        # The comparison that matters. A model whose RMSE exceeds the
        # zero-prediction RMSE has negative skill on magnitude, however good
        # its ordering is, and this ratio says so in one number.
        zero_rmse = float(np.sqrt(np.mean(true**2)))
        metrics.values["rmse_vs_zero"] = (
            float(metrics.values["rmse"] / zero_rmse) if zero_rmse > 0 else None
        )
    else:
        metrics.notes.append(
            "scale-dependent metrics (MAE/RMSE/R2) suppressed: this predictor's "
            "output is not in the target's units"
        )

    directional = directional_accuracy(true, pred)
    metrics.values.update(directional)

    if np.std(pred) > 0 and np.std(true) > 0:
        metrics.values["pearson"] = float(np.corrcoef(pred, true)[0, 1])
        metrics.values["spearman"] = float(
            pd.Series(pred).rank().corr(pd.Series(true).rank())
        )
    else:
        metrics.values["pearson"] = None
        metrics.values["spearman"] = None
        metrics.notes.append("prediction or target has zero variance")
    return metrics


def directional_accuracy(y_true: Sequence[float], y_pred: Sequence[float]) -> dict[str, Optional[float]]:
    """Sign agreement, reported next to the base rate it must beat.

    The base rate is not decoration. In an equity sample with a positive drift,
    the majority of forward returns are positive, so a constant "up" prediction
    scores well above 50%. `directional_edge` is accuracy minus base rate and
    is the only one of the three worth reading alone.
    """
    true, pred = _clean(y_true, y_pred)
    if len(true) < MIN_OBSERVATIONS:
        return {"directional_accuracy": None, "base_rate": None, "directional_edge": None}
    actual_up = true > 0
    predicted_up = pred > 0
    accuracy = float(np.mean(actual_up == predicted_up))
    base_rate = float(np.mean(actual_up))
    # The naive constant predictor picks the majority class.
    naive = max(base_rate, 1.0 - base_rate)
    return {
        "directional_accuracy": accuracy,
        "base_rate": base_rate,
        "directional_edge": accuracy - naive,
    }


def classification_metrics(
    y_true: Sequence[float], y_proba: Sequence[float], *, threshold: float = 0.5
) -> MetricSet:
    """Accuracy, Brier score and log loss for a probability output."""
    true, proba = _clean(y_true, y_proba)
    metrics = MetricSet(observations=len(true))
    if len(true) < MIN_OBSERVATIONS:
        metrics.notes.append(f"fewer than {MIN_OBSERVATIONS} paired observations")
        return metrics

    predicted = (proba >= threshold).astype(float)
    base_rate = float(np.mean(true))
    metrics.values["accuracy"] = float(np.mean(predicted == true))
    metrics.values["base_rate"] = base_rate
    metrics.values["accuracy_edge"] = metrics.values["accuracy"] - max(base_rate, 1 - base_rate)
    metrics.values["brier"] = float(np.mean((proba - true) ** 2))
    # Brier for a constant base-rate forecast. A model above this is worse than
    # knowing nothing but the unconditional frequency.
    metrics.values["brier_vs_base_rate"] = float(
        metrics.values["brier"] / np.mean((base_rate - true) ** 2)
    ) if np.mean((base_rate - true) ** 2) > 0 else None
    clipped = np.clip(proba, 1e-9, 1 - 1e-9)
    metrics.values["log_loss"] = float(
        -np.mean(true * np.log(clipped) + (1 - true) * np.log(1 - clipped))
    )
    return metrics


def calibration_bins(
    y_true: Sequence[float], y_proba: Sequence[float], *, bins: int = 10, min_per_bin: int = 20
) -> list[dict[str, Any]]:
    """A reliability diagram: predicted probability against realised frequency.

    Bins with fewer than `min_per_bin` observations are omitted rather than
    plotted. A bin holding three observations produces a realised frequency of
    0, 1/3, 2/3 or 1 — which renders as dramatic miscalibration and is
    arithmetic.
    """
    true, proba = _clean(y_true, y_proba)
    if len(true) < MIN_OBSERVATIONS:
        return []
    edges = np.linspace(0.0, 1.0, bins + 1)
    out: list[dict[str, Any]] = []
    for i in range(bins):
        mask = (proba >= edges[i]) & (proba < edges[i + 1] if i < bins - 1 else proba <= edges[i + 1])
        count = int(mask.sum())
        if count < min_per_bin:
            continue
        out.append(
            {
                "bin": f"{edges[i]:.1f}-{edges[i + 1]:.1f}",
                "predicted": round(float(np.mean(proba[mask])), 4),
                "realised": round(float(np.mean(true[mask])), 4),
                "count": count,
            }
        )
    return out


def expected_calibration_error(
    y_true: Sequence[float], y_proba: Sequence[float], *, bins: int = 10
) -> Optional[float]:
    """Weighted mean gap between predicted and realised frequency."""
    rows = calibration_bins(y_true, y_proba, bins=bins)
    if not rows:
        return None
    total = sum(row["count"] for row in rows)
    return float(
        sum(row["count"] * abs(row["predicted"] - row["realised"]) for row in rows) / total
    )


def per_date_ic(
    frame: pd.DataFrame,
    *,
    prediction_column: str,
    target_column: str,
    date_column: str = "date",
) -> pd.Series:
    """Rank IC on each date, indexed by date.

    Delegates to `src/research/cross_section.spearman_ic`, which returns None
    rather than 0.0 for a date with no ranking — so a thin date is a missing
    observation rather than a zero folded into the mean as evidence.
    """
    values: dict[Any, float] = {}
    for day, group in frame.groupby(date_column, sort=True):
        ic = spearman_ic(group[prediction_column], group[target_column])
        if ic is not None:
            values[day] = ic
    return pd.Series(values, dtype=float)


def ic_summary(
    ic_series: pd.Series, *, horizon_sessions: int, step_sessions: int
) -> dict[str, Any]:
    """Mean IC with an autocorrelation-robust t-statistic.

    Lags are `ceil(horizon / step) - 1`: the number of subsequent observations
    whose label windows overlap this one. With a 21-session label sampled every
    5 sessions that is 4 lags, and ignoring them inflates the t-statistic by
    roughly a factor of two — which is the difference between a factor that is
    significant and one that is not.
    """
    values = pd.to_numeric(ic_series, errors="coerce").dropna().to_numpy()
    if len(values) < 8:
        return {
            "observations": int(len(values)),
            "mean_ic": None,
            "t_stat": None,
            "note": "fewer than 8 dated IC observations",
        }
    lags = max(0, int(np.ceil(horizon_sessions / max(1, step_sessions))) - 1)
    positive = float(np.mean(values > 0))
    mean = float(np.mean(values))
    std = float(np.std(values, ddof=1))
    return {
        "observations": int(len(values)),
        "mean_ic": mean,
        "median_ic": float(np.median(values)),
        "std_ic": std,
        # Grinold-Kahn: the ratio of mean IC to its dispersion, the closest
        # thing to a Sharpe ratio a signal has.
        "ic_ir": float(mean / std) if std > 0 else None,
        "hit_rate": positive,
        "t_stat": float(newey_west_tstat(values, lags)),
        "newey_west_lags": lags,
        "naive_t_stat": float(mean / (std / np.sqrt(len(values)))) if std > 0 else None,
    }


def bootstrap_interval(
    values: Sequence[float],
    *,
    statistic=np.mean,
    samples: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
    block: int = 1,
) -> dict[str, Any]:
    """Bootstrap confidence interval, blocked when observations overlap.

    `block > 1` selects the moving-block bootstrap, which resamples contiguous
    runs instead of individual points. That is required here: with overlapping
    labels the observations are dependent, and an i.i.d. bootstrap would
    produce an interval far too narrow — understating uncertainty in exactly
    the direction that flatters a result.
    """
    array = np.asarray([v for v in values if np.isfinite(v)], dtype=float)
    if len(array) < 20:
        return {"point": None, "lower": None, "upper": None, "samples": 0}

    rng = np.random.default_rng(seed)
    point = float(statistic(array))
    draws = np.empty(samples)

    if block <= 1:
        for i in range(samples):
            draws[i] = statistic(rng.choice(array, size=len(array), replace=True))
    else:
        block = min(block, len(array))
        starts_available = len(array) - block + 1
        blocks_needed = int(np.ceil(len(array) / block))
        for i in range(samples):
            starts = rng.integers(0, starts_available, size=blocks_needed)
            sample = np.concatenate([array[s : s + block] for s in starts])[: len(array)]
            draws[i] = statistic(sample)

    alpha = (1.0 - confidence) / 2.0
    return {
        "point": point,
        "lower": float(np.quantile(draws, alpha)),
        "upper": float(np.quantile(draws, 1 - alpha)),
        "samples": samples,
        "block": block,
        "confidence": confidence,
        "excludes_zero": bool(
            np.quantile(draws, alpha) > 0 or np.quantile(draws, 1 - alpha) < 0
        ),
    }
