"""
Factor stability — did this work recently, or did it stop working?

A mean IC over two and a half years is one number covering a hundred and
thirty observations. It cannot distinguish a factor that worked steadily from
one that worked brilliantly in 2024 and has been dead since, and those are
completely different propositions for anyone deciding whether to use it now.

Three views, cheapest to most demanding:

**Rolling IC** — mean IC over a trailing window, so decay is visible as a
shape rather than inferred from a summary.

**Half-sample split** — mean IC in the first half against the second. The
simplest honest check for decay, and the one most likely to embarrass a
factor that was fitted to its own history.

**Best and worst stretches** — the strongest and weakest contiguous windows.
A factor whose entire edge comes from one quarter is not a factor, it is an
anecdote, and `concentration` measures exactly that.

No claim here is a forecast. Every statistic is descriptive: this is what the
factor did, split by time, with no assertion that any of it persists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

#: Enough observations for a trailing mean to mean anything. At weekly
#: sampling this is roughly six months.
DEFAULT_WINDOW = 26

#: Below this, splitting the sample leaves halves too small to compare.
MIN_FOR_SPLIT = 24


@dataclass(frozen=True)
class Stability:
    """How a factor's information coefficient behaved over time."""

    factor: str
    window: int
    rolling: list[dict[str, object]]
    first_half_ic: Optional[float]
    second_half_ic: Optional[float]
    best_window: Optional[dict[str, object]]
    worst_window: Optional[dict[str, object]]
    concentration: float          # share of total IC from the best window
    sign_flips: int               # times the rolling mean crossed zero

    @property
    def decayed(self) -> bool:
        """Positive in the first half, non-positive in the second."""
        if self.first_half_ic is None or self.second_half_ic is None:
            return False
        return self.first_half_ic > 0.02 and self.second_half_ic <= 0.0

    @property
    def assessment(self) -> str:
        if self.first_half_ic is None:
            return "too few observations to judge stability"
        first, second = self.first_half_ic, self.second_half_ic or 0.0
        if self.decayed:
            return (
                f"worked earlier and stopped — IC {first:+.4f} in the first half, "
                f"{second:+.4f} in the second"
            )
        if self.concentration > 0.6:
            return (
                f"edge is concentrated in one stretch ({self.concentration:.0%} of "
                f"total IC), which is an anecdote more than a factor"
            )
        if abs(first - second) < 0.02:
            return (
                f"stable across the sample — IC {first:+.4f} then {second:+.4f}"
            )
        direction = "improved" if second > first else "weakened"
        return f"{direction} over the sample — IC {first:+.4f} then {second:+.4f}"


def _window_stats(values: np.ndarray, dates: list[str], window: int):
    best = worst = None
    for start in range(0, len(values) - window + 1):
        mean = float(values[start:start + window].mean())
        record = {"start": dates[start], "end": dates[start + window - 1],
                  "mean_ic": round(mean, 4)}
        if best is None or mean > best["mean_ic"]:
            best = record
        if worst is None or mean < worst["mean_ic"]:
            worst = record
    return best, worst


def analyse(
    factor: str,
    ic_series: list[tuple[str, float]],
    window: int = DEFAULT_WINDOW,
) -> Stability:
    """Describe how `factor`'s IC behaved over time. Never raises."""
    dates = [day for day, _ in ic_series]
    values = np.array([value for _, value in ic_series], dtype=float)
    count = len(values)
    effective = min(window, max(2, count // 3))

    rolling: list[dict[str, object]] = []
    if count >= effective:
        for end in range(effective, count + 1):
            rolling.append({
                "date": dates[end - 1],
                "ic": round(float(values[end - effective:end].mean()), 4),
            })

    first_half = second_half = None
    if count >= MIN_FOR_SPLIT:
        midpoint = count // 2
        first_half = float(values[:midpoint].mean())
        second_half = float(values[midpoint:].mean())

    best, worst = (_window_stats(values, dates, effective)
                   if count >= effective else (None, None))

    total = float(np.abs(values).sum())
    concentration = 0.0
    if best is not None and total > 0:
        # Share of the sample's total absolute IC contributed by the best
        # window. High means the edge lives in one stretch.
        concentration = min(1.0, abs(best["mean_ic"]) * effective / total)

    signs = np.sign([row["ic"] for row in rolling]) if rolling else np.array([])
    flips = int(np.sum(signs[1:] != signs[:-1])) if len(signs) > 1 else 0

    return Stability(
        factor=factor,
        window=effective,
        rolling=rolling,
        first_half_ic=first_half,
        second_half_ic=second_half,
        best_window=best,
        worst_window=worst,
        concentration=concentration,
        sign_flips=flips,
    )
