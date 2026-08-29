"""
Significance — correcting for the fact that many things were tried.

## The problem these address

Run forty backtests and the best one looks good whether or not anything works.
Its Sharpe ratio is the maximum of forty draws, and the maximum of forty draws
from a zero-mean distribution is comfortably positive. A research process that
reports the winner's Sharpe without accounting for the forty is not reporting a
result; it is reporting a selection.

Two corrections are implemented, both from Bailey & Lopez de Prado, and each is
implemented **only to the extent it can be done correctly** — a
misimplemented significance test is worse than none, because it launders the
same bias through a formula that looks rigorous.

## Deflated Sharpe Ratio

`deflated_sharpe_ratio` adjusts an observed Sharpe for three things at once:
the number of trials, the return distribution's skew and kurtosis, and the
sample length. It answers: given that N strategies were tried, what is the
probability this Sharpe exceeds what the *best of N* zero-skill strategies
would have produced?

The expected maximum Sharpe under the null is the extreme-value approximation
for N draws, **scaled by the dispersion of the trial Sharpes**:

    E[max SR] ≈ sqrt(V[SR]) · [ (1 - γ) Φ⁻¹(1 - 1/N) + γ Φ⁻¹(1 - 1/(N·e)) ]

with γ the Euler-Mascheroni constant. The `sqrt(V[SR])` factor is not optional
and dropping it is a real error, not a simplification: without it the threshold
is expressed in units of a standard normal rather than in units of a Sharpe
estimate, and for N=200 it produces an expected maximum around 2.8 per period —
roughly 20 annualised, a threshold no strategy could clear and which would
therefore declare everything insignificant.

`V[SR]` is the variance of the Sharpe ratios **across the trials actually run**,
and `trial_sharpes` is how a caller supplies them. When they are not available,
the estimator's own sampling variance under non-normal returns (Lo, 2002) is
used instead, and `variance_source` on the result records which was used —
because the two answer slightly different questions and the reader should know
which one produced the number.

Bailey & Lopez de Prado (2014).

## Probability of Backtest Overfitting

`probability_of_backtest_overfitting` implements combinatorially symmetric
cross-validation: split the period into S blocks, take every way of choosing
S/2 for training, pick the configuration that was best in-sample, and record
where it ranks out-of-sample. PBO is the frequency with which that choice lands
in the bottom half. A PBO near 0.5 means in-sample selection carries no
information about out-of-sample rank.

It requires a **matrix of per-period returns for every configuration tried** —
not just the winner. Given only one series it returns `None` with a reason,
rather than a number, because there is no honest way to estimate overfitting
from a single configuration.

## What is deliberately not implemented

White's Reality Check and Hansen's SPA. Both need a stationary bootstrap over
the full set of candidate return series with a correctly chosen block length,
and getting the block length wrong silently changes the answer. Rather than
ship a version that produces a plausible number under conditions nobody
checked, they are absent and this paragraph says so. `docs/modeling-methodology.md`
records it as a known gap.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional, Sequence

import numpy as np

#: Euler-Mascheroni constant, for the expected maximum of N normal draws.
EULER_MASCHERONI = 0.5772156649015329

MIN_OBSERVATIONS = 30


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _normal_ppf(p: float) -> float:
    """Inverse normal CDF (Acklam's rational approximation, ~1e-9 accurate).

    Implemented here rather than taken from scipy so the significance layer has
    no hard dependency: it must remain runnable wherever a result is being
    checked, including an environment without the optional quant extras.
    """
    if not 0.0 < p < 1.0:
        raise ValueError(f"probability must be in (0, 1), got {p}")

    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00]
    low, high = 0.02425, 1 - 0.02425

    if p < low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > high:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


@dataclass
class DeflatedSharpe:
    """An observed Sharpe, and what it is worth given how many were tried."""

    observed_sharpe: float
    deflated_probability: Optional[float]
    expected_max_sharpe: float
    trials: int
    observations: int
    skew: float
    kurtosis: float
    significant: Optional[bool]
    variance_source: str = "estimator"
    trial_sharpe_std: Optional[float] = None
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "observed_sharpe": round(self.observed_sharpe, 4),
            "deflated_probability": (
                round(self.deflated_probability, 4) if self.deflated_probability is not None else None
            ),
            "expected_max_sharpe_under_null": round(self.expected_max_sharpe, 4),
            "trials": self.trials,
            "observations": self.observations,
            "skew": round(self.skew, 4),
            "excess_kurtosis": round(self.kurtosis, 4),
            "significant": self.significant,
            "variance_source": self.variance_source,
            "trial_sharpe_std": (
                round(self.trial_sharpe_std, 4) if self.trial_sharpe_std is not None else None
            ),
            "note": self.note,
            "methodology": (
                "Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014). Adjusts for the "
                "number of configurations tried, for non-normal returns, and for sample "
                "length. Significance is a deflated probability above 0.95."
            ),
        }


def deflated_sharpe_ratio(
    returns: Sequence[float],
    *,
    trials: int,
    periods_per_year: float = 252.0,
    benchmark_sharpe: float = 0.0,
    trial_sharpes: Optional[Sequence[float]] = None,
) -> DeflatedSharpe:
    """Probability that an observed Sharpe beats the best of `trials` zero-skill runs.

    `trials` must be the number of configurations actually evaluated, not the
    number reported. Passing 1 after selecting from forty is the error this
    function exists to prevent, so it is worth stating: the caller supplies
    `ExperimentLog.distribution()["experiments"]`, not a hand-written 1.

    `trial_sharpes` is the per-period Sharpe of every configuration tried. Pass
    it when available: the dispersion of the actual trials is the quantity the
    deflation is defined on, and the estimator-variance fallback is only an
    approximation of it.
    """
    values = np.asarray([v for v in returns if np.isfinite(v)], dtype=float)
    if len(values) < MIN_OBSERVATIONS:
        return DeflatedSharpe(
            observed_sharpe=float("nan"), deflated_probability=None,
            expected_max_sharpe=float("nan"), trials=trials, observations=len(values),
            skew=float("nan"), kurtosis=float("nan"), significant=None,
            note=f"fewer than {MIN_OBSERVATIONS} periods",
        )

    n = len(values)
    mean, std = float(np.mean(values)), float(np.std(values, ddof=1))
    if std <= 0:
        return DeflatedSharpe(
            observed_sharpe=0.0, deflated_probability=None, expected_max_sharpe=0.0,
            trials=trials, observations=n, skew=0.0, kurtosis=0.0, significant=None,
            note="zero return variance",
        )

    # Per-period Sharpe throughout — the deflation formula's variance term is
    # defined on the per-period statistic, and annualising before deflating is
    # a common error that inflates the result.
    sharpe = mean / std
    centred = (values - mean) / std
    skew = float(np.mean(centred**3))
    kurtosis = float(np.mean(centred**4))

    # Variance of the Sharpe estimator under non-normal returns (Lo, 2002).
    denominator = 1.0 - skew * sharpe + (kurtosis - 1.0) / 4.0 * sharpe**2

    trials = max(1, int(trials))
    variance_source = "estimator"
    trial_sharpe_std: Optional[float] = None
    if trial_sharpes is not None:
        finite = np.asarray([v for v in trial_sharpes if np.isfinite(v)], dtype=float)
        if len(finite) >= 2:
            trial_sharpe_std = float(np.std(finite, ddof=1))
            variance_source = "trial_dispersion"
    if trial_sharpe_std is None:
        # Fallback: the sampling standard deviation of a single Sharpe estimate.
        trial_sharpe_std = math.sqrt(max(denominator, 1e-12) / max(n - 1, 1))

    if trials == 1:
        expected_max = 0.0
    else:
        expected_max = trial_sharpe_std * (
            (1 - EULER_MASCHERONI) * _normal_ppf(1 - 1 / trials)
            + EULER_MASCHERONI * _normal_ppf(1 - 1 / (trials * math.e))
        )

    threshold = max(benchmark_sharpe, expected_max)
    if denominator <= 0 or n <= 1:
        return DeflatedSharpe(
            observed_sharpe=sharpe * math.sqrt(periods_per_year),
            deflated_probability=None, expected_max_sharpe=threshold, trials=trials,
            observations=n, skew=skew, kurtosis=kurtosis - 3.0, significant=None,
            note="Sharpe estimator variance is non-positive under the observed moments",
        )

    statistic = (sharpe - threshold) * math.sqrt(n - 1) / math.sqrt(denominator)
    probability = _normal_cdf(statistic)

    return DeflatedSharpe(
        observed_sharpe=sharpe * math.sqrt(periods_per_year),
        deflated_probability=probability,
        expected_max_sharpe=threshold * math.sqrt(periods_per_year),
        trials=trials,
        observations=n,
        skew=skew,
        kurtosis=kurtosis - 3.0,
        significant=bool(probability > 0.95),
        variance_source=variance_source,
        trial_sharpe_std=trial_sharpe_std,
        note=(
            f"Compared against the best of {trials} zero-skill configuration(s), with the "
            f"null threshold scaled by the {variance_source.replace('_', ' ')} Sharpe "
            "dispersion. Annualised figures shown; deflation computed per period."
        ),
    )


def probability_of_backtest_overfitting(
    configuration_returns: np.ndarray,
    *,
    blocks: int = 8,
    max_combinations: int = 500,
    seed: int = 0,
) -> dict[str, Any]:
    """Combinatorially symmetric cross-validation PBO.

    `configuration_returns` is `(periods, configurations)` — every configuration
    tried, not the winner. Given a single column this returns None with a
    reason, because overfitting is a property of a *selection process* and
    cannot be estimated from the thing that was selected.

    Bailey, Borwein, Lopez de Prado & Zhu (2016).
    """
    matrix = np.asarray(configuration_returns, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("configuration_returns must be (periods, configurations)")
    periods, configurations = matrix.shape

    if configurations < 2:
        return {
            "pbo": None,
            "configurations": configurations,
            "note": (
                "PBO measures whether in-sample selection predicts out-of-sample rank. "
                "With one configuration there was no selection, so it is undefined — "
                "returning a number here would be inventing one."
            ),
        }
    if periods < blocks * 4:
        return {
            "pbo": None,
            "configurations": configurations,
            "note": f"{periods} periods cannot support {blocks} blocks with usable halves",
        }

    from itertools import combinations

    edges = np.array_split(np.arange(periods), blocks)
    half = blocks // 2
    all_splits = list(combinations(range(blocks), half))
    rng = np.random.default_rng(seed)
    if len(all_splits) > max_combinations:
        chosen = rng.choice(len(all_splits), size=max_combinations, replace=False)
        all_splits = [all_splits[i] for i in chosen]

    logits: list[float] = []
    for train_blocks in all_splits:
        train_index = np.concatenate([edges[b] for b in train_blocks])
        test_index = np.concatenate(
            [edges[b] for b in range(blocks) if b not in train_blocks]
        )
        train, test = matrix[train_index], matrix[test_index]

        with np.errstate(divide="ignore", invalid="ignore"):
            train_sharpe = train.mean(axis=0) / train.std(axis=0, ddof=1)
            test_sharpe = test.mean(axis=0) / test.std(axis=0, ddof=1)
        train_sharpe = np.nan_to_num(train_sharpe, nan=-np.inf)
        test_sharpe = np.nan_to_num(test_sharpe, nan=-np.inf)

        best = int(np.argmax(train_sharpe))
        # Relative rank of the in-sample winner among out-of-sample results.
        rank = float((test_sharpe <= test_sharpe[best]).sum()) / configurations
        rank = min(max(rank, 1.0 / (configurations + 1)), configurations / (configurations + 1))
        logits.append(math.log(rank / (1.0 - rank)))

    array = np.asarray(logits)
    pbo = float(np.mean(array <= 0.0))
    return {
        "pbo": pbo,
        "configurations": configurations,
        "splits_evaluated": len(all_splits),
        "blocks": blocks,
        "median_logit": float(np.median(array)),
        "interpretation": (
            f"The configuration chosen in-sample landed in the bottom half out-of-sample "
            f"{pbo:.0%} of the time. Near 0.5 means in-sample selection carries no "
            "information about out-of-sample rank; below ~0.2 is where selection is "
            "doing real work."
        ),
        "methodology": "Combinatorially symmetric cross-validation (Bailey et al., 2016).",
    }


def minimum_track_record_length(
    returns: Sequence[float], *, target_sharpe: float = 0.0, confidence: float = 0.95
) -> dict[str, Any]:
    """How many periods are needed to call this Sharpe distinguishable from `target`.

    Frequently the most sobering number in a research report: a strategy with a
    Sharpe of 0.5 and mildly negative skew can need a decade of observations
    before the estimate separates from zero. Reporting it next to a three-year
    backtest is the honest framing.
    """
    values = np.asarray([v for v in returns if np.isfinite(v)], dtype=float)
    if len(values) < MIN_OBSERVATIONS:
        return {"required_periods": None, "note": "too few observations"}

    mean, std = float(np.mean(values)), float(np.std(values, ddof=1))
    if std <= 0:
        return {"required_periods": None, "note": "zero variance"}
    sharpe = mean / std
    if sharpe <= target_sharpe:
        return {
            "required_periods": None,
            "observed_sharpe_per_period": sharpe,
            "note": "observed Sharpe does not exceed the target — no length suffices",
        }

    centred = (values - mean) / std
    skew = float(np.mean(centred**3))
    kurtosis = float(np.mean(centred**4))
    z = _normal_ppf(confidence)
    numerator = 1.0 - skew * sharpe + (kurtosis - 1.0) / 4.0 * sharpe**2
    required = 1.0 + numerator * (z / (sharpe - target_sharpe)) ** 2

    return {
        "required_periods": int(math.ceil(required)),
        "observed_periods": len(values),
        "observed_sharpe_per_period": sharpe,
        "sufficient": bool(len(values) >= required),
        "confidence": confidence,
        "methodology": "Minimum Track Record Length (Bailey & Lopez de Prado, 2012).",
    }
