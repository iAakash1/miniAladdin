"""
How well does a prediction order a cross-section? — metrics that need no portfolio.

Rank IC says the *average* ordering is informative. A ranking objective makes a
sharper claim: that it orders the names that matter — the ends of the list — better
than a point-regression loss does. So this module measures the ends directly, and it
measures whether a better ordering was bought by re-ordering everything every week.

All quantities are functions of predictions and the realised rank label
(`fwd_rank_21`), evaluated one date at a time and then averaged; none reads a
portfolio, a cost or a return.

* `ndcg_at_k` — NDCG of the top `k` by prediction against quintile relevance
  (linear gains, log2 discount). `long` uses the relevance itself; `short` reverses
  both the relevance and the score, so the *bottom* of the list is scored the same way.
* top/bottom realised rank — the mean realised label of the `k` names predicted best
  (worst). The spread between them is the ordering quality a long/short quintile
  book can actually capture.
* stability — the rank correlation of predictions between consecutive dates over the
  names present in both, and the share of the top (bottom) group still in it a date later.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src.quant.models.ranking import relevance_from_rank

RELEVANCE_LEVELS = 5


def ndcg_at_k(scores: np.ndarray, relevance: np.ndarray, k: int) -> float:
    """NDCG@k of ordering `relevance` by descending `scores` (linear gains). NaN if undefined."""
    if len(scores) == 0:
        return float("nan")
    k = min(k, len(scores))
    order = np.argsort(-scores, kind="stable")[:k]
    discount = 1.0 / np.log2(np.arange(k) + 2.0)
    dcg = float((relevance[order].astype(float) * discount).sum())
    ideal = np.sort(relevance)[::-1][:k].astype(float)
    idcg = float((ideal * discount).sum())
    return dcg / idcg if idcg > 0 else float("nan")


def per_date_ordering(
    predictions: pd.DataFrame, *, label: str = "fwd_rank_21", k: int = 50,
    prediction_column: str = "prediction",
) -> pd.DataFrame:
    """One row per date: IC, NDCG@k for both ends, and the realised rank of each end."""
    rows = []
    for day, group in predictions.groupby("date", sort=True):
        score = group[prediction_column].to_numpy(dtype=float)
        truth = group[label].to_numpy(dtype=float)
        if len(group) < 2 * k or np.ptp(score) == 0:
            continue
        rel = relevance_from_rank(truth, RELEVANCE_LEVELS)
        order = np.argsort(-score, kind="stable")
        rows.append({
            "date": day,
            "ic": spearmanr(score, truth)[0],
            "ndcg_long": ndcg_at_k(score, rel, k),
            "ndcg_short": ndcg_at_k(-score, (RELEVANCE_LEVELS - 1) - rel, k),
            "top_realised_rank": float(truth[order[:k]].mean()),
            "bottom_realised_rank": float(truth[order[-k:]].mean()),
        })
    out = pd.DataFrame(rows).set_index("date")
    out["realised_rank_spread"] = out["top_realised_rank"] - out["bottom_realised_rank"]
    return out


def stability(
    predictions: pd.DataFrame, *, group_fraction: float = 0.2, prediction_column: str = "prediction",
) -> dict[str, Any]:
    """Week-to-week stability of the ordering (consecutive dates, names present in both)."""
    dates = sorted(predictions["date"].unique())
    by_date = {d: g.set_index("symbol")[prediction_column] for d, g in predictions.groupby("date")}
    rank_corr, top_keep, bottom_keep = [], [], []
    for previous, current in zip(dates[:-1], dates[1:]):
        p, c = by_date[previous], by_date[current]
        common = p.index.intersection(c.index)
        if len(common) < 20:
            continue
        rank_corr.append(float(spearmanr(p.loc[common], c.loc[common])[0]))
        n = max(int(round(group_fraction * len(common))), 1)
        pr, cr = p.loc[common].rank(method="first"), c.loc[common].rank(method="first")
        top_p, top_c = set(pr.index[pr > len(common) - n]), set(cr.index[cr > len(common) - n])
        bot_p, bot_c = set(pr.index[pr <= n]), set(cr.index[cr <= n])
        top_keep.append(len(top_p & top_c) / n)
        bottom_keep.append(len(bot_p & bot_c) / n)
    return {
        "mean_rank_correlation_between_consecutive_dates": float(np.mean(rank_corr)),
        "top_group_retention": float(np.mean(top_keep)),
        "bottom_group_retention": float(np.mean(bottom_keep)),
        "dates_compared": len(rank_corr),
    }
