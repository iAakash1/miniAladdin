"""Descriptive robustness summaries; never selection criteria after the fact."""

from __future__ import annotations

from typing import Iterable

import numpy as np


def distribution(values: Iterable[float]) -> dict[str, float | int | None]:
    array = np.asarray([value for value in values if np.isfinite(value)], dtype=float)
    if not len(array):
        return {"n": 0, "mean": None, "median": None, "std": None, "min": None, "max": None, "p05": None, "p95": None}
    return {
        "n": int(len(array)), "mean": float(array.mean()), "median": float(np.median(array)),
        "std": float(array.std(ddof=1)) if len(array) > 1 else 0.0,
        "min": float(array.min()), "max": float(array.max()),
        "p05": float(np.quantile(array, 0.05)), "p95": float(np.quantile(array, 0.95)),
    }


def overfit_flag(train_ic: float | None, validation_ic: float | None, *, threshold: float = 0.15) -> dict[str, object]:
    gap = None if train_ic is None or validation_ic is None else float(train_ic - validation_ic)
    return {"train_validation_ic_gap": gap, "overfit_warning": bool(gap is not None and gap > threshold), "threshold": threshold}
