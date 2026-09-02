"""
Market regime — a state label, tested rather than asserted.

## The question this exists to answer

"Does this model work in the regime we are currently in?" A model with a mean
IC of 0.03 across fifteen years that earned all of it in one volatility spike
is not a 0.03-IC model; it is a volatility-spike model with a misleading
average. Splitting performance by regime is the cheapest way to tell those
apart, and the answer is frequently uncomfortable.

## Two labellers, on purpose

**Rule-based** (`classify_rules`). Volatility percentile crossed with trailing
market return, giving four states plus a stress state. Transparent, stable, and
its boundaries are stated numbers a reader can disagree with.

**Unsupervised** (`classify_clusters`). K-means over standardised regime
features, fitted **only on data before each labelling date**, so a 2015 label
never depends on 2020's cluster centres. Finds structure the rules do not
impose.

They are both produced and both reported. When they agree, the regime call is
robust; when they disagree, that disagreement is the honest output — and
picking whichever one made a model look better would be regime selection after
seeing results, which is the exact failure mode the brief names.

## Point-in-time labelling

`classify_rules` consumes features that are already backward-looking
(`market_vol_percentile` is a trailing rank, `market_mom_252` a trailing
return). `classify_clusters` refits on an expanding window and labels only the
next block. Neither ever sees a future observation, and
`tests/quant/test_leakage.py` perturbs the future to confirm it.

## The naming caveat

"High-volatility bear" is a *description of measured conditions*, not a claim
about cause or about what happens next. The states are named for legibility.
Nothing here forecasts a regime, and nothing should be read as doing so.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

import numpy as np
import pandas as pd

logger = logging.getLogger("omnisignal.quant.regime")

#: Volatility percentile above which conditions are called high-volatility.
HIGH_VOL_PERCENTILE = 0.70
LOW_VOL_PERCENTILE = 0.30

#: Drawdown depth that overrides the four-state grid with an explicit stress
#: label. A 20% market drawdown is a different environment from a merely
#: volatile one, and folding it into "high-volatility bear" loses that.
STRESS_DRAWDOWN = 0.15

RULE_STATES: tuple[str, ...] = (
    "low_vol_bull", "high_vol_bull", "low_vol_bear", "high_vol_bear", "stress", "unknown",
)


@dataclass
class RegimeSeries:
    """Dated regime labels with the evidence that produced them."""

    frame: pd.DataFrame
    method: str
    states: list[str]
    parameters: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def label_for(self, day) -> Optional[str]:
        """The label in force on a date — latest at or before, never after."""
        subset = self.frame[self.frame["date"] <= day]
        return None if subset.empty else str(subset.iloc[-1]["regime"])

    def distribution(self) -> dict[str, int]:
        return self.frame["regime"].value_counts().to_dict()

    def as_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "states": list(self.states),
            "observations": len(self.frame),
            "distribution": self.distribution(),
            "parameters": dict(self.parameters),
            "notes": list(self.notes),
            "start": str(self.frame["date"].min()) if len(self.frame) else None,
            "end": str(self.frame["date"].max()) if len(self.frame) else None,
        }


def classify_rules(
    macro: pd.DataFrame,
    *,
    high_vol: float = HIGH_VOL_PERCENTILE,
    low_vol: float = LOW_VOL_PERCENTILE,
    stress_drawdown: float = STRESS_DRAWDOWN,
) -> RegimeSeries:
    """Label each date from trailing volatility percentile and trailing return.

    Every input is already a trailing statistic, so the label for a date uses
    only that date's information. The boundaries are constants stated above
    rather than fitted, which means they cannot have been chosen to make a
    result look better.
    """
    required = {"date", "market_vol_percentile", "market_mom_252", "market_drawdown"}
    missing = required - set(macro.columns)
    if missing:
        raise ValueError(f"regime classification needs columns {sorted(missing)}")

    frame = macro.sort_values("date").reset_index(drop=True)
    percentile = pd.to_numeric(frame["market_vol_percentile"], errors="coerce")
    momentum = pd.to_numeric(frame["market_mom_252"], errors="coerce")
    drawdown = pd.to_numeric(frame["market_drawdown"], errors="coerce")

    labels: list[str] = []
    for pct, mom, dd in zip(percentile, momentum, drawdown):
        if not np.isfinite(pct) or not np.isfinite(mom):
            # "unknown" rather than a default state. A date before the trailing
            # windows fill is not low-volatility; it is unmeasured, and
            # labelling it anything else would put unmeasured dates into a
            # regime bucket and shift that bucket's statistics.
            labels.append("unknown")
            continue
        if np.isfinite(dd) and dd >= stress_drawdown:
            labels.append("stress")
            continue
        volatile = pct >= high_vol
        rising = mom > 0
        if volatile:
            labels.append("high_vol_bull" if rising else "high_vol_bear")
        elif pct <= low_vol:
            labels.append("low_vol_bull" if rising else "low_vol_bear")
        else:
            labels.append("low_vol_bull" if rising else "low_vol_bear")

    out = pd.DataFrame({"date": frame["date"], "regime": labels})
    return RegimeSeries(
        frame=out,
        method="rule_based",
        states=list(RULE_STATES),
        parameters={
            "high_vol_percentile": high_vol,
            "low_vol_percentile": low_vol,
            "stress_drawdown": stress_drawdown,
        },
        notes=[
            "Boundaries are fixed constants, not fitted — they cannot have been "
            "tuned to a result.",
            "State names describe measured conditions. They are not forecasts and "
            "carry no claim about what follows.",
            "Dates before the trailing windows fill are labelled 'unknown' rather "
            "than assigned a default state.",
        ],
    )


def classify_clusters(
    macro: pd.DataFrame,
    *,
    features: Sequence[str] = ("market_vol_21", "market_mom_252", "market_drawdown", "rates_slope"),
    clusters: int = 4,
    min_train: int = 504,
    refit_every: int = 63,
    seed: int = 0,
) -> RegimeSeries:
    """K-means regimes, refitted on an expanding window and applied forward.

    The point-in-time construction is the whole design. Fitting k-means once
    over the full history and labelling every date would let 2020's centroids
    define what "high volatility" meant in 2014 — a leak that is invisible
    because the label looks reasonable either way, and which makes any
    regime-conditional performance statistic optimistic.

    So: fit on `[0, t)`, label `[t, t + refit_every)`, advance. Dates before
    `min_train` are `unknown`.
    """
    try:
        from sklearn.cluster import KMeans
    except ImportError as error:  # pragma: no cover
        raise RuntimeError(
            f"cluster regimes need scikit-learn ({error}); install requirements-quant.txt. "
            "The capability reports unavailable rather than falling back to the rule-based "
            "labeller, which would be a different method reported under this one's name."
        ) from error

    available = [name for name in features if name in macro.columns]
    if len(available) < 2:
        raise ValueError(f"cluster regimes need at least 2 of {list(features)}")

    frame = macro.sort_values("date").reset_index(drop=True)
    matrix = frame[available].apply(pd.to_numeric, errors="coerce")
    complete = matrix.notna().all(axis=1).to_numpy()

    labels = np.full(len(frame), -1, dtype=int)
    position = min_train
    while position < len(frame):
        train_mask = complete[:position]
        if train_mask.sum() < min_train // 2:
            position += refit_every
            continue
        train = matrix.iloc[:position][train_mask]
        mean, std = train.mean(), train.std(ddof=1).replace(0.0, 1.0)
        model = KMeans(n_clusters=clusters, random_state=seed, n_init=10)
        model.fit(((train - mean) / std).to_numpy())

        end = min(position + refit_every, len(frame))
        block = matrix.iloc[position:end]
        block_mask = complete[position:end]
        if block_mask.any():
            scaled = ((block[block_mask] - mean) / std).to_numpy()
            labels[position:end][block_mask] = model.predict(scaled)
        position = end

    named = [f"cluster_{value}" if value >= 0 else "unknown" for value in labels]
    out = pd.DataFrame({"date": frame["date"], "regime": named})
    return RegimeSeries(
        frame=out,
        method="kmeans_expanding",
        states=sorted(set(named)),
        parameters={
            "features": available, "clusters": clusters, "min_train": min_train,
            "refit_every": refit_every, "seed": seed,
        },
        notes=[
            f"Refitted every {refit_every} sessions on an expanding window; each block "
            "is labelled by centroids fitted strictly before it.",
            "Cluster identities are not stable across refits — cluster_2 in 2015 is not "
            "necessarily cluster_2 in 2022. Compare cluster CENTROIDS, not labels, "
            "across periods.",
            "Standardisation statistics come from the training window only.",
        ],
    )


def performance_by_regime(
    predictions: pd.DataFrame,
    regimes: RegimeSeries,
    *,
    label: str,
    horizon_sessions: int,
    step_sessions: int,
    prediction_column: str = "prediction",
    date_column: str = "date",
    min_observations: int = 200,
) -> list[dict[str, Any]]:
    """Break out-of-sample performance down by regime.

    A regime holding fewer than `min_observations` rows is reported with its
    count and no metrics. A rank IC computed on 40 rows in one rare regime has a
    standard error wide enough to cover any conclusion, and printing it invites
    exactly the story it cannot support.

    `horizon_sessions` and `step_sessions` carry no defaults on purpose. They
    set the Newey-West lag count, and a wrong one is invisible: the t-statistic
    stays plausible and only its size is wrong. These were hardcoded to 21 and
    5, which under-corrects every label that looks further than 21 sessions —
    `fwd_ret_63` among them.
    """
    from src.quant.validation.metrics import ic_summary, per_date_ic, regression_metrics

    frame = predictions.copy()
    lookup = regimes.frame.set_index("date")["regime"].to_dict()
    frame["regime"] = frame[date_column].map(lookup).fillna("unknown")

    rows: list[dict[str, Any]] = []
    for regime, group in frame.groupby("regime", sort=True):
        row: dict[str, Any] = {
            "regime": regime,
            "observations": len(group),
            "dates": int(group[date_column].nunique()),
            "share": round(len(group) / len(frame), 4),
        }
        if len(group) < min_observations:
            row["note"] = (
                f"fewer than {min_observations} observations — no metric reported, "
                "because one computed here would not distinguish signal from sampling"
            )
            rows.append(row)
            continue
        metrics = regression_metrics(group[label], group[prediction_column], scale_free=True)
        ic = ic_summary(
            per_date_ic(
                group, prediction_column=prediction_column, target_column=label,
                date_column=date_column,
            ),
            horizon_sessions=horizon_sessions,
            step_sessions=step_sessions,
        )
        row.update(
            {
                "mean_ic": ic.get("mean_ic"),
                "ic_t_stat": ic.get("t_stat"),
                "ic_hit_rate": ic.get("hit_rate"),
                "directional_edge": metrics.values.get("directional_edge"),
                "spearman": metrics.values.get("spearman"),
                "mean_realised_return": float(pd.to_numeric(group[label], errors="coerce").mean()),
            }
        )
        rows.append(row)
    return rows


def compare_labellers(rules: RegimeSeries, clusters: RegimeSeries) -> dict[str, Any]:
    """How often the two methods agree, reported without choosing between them.

    Agreement is measured as mutual information rather than raw match rate,
    because the cluster labels are arbitrary integers — `cluster_2` and
    `high_vol_bear` can describe the same state and never string-match.
    """
    merged = rules.frame.merge(clusters.frame, on="date", suffixes=("_rule", "_cluster"))
    merged = merged[(merged["regime_rule"] != "unknown") & (merged["regime_cluster"] != "unknown")]
    if merged.empty:
        return {"overlapping_dates": 0}

    table = pd.crosstab(merged["regime_rule"], merged["regime_cluster"])
    joint = table.to_numpy(dtype=float) / table.to_numpy().sum()
    row_marginal = joint.sum(axis=1, keepdims=True)
    column_marginal = joint.sum(axis=0, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        terms = joint * np.log(joint / (row_marginal * column_marginal))
    mutual_information = float(np.nansum(terms))
    entropy = float(-np.nansum(row_marginal * np.log(row_marginal)))

    return {
        "overlapping_dates": int(len(merged)),
        "mutual_information": round(mutual_information, 4),
        "normalised_mutual_information": (
            round(mutual_information / entropy, 4) if entropy > 0 else None
        ),
        "crosstab": table.to_dict(),
        "note": (
            "Cluster labels are arbitrary integers, so agreement is measured by mutual "
            "information rather than by matching names. Both labellers are reported; "
            "choosing the one that flatters a model would be regime selection after "
            "seeing results."
        ),
    }
