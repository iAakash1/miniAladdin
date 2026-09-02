"""
Derived series for the quant UI — computed in Python, never in TypeScript.

## Why this module exists

The study artifact records *summary* statistics: a pooled IC, a fold count, a
Sharpe. It does not record the per-fold IC series or the equity curve, because
those are cheap to derive and expensive to store for seventeen models.

They are derived HERE rather than in the frontend for one reason: every number
on the quant page has to come from the same code path that produced the
conclusions. A rank IC recomputed in TypeScript would be a second implementation
of a scientific calculation, and the first time the two disagreed the UI would
be quietly wrong in a way no test covers.

## What is derived

* **Per-fold rank IC** — Spearman between prediction and realised forward rank,
  computed per date and averaged within a fold. Matches `ic_summary`.
* **Equity curve** — the quintile long/short book the backtest engine builds,
  gross and net, replayed period by period so the drawdown is visible rather
  than reported as a single number.

Results are cached by (artifact mtime, model) because a study artifact is
immutable and re-reading a 10 MB parquet per request would spend I/O to produce
an identical answer.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from src.quant.validation.metrics import bootstrap_interval
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("omnisignal.services.quant_series")

DEFAULT_ROOT = Path("experiments")

#: Label horizon and rebalance cadence, from the experiment definitions. Their
#: ratio is the dependence length that the bootstrap must respect.
_LABEL_HORIZON_SESSIONS = 21
_REBALANCE_SESSIONS = 5
_OVERLAP_BLOCK = max(1, _LABEL_HORIZON_SESSIONS // _REBALANCE_SESSIONS)

#: A cross-section smaller than this cannot support a rank correlation.
MIN_NAMES_PER_DATE = 10

#: Quintile book, matching `BacktestConfig` defaults.
QUANTILES = 5

_cache: dict[tuple[str, str], Any] = {}
_lock = threading.Lock()


def _predictions(root: Path, experiment_id: str, target: str) -> Optional[pd.DataFrame]:
    path = root / experiment_id / f"predictions_{target}.parquet"
    if not path.exists():
        return None
    key = (str(path), str(path.stat().st_mtime))
    with _lock:
        hit = _cache.get(key)
    if hit is not None:
        return hit
    frame = pd.read_parquet(path)
    with _lock:
        _cache.clear()          # one artifact at a time; this is a UI cache
        _cache[key] = frame
    return frame


def _rank_ic_by_date(block: pd.DataFrame, target: str) -> pd.Series:
    """Spearman per date. Dates with too few names return NaN, never 0."""
    def one(group: pd.DataFrame) -> float:
        usable = group[[target, "prediction"]].dropna()
        if len(usable) < MIN_NAMES_PER_DATE:
            return np.nan
        if usable["prediction"].nunique() < 2:
            return np.nan          # a constant predictor has no ranking
        return usable[target].corr(usable["prediction"], method="spearman")

    return block.groupby("date", sort=True).apply(one, include_groups=False)


def fold_series(
    experiment_id: str,
    model_id: str,
    *,
    target: str = "fwd_rank_21",
    root: Path | str = DEFAULT_ROOT,
) -> dict[str, Any]:
    """Per-fold IC, and the per-date IC series inside each fold."""
    frame = _predictions(Path(root), experiment_id, target)
    if frame is None:
        return {"status": "unavailable", "detail": "no predictions artifact"}

    block = frame[frame["model"] == model_id]
    if block.empty:
        return {"status": "unavailable", "detail": f"no predictions for {model_id}"}

    folds: list[dict[str, Any]] = []
    for index, chunk in block.groupby("fold", sort=True):
        ic = _rank_ic_by_date(chunk, target).dropna()
        if ic.empty:
            folds.append({"fold": int(index), "mean_ic": None, "dates": 0})
            continue
        folds.append({
            "fold": int(index),
            "mean_ic": float(ic.mean()),
            "median_ic": float(ic.median()),
            "std_ic": float(ic.std()),
            "dates": int(len(ic)),
            "positive_rate": float((ic > 0).mean()),
            "start": str(chunk["date"].min()),
            "end": str(chunk["date"].max()),
            "observations": int(len(chunk)),
        })

    per_date = _rank_ic_by_date(block, target).dropna()

    # A confidence interval on the pooled IC.
    #
    # The surface reported a point estimate, which invites reading a mean of
    # 0.03 as though its precision were known. The block bootstrap is what makes
    # the interval honest here: labels span 21 sessions and rebalances are 5
    # apart, so consecutive observations share roughly four fifths of their
    # outcome. An i.i.d. bootstrap on dependent draws produces an interval far
    # too narrow — understating uncertainty in exactly the direction that
    # flatters a result.
    interval = bootstrap_interval(
        per_date.to_numpy(), block=_OVERLAP_BLOCK, samples=2000, seed=0,
    )

    return {
        "status": "ok",
        "model_id": model_id,
        "target": target,
        "folds": folds,
        "pooled_ic": {
            **interval,
            "method": (
                f"moving-block bootstrap, block={_OVERLAP_BLOCK} periods, "
                "2000 resamples, 95% interval"
            ),
            "why_blocked": (
                f"labels span {_LABEL_HORIZON_SESSIONS} sessions against a "
                f"{_REBALANCE_SESSIONS}-session rebalance, so consecutive "
                "observations overlap and are not independent"
            ),
            "observations": int(len(per_date)),
        },
        "ic_by_date": [
            {"date": str(d), "ic": float(v)} for d, v in per_date.items()
        ],
        "note": (
            "Rank IC is Spearman between the prediction and the realised forward "
            f"rank, computed per date over at least {MIN_NAMES_PER_DATE} names and "
            "averaged. Dates with a thinner cross-section are excluded, not zeroed."
        ),
    }


def spread_curve(
    experiment_id: str,
    model_id: str,
    *,
    target: str = "fwd_rank_21",
    root: Path | str = DEFAULT_ROOT,
    half_spread_bps: float = 10.0,
    commission_bps: float = 1.0,
    execution_lag_periods: int = 1,
) -> dict[str, Any]:
    """Cumulative rank spread of the quintile book. **Not** an equity curve.

    ## Why this is not called an equity curve, and does not compound

    `fwd_rank_21` is a cross-sectional rank in [-1, 1], not a return. A long/short
    book over ranks earns a *rank spread* per period, and the first version of
    this function compounded that spread as though it were a percentage return.
    It produced **+6,553%** — a number that would sit on a page headlined "no
    evidence of edge" and be believed.

    So the accumulation is ADDITIVE and the units are rank points. The curve
    answers "did the ranking work consistently, or in one lucky stretch?", which
    is the question a single Sharpe cannot answer. It is deliberately incapable
    of answering "how much money would this have made" — the artifact's costed
    backtest answers that, and its answer is a negative Sharpe.

    Costs are the linear part only (commission + half-spread on turnover),
    converted to rank points at the same scale. The engine additionally models
    square-root impact, so this understates cost.
    """
    frame = _predictions(Path(root), experiment_id, target)
    if frame is None:
        return {"status": "unavailable", "detail": "no predictions artifact"}

    block = frame[frame["model"] == model_id].copy()
    if block.empty:
        return {"status": "unavailable", "detail": f"no predictions for {model_id}"}

    block = block.dropna(subset=["prediction", target])
    dates = sorted(block["date"].unique())
    if len(dates) < 3:
        return {"status": "unavailable", "detail": "too few rebalance dates"}

    prior: dict[str, float] = {}
    rows: list[dict[str, Any]] = []
    gross_cumulative = 0.0
    net_cumulative = 0.0

    # The lag: weights formed on date i are held over the outcome realised at
    # date i + lag. Skipping this is the single most flattering error available.
    for position in range(len(dates) - execution_lag_periods):
        formed = block[block["date"] == dates[position]]
        realised_on = dates[position + execution_lag_periods]
        realised = block[block["date"] == realised_on]
        if len(formed) < QUANTILES * 2 or realised.empty:
            continue

        ranked = formed.sort_values("prediction")
        bucket = len(ranked) // QUANTILES
        if bucket < 1:
            continue
        shorts = ranked.head(bucket)["symbol"].tolist()
        longs = ranked.tail(bucket)["symbol"].tolist()

        weights = {s: 0.5 / len(longs) for s in longs}
        weights.update({s: -0.5 / len(shorts) for s in shorts})

        outcome = realised.set_index("symbol")[target].to_dict()
        gross = sum(w * outcome.get(s, 0.0) for s, w in weights.items())

        turnover = sum(
            abs(weights.get(s, 0.0) - prior.get(s, 0.0))
            for s in set(weights) | set(prior)
        )
        cost = turnover * (half_spread_bps + commission_bps) / 10_000.0
        net = gross - cost

        gross_cumulative += gross
        net_cumulative += net
        prior = weights

        rows.append({
            "date": str(realised_on),
            "gross_period": gross,
            "net_period": net,
            "turnover": turnover,
            "cost": cost,
            "gross_cumulative": gross_cumulative,
            "net_cumulative": net_cumulative,
            "names": len(weights),
        })

    if not rows:
        return {"status": "unavailable", "detail": "no rebalance produced a book"}

    net_path = np.array([r["net_cumulative"] for r in rows])
    gross_path = np.array([r["gross_cumulative"] for r in rows])
    # Additive series, so drawdown is a difference from the running peak in rank
    # points — not a percentage. Dividing would reintroduce the units error.
    net_dd = net_path - np.maximum.accumulate(net_path)
    gross_dd = gross_path - np.maximum.accumulate(gross_path)
    for row, nd, gd in zip(rows, net_dd, gross_dd):
        row["net_drawdown"] = float(nd)
        row["gross_drawdown"] = float(gd)

    return {
        "status": "ok",
        "model_id": model_id,
        "target": target,
        "periods": rows,
        "summary": {
            "periods": len(rows),
            "gross_cumulative": float(gross_path[-1]),
            "net_cumulative": float(net_path[-1]),
            "net_max_drawdown_rank_points": float(net_dd.min()),
            "gross_max_drawdown_rank_points": float(gross_dd.min()),
            "mean_turnover": float(np.mean([r["turnover"] for r in rows])),
            "total_cost": float(sum(r["cost"] for r in rows)),
        },
        "units": "rank points (additive)",
        "assumptions": {
            "quantiles": QUANTILES,
            "execution_lag_periods": execution_lag_periods,
            "half_spread_bps": half_spread_bps,
            "commission_bps": commission_bps,
            "market_impact": "NOT modelled here (the engine does); this understates cost",
            "not_a_return_series": (
                f"{target} is a cross-sectional rank in [-1, 1]. This curve accumulates "
                "rank spread ADDITIVELY and is not a P&L. Every Sharpe, return and cost "
                "figure quoted as evidence comes from the artifact's costed backtest."
            ),
        },
    }
