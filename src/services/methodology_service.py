"""The methodology handbook, generated from the engine rather than written out.

A handbook maintained by hand drifts from the code the first time a convention
changes, and a drifted handbook is worse than none: it is a confident statement
about how a number was computed that is no longer true.

So everything here is derived. Units and annualisation come from the risk
engine's own `METHODOLOGY` table, the applicability rule comes from
`RETURN_ONLY_METRICS`, and the observation floor comes from `MIN_OBSERVATIONS`.
When a metric changes convention, this changes with it.

Only the prose fields — what a measure is for, and what makes it fail — are
authored here, because those are not derivable from the table. They are held
next to the derived fields so a reader can see which is which.
"""

from __future__ import annotations

from typing import Any

from src.quant.risk.engine import (
    METHODOLOGY,
    MIN_OBSERVATIONS,
    RETURN_ONLY_METRICS,
)

#: Purpose and failure conditions. Prose, and marked as such in the payload.
#:
#: "fails_when" is the field that matters. A measure's assumptions are only
#: useful to a reader who is told what breaks them.
NOTES: dict[str, dict[str, str]] = {
    "volatility": {
        "purpose": "Dispersion of returns about their own mean.",
        "fails_when": "Returns are not close to normal. A fat tail is invisible "
                      "here, which is why the tail measures are reported beside it.",
    },
    "downside_deviation": {
        "purpose": "Dispersion of the losing periods only.",
        "fails_when": "Few periods fall below the threshold, leaving the estimate "
                      "resting on a handful of observations.",
    },
    "mean_absolute_deviation": {
        "purpose": "Average absolute deviation. Assumes less about shape than a "
                   "standard deviation.",
        "fails_when": "Nothing structural; it is simply less familiar, so it is "
                      "reported beside the standard deviation rather than instead of it.",
    },
    "gini_dispersion": {
        "purpose": "Expected absolute difference between two independent draws.",
        "fails_when": "Nothing structural. It assumes no distributional shape at all.",
    },
    "semi_variance": {
        "purpose": "Second lower partial moment about an explicit threshold.",
        "fails_when": "The threshold is left implicit. Zero and the mean are "
                      "different questions with different answers.",
    },
    "sharpe": {
        "purpose": "Excess return per unit of volatility.",
        "fails_when": "Returns are skewed or fat-tailed, or the series is short. "
                      "It is also the statistic most inflated by repeated trials, "
                      "which is what the deflated Sharpe ratio corrects.",
    },
    "sortino": {
        "purpose": "Excess return per unit of downside deviation.",
        "fails_when": "Few losing periods exist, making the denominator unstable.",
    },
    "calmar": {
        "purpose": "Compound growth per unit of worst peak-to-trough loss.",
        "fails_when": "The sample is short enough that the worst drawdown has not "
                      "happened yet. It is also path-dependent: an unsorted series "
                      "produces a different, plausible, wrong answer.",
    },
    "ulcer_index": {
        "purpose": "Root mean square of the drawdown path. Depth and duration together.",
        "fails_when": "The series is not in date order — it walks the path as given.",
    },
    "ulcer_performance_index": {
        "purpose": "Excess return per unit of ulcer index.",
        "fails_when": "As for the ulcer index; and the return must be in return units.",
    },
    "max_drawdown": {
        "purpose": "Worst peak-to-trough decline.",
        "fails_when": "The series is not in date order, or the sample is too short "
                      "to have contained the drawdown that matters.",
    },
    "average_drawdown": {
        "purpose": "Mean of the drawdown path, zeros included.",
        "fails_when": "Averaging only the underwater periods would answer a "
                      "different question and read far better; this does not.",
    },
    "drawdown_at_risk_95": {
        "purpose": "The 95th percentile of the drawdown path.",
        "fails_when": "The path is short; a percentile of 60 observations is coarse.",
    },
    "conditional_drawdown_at_risk_95": {
        "purpose": "Mean drawdown beyond the 95th percentile.",
        "fails_when": "Few observations lie beyond the cutoff.",
    },
    "entropic_drawdown_risk_95": {
        "purpose": "Entropic bound on the drawdown at risk.",
        "fails_when": "The optimisation does not converge, in which case nothing "
                      "is reported rather than a fallback.",
    },
    "var_historical_95": {
        "purpose": "The empirical loss quantile.",
        "fails_when": "It says nothing about what lies beyond it, and it is not "
                      "coherent — splitting a position across two books can reduce it.",
    },
    "var_parametric_95": {
        "purpose": "The same quantile under a normal assumption.",
        "fails_when": "Returns are not normal, which is the usual case. Reported "
                      "beside the historical figure so the gap is visible.",
    },
    "cvar_historical_95": {
        "purpose": "Mean loss beyond the historical VaR. Coherent.",
        "fails_when": "The tail holds few observations, so the average is taken "
                      "over a small sample; the count is reported with it.",
    },
    "entropic_var_95": {
        "purpose": "The tightest Chernoff bound on VaR. Coherent, and at or above "
                   "CVaR by construction.",
        "fails_when": "The optimisation does not converge. It is a bound, so it is "
                      "conservative by design and not an estimate of the tail mean.",
    },
    "var_historical_99": {
        "purpose": "The empirical loss quantile at 99%.",
        "fails_when": "Far fewer observations sit beyond a 99% cutoff than a 95% "
                      "one, so it is the noisier of the two and is read beside it.",
    },
    "cvar_historical_99": {
        "purpose": "Mean loss beyond the 99% historical VaR.",
        "fails_when": "The tail it averages over is very small — on 252 sessions "
                      "it is two or three observations.",
    },
    "worst_realization": {
        "purpose": "The single worst observed period.",
        "fails_when": "It is one observation. It describes the sample, not the distribution.",
    },
    "omega": {
        "purpose": "Probability-weighted gains over losses about a threshold.",
        "fails_when": "Nothing falls below the threshold, leaving the ratio "
                      "unbounded — nothing is reported in that case.",
    },
    "beta": {
        "purpose": "Sensitivity to a benchmark, by ordinary least squares.",
        "fails_when": "The benchmark has near-zero variance, or the overlap with "
                      "the portfolio series is short.",
    },
    "tracking_error": {
        "purpose": "Dispersion of the active return against a benchmark.",
        "fails_when": "The two series are aligned on few common dates.",
    },
    "information_ratio": {
        "purpose": "Mean active return per unit of tracking error.",
        "fails_when": "The tracking error is near zero, making the ratio explosive.",
    },
    "capm_alpha": {
        "purpose": "Intercept of a single-factor regression on one benchmark.",
        "fails_when": "It is a single-factor claim. Clearing it says nothing about "
                      "the six-factor alpha reported for research.",
    },
}


def handbook() -> dict[str, Any]:
    """Every measure the engine reports, with its derived and authored fields."""
    entries = []
    for name, (unit, annualisation, inputs) in sorted(METHODOLOGY.items()):
        note = NOTES.get(name, {})
        entries.append(
            {
                "name": name,
                # Derived from the engine. Cannot drift.
                "unit": unit.value,
                "annualisation": annualisation.value,
                "inputs": list(inputs),
                "return_units_required": name in RETURN_ONLY_METRICS,
                "minimum_observations": MIN_OBSERVATIONS,
                # Authored prose, marked as such.
                "purpose": note.get("purpose"),
                "fails_when": note.get("fails_when"),
                "documented": bool(note),
            }
        )
    return {
        "entries": entries,
        "total": len(entries),
        "documented": sum(1 for e in entries if e["documented"]),
        "minimum_observations": MIN_OBSERVATIONS,
        "source": "src/quant/risk/engine.py::METHODOLOGY",
        "note": (
            "Units, annualisation, inputs and applicability are read from the "
            "engine's own methodology table, so they cannot drift from the code "
            "that computes the numbers. Purpose and failure conditions are "
            "authored and are flagged by `documented`."
        ),
    }
