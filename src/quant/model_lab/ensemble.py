"""OOF-only diversity and simple rank ensembles."""

from __future__ import annotations

import pandas as pd


KEYS = ["date", "symbol", "outer_fold", "fwd_rank_21"]


def prediction_rank_correlation(predictions: dict[str, pd.DataFrame]) -> pd.DataFrame:
    ranked = []
    for name, frame in predictions.items():
        values = frame[KEYS + ["prediction"]].copy()
        values[name] = values.groupby("date")["prediction"].rank(pct=True)
        ranked.append(values[KEYS + [name]])
    merged = ranked[0]
    for frame in ranked[1:]:
        merged = merged.merge(frame, on=KEYS, how="inner", validate="one_to_one")
    return merged[list(predictions)].corr(method="spearman")


def equal_weight_rank_average(predictions: dict[str, pd.DataFrame]) -> pd.DataFrame:
    if len(predictions) < 2:
        raise ValueError("an ensemble needs at least two independently fitted OOF prediction sets")
    ranked = []
    for name, frame in predictions.items():
        values = frame[KEYS + ["prediction"]].copy()
        values[name] = values.groupby("date")["prediction"].rank(pct=True)
        ranked.append(values[KEYS + [name]])
    merged = ranked[0]
    for frame in ranked[1:]:
        merged = merged.merge(frame, on=KEYS, how="inner", validate="one_to_one")
    merged["prediction"] = merged[list(predictions)].mean(axis=1)
    return merged[KEYS + ["prediction"]]
