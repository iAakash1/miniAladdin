"""Ordering metrics and stable hashes for Model Lab trials."""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
import pandas as pd

from src.quant.validation.metrics import ic_summary, per_date_ic


def prediction_hash(frame: pd.DataFrame) -> str:
    columns = [c for c in ("date", "symbol", "outer_fold", "prediction", "fwd_rank_21") if c in frame]
    ordered = frame[columns].copy().sort_values([c for c in ("date", "symbol") if c in columns], kind="mergesort")
    if "date" in ordered:
        ordered["date"] = pd.to_datetime(ordered["date"]).dt.strftime("%Y-%m-%d")
    return hashlib.sha256(pd.util.hash_pandas_object(ordered, index=False).to_numpy().tobytes()).hexdigest()


def ordering_metrics(frame: pd.DataFrame, *, target: str = "fwd_rank_21") -> dict[str, Any]:
    series = per_date_ic(frame, prediction_column="prediction", target_column=target)
    report = ic_summary(series, horizon_sessions=21, step_sessions=5)
    finite = series[np.isfinite(series)]
    return {
        "mean_rank_ic": report.get("mean_ic"),
        "hac_t_stat": report.get("t_stat"),
        "icir": report.get("ic_ir"),
        "positive_date_share": float((finite > 0).mean()) if len(finite) else None,
        "dates": int(len(finite)),
    }
