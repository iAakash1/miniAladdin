"""
Cross-sectional screen — which names rank highest today, and do the factors agree?

Answers two questions the product could not previously ask:

1. **Where does this name sit against its peers, right now?** A raw factor
   score of 0.42 means nothing. "83rd percentile of the mega-cap universe
   today" means something, and only a cross-section can produce it.

2. **Do the factors agree?** A name in the 90th percentile on every factor is
   a different proposition from one averaging the 90th while sitting at the
   10th on two of them. The mean is identical; the confidence is not. Nothing
   in this product exposed that, and it is the most useful column here.

## Equal weights, on purpose

The obvious refinement is to weight each factor by its measured IC. It is
rejected: `docs/FACTOR-LAB.md` showed that on this sample **no factor is
statistically significant**, so IC-weighting would be fitting weights to
noise and presenting the result as if it were informed. Equal weights across
whatever factors are available make a weaker claim, and a weaker claim is the
correct one when the evidence is weak.

`agreement` is what carries the real information here, not the composite.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from typing import Optional

import numpy as np
import pandas as pd

#: Below this a percentile is meaningless — with eight names, the third-best
#: is the 62nd percentile purely by arithmetic.
MIN_NAMES = 10

#: A name needs this many factors before a composite means anything.
MIN_FACTORS = 3


@dataclass(frozen=True)
class ScreenRow:
    symbol: str
    composite: float                        # 0-100, mean of factor percentiles
    rank: int
    agreement: float                        # 0-1; 1 = every factor agrees
    factors_used: int
    percentiles: dict[str, float]
    strongest: Optional[str]
    weakest: Optional[str]

    @property
    def conviction(self) -> str:
        """Agreement bucketed, because the number alone invites false precision."""
        if self.agreement >= 0.75:
            return "aligned"
        if self.agreement >= 0.5:
            return "mixed"
        return "conflicted"


def screen(
    panel: pd.DataFrame,
    factors: tuple[str, ...],
    observed_on: Date,
    limit: int = 0,
) -> list[ScreenRow]:
    """Rank every name on one date by the mean of its factor percentiles.

    Percentiles are computed **within the date**, so the output is explicitly
    relative: this is where a name sits against its peers today, not an
    absolute judgement that could be compared across universes.
    """
    day = panel[panel["date"] == observed_on]
    present = [f for f in factors if f in day.columns and day[f].notna().sum() >= MIN_NAMES]
    if day.empty or not present:
        return []

    # Rank within the date. `pct=True` gives 0-1; scaled to 0-100 for display.
    ranked = day[["symbol"] + present].copy()
    for factor in present:
        ranked[factor] = ranked[factor].rank(pct=True) * 100.0

    rows: list[ScreenRow] = []
    for _, record in ranked.iterrows():
        values = {f: record[f] for f in present if pd.notna(record[f])}
        if len(values) < MIN_FACTORS:
            continue
        series = np.fromiter(values.values(), dtype=float)

        # Agreement: 1 minus normalised spread. A name at the 90th on every
        # factor scores 1.0; one split between 10th and 90th scores near 0.
        # Divided by 50 because that is the maximum std of values on 0-100
        # that a two-point split can produce.
        agreement = float(max(0.0, 1.0 - series.std() / 50.0))

        rows.append(ScreenRow(
            symbol=str(record["symbol"]),
            composite=float(series.mean()),
            rank=0,
            agreement=agreement,
            factors_used=len(values),
            percentiles={f: round(v, 1) for f, v in values.items()},
            strongest=max(values, key=values.get),
            weakest=min(values, key=values.get),
        ))

    rows.sort(key=lambda row: -row.composite)
    ranked_rows = [
        ScreenRow(**{**row.__dict__, "rank": position + 1})
        for position, row in enumerate(rows)
    ]
    return ranked_rows[:limit] if limit else ranked_rows


def dispersion(rows: list[ScreenRow]) -> dict[str, float]:
    """How much the universe is actually differentiated today.

    A day where every name sits near the 50th percentile on every factor is a
    day the engine has no opinion, and saying so is more useful than
    presenting a ranking that is noise ordered by luck.
    """
    if not rows:
        return {"composite_spread": 0.0, "mean_agreement": 0.0}
    composites = np.array([row.composite for row in rows])
    return {
        "composite_spread": float(composites.max() - composites.min()),
        "mean_agreement": float(np.mean([row.agreement for row in rows])),
    }
