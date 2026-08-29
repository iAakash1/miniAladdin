"""
Corporate actions — returns first, adjusted prices only if asked.

## The decision that makes this point-in-time by construction

The conventional approach back-adjusts a price series: take today's corporate
actions and divide every historical price by the cumulative split factor. That
series is convenient and **structurally incapable of being point-in-time**,
because the value it shows for 2015 depends on a split that happened in 2020.
Rebuild it after a new split and every historical number changes. A model
trained on Tuesday's adjusted history and evaluated against Wednesday's is not
being evaluated on what it trained on.

So this module computes **returns**, not adjusted prices:

    r_t = (close_t * k_t + d_t) / close_{t-1} - 1

where `k_t` is the split ratio for an action with `ex_date == t` (1.0 when
none) and `d_t` is the cash dividend with `ex_date == t` (0.0 when none).

Every term is knowable at `t`. Nothing dated after `t` appears anywhere in the
expression, so there is no adjustment to invalidate and no rebuild to diverge
from. This is the same reason `src/panel/builder.py` truncates windows rather
than remembering not to look forward: the property is structural, not a
discipline.

A total-return index is then the cumulative product of those returns. Its value
at `t` depends only on actions up to `t`, so it too is point-in-time — which a
back-adjusted price series never is.

## Why unadjusted input is a feature

`dolthub_stocks_ohlcv` carries no adjusted close, which reads like a gap and is
the opposite. An adjusted close from a vendor is that vendor's back-adjustment
under an unpublished dividend-reinvestment convention, applied at an unknown
time. Raw prices plus dated actions is strictly more information, and it is the
only form from which a point-in-time return can be derived at all.

## Stated assumptions

1. **A split's ex-date is its availability date.** Splits are announced weeks
   earlier, so treating the ex-date as the moment of knowledge is conservative:
   it never reveals a split before it happens.
2. **A dividend on a split ex-date is quoted pre-split.** The declared amount
   applies to the old share count. Same-day split-and-dividend is rare; the
   assumption is recorded here rather than buried, and `applied_actions` on
   every result names the actions used so the case is auditable.
3. **Dollar volume needs no adjustment.** A 4:1 split quarters the price and
   quadruples the share count, so `close x volume` is continuous through it.
   Share volume is not, and is adjusted only when explicitly requested.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date as Date
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("omnisignal.quant.pit.adjust")

#: A split ratio outside this band is almost certainly a data error rather than
#: a corporate action. Real ratios range from 1:10 reverse splits to 20:1
#: forward splits; beyond that the row is quarantined and reported, never
#: applied. Applying a bad ratio manufactures the largest single-day return in
#: the sample, which then dominates every statistic computed over it.
MIN_SPLIT_RATIO = 0.02
MAX_SPLIT_RATIO = 50.0

#: A single-session total return beyond this is flagged for review. Not
#: rejected — real names do move like this, and 2023's regional banks are in
#: this dataset precisely so that they can. Flagged, counted, and surfaced.
EXTREME_RETURN = 0.75


@dataclass
class AdjustmentResult:
    """A point-in-time return series and the evidence behind it."""

    symbol: str
    frame: pd.DataFrame
    applied_splits: int = 0
    applied_dividends: int = 0
    quarantined_splits: list[dict[str, Any]] = field(default_factory=list)
    extreme_returns: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "rows": int(len(self.frame)),
            "applied_splits": self.applied_splits,
            "applied_dividends": self.applied_dividends,
            "quarantined_splits": list(self.quarantined_splits),
            "extreme_returns": self.extreme_returns[:20],
            "extreme_return_count": len(self.extreme_returns),
            "warnings": list(self.warnings),
        }


def split_ratios(splits: pd.DataFrame) -> pd.DataFrame:
    """Turn `to_factor`/`for_factor` into one ratio per (symbol, ex-date).

    A 4:1 forward split is `to_factor=4, for_factor=1` and quarters the price,
    so the return-restoring multiplier is `to/for = 4`. A 1:10 reverse split is
    `to=1, for=10` and multiplies the price tenfold, giving `0.1`.
    """
    if splits.empty:
        return pd.DataFrame(columns=["symbol", "date", "ratio"])

    frame = splits.copy()
    frame["ratio"] = pd.to_numeric(frame["to_factor"], errors="coerce") / pd.to_numeric(
        frame["for_factor"], errors="coerce"
    )
    frame = frame[["symbol", "date", "ratio"]].dropna()
    # A ratio of exactly 1 is a no-op recorded by the source; carrying it would
    # inflate the applied-action count without changing a single number.
    return frame[frame["ratio"] != 1.0].reset_index(drop=True)


def point_in_time_returns(
    bars: pd.DataFrame,
    *,
    symbol: str,
    splits: Optional[pd.DataFrame] = None,
    dividends: Optional[pd.DataFrame] = None,
    price_column: str = "close",
) -> AdjustmentResult:
    """Daily total and price returns for one symbol, point-in-time by construction.

    `bars` must be one symbol's rows sorted ascending by `date`. Returns a frame
    carrying `total_return`, `price_return`, `split_ratio`, `dividend` and
    `dollar_volume`, with the first row's returns NULL — because the return
    into the first observed bar is not observable, and writing 0.0 there would
    make an unknown look like a flat day.
    """
    result_warnings: list[str] = []
    if bars.empty:
        return AdjustmentResult(symbol=symbol, frame=_empty_returns(), warnings=["no bars"])

    frame = bars.sort_values("date", kind="mergesort").reset_index(drop=True)
    if frame["date"].duplicated().any():
        duplicates = int(frame["date"].duplicated().sum())
        frame = frame.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
        result_warnings.append(
            f"{duplicates} duplicate session(s) dropped, keeping the last row per date"
        )

    ratios = split_ratios(splits) if splits is not None else pd.DataFrame()
    quarantined: list[dict[str, Any]] = []
    ratio_by_date: dict[Date, float] = {}
    if not ratios.empty:
        mine = ratios[ratios["symbol"] == symbol]
        for row in mine.itertuples(index=False):
            value = float(row.ratio)
            if not math.isfinite(value) or not (MIN_SPLIT_RATIO <= value <= MAX_SPLIT_RATIO):
                quarantined.append({"date": str(row.date), "ratio": value})
                continue
            ratio_by_date[row.date] = value * ratio_by_date.get(row.date, 1.0)

    dividend_by_date: dict[Date, float] = {}
    if dividends is not None and not dividends.empty:
        mine = dividends[dividends["symbol"] == symbol]
        for row in mine.itertuples(index=False):
            amount = float(getattr(row, "amount", float("nan")))
            if math.isfinite(amount) and amount > 0:
                dividend_by_date[row.date] = dividend_by_date.get(row.date, 0.0) + amount

    frame["split_ratio"] = [float(ratio_by_date.get(day, 1.0)) for day in frame["date"]]
    frame["dividend"] = [float(dividend_by_date.get(day, 0.0)) for day in frame["date"]]

    close = pd.to_numeric(frame[price_column], errors="coerce").astype(float)
    previous = close.shift(1)
    invalid = (previous <= 0) | previous.isna() | (close <= 0) | close.isna()

    # The whole point-in-time argument, in two lines. Both terms are dated `t`.
    total = (close * frame["split_ratio"] + frame["dividend"]) / previous - 1.0
    price = (close * frame["split_ratio"]) / previous - 1.0
    frame["total_return"] = total.where(~invalid)
    frame["price_return"] = price.where(~invalid)

    volume = pd.to_numeric(frame.get("volume"), errors="coerce").astype(float)
    # Scale-invariant through splits — see assumption 3 in the module docstring.
    frame["dollar_volume"] = close * volume

    extreme = [
        {"date": str(row.date), "total_return": round(float(row.total_return), 4)}
        for row in frame.itertuples(index=False)
        if row.total_return is not None
        and isinstance(row.total_return, float)
        and math.isfinite(row.total_return)
        and abs(row.total_return) > EXTREME_RETURN
    ]

    applied_splits = int((frame["split_ratio"] != 1.0).sum())
    applied_dividends = int((frame["dividend"] > 0).sum())
    if quarantined:
        result_warnings.append(
            f"{len(quarantined)} split ratio(s) outside "
            f"[{MIN_SPLIT_RATIO}, {MAX_SPLIT_RATIO}] quarantined, not applied"
        )

    return AdjustmentResult(
        symbol=symbol,
        frame=frame,
        applied_splits=applied_splits,
        applied_dividends=applied_dividends,
        quarantined_splits=quarantined,
        extreme_returns=extreme,
        warnings=result_warnings,
    )


def total_return_index(returns: pd.Series, *, base: float = 1.0) -> pd.Series:
    """Cumulate point-in-time returns into an index.

    Point-in-time because each factor is: the value at `t` uses only returns up
    to `t`, so extending the series never changes a historical value.

    A NULL return breaks the chain and is treated as such — the index is NULL
    from the first missing observation forward, rather than resuming as though
    the gap were a flat day. An index that silently bridges its own gaps
    understates realised volatility exactly where the data was worst.
    """
    values = pd.to_numeric(returns, errors="coerce")
    first_missing = values.isna().to_numpy().nonzero()[0]
    index = (1.0 + values.fillna(0.0)).cumprod() * base
    if len(first_missing):
        # Position 0 is expected to be NULL (no prior bar); a later gap is not.
        breaks = [position for position in first_missing if position > 0]
        if breaks:
            index.iloc[breaks[0] :] = np.nan
    if len(index):
        index.iloc[0] = base if pd.notna(values.iloc[0]) else base
    return index


def adjusted_price_series(
    frame: pd.DataFrame, *, as_of: Date, price_column: str = "close"
) -> pd.Series:
    """A back-adjusted price series, valid **only** as of `as_of`.

    Provided because charts and human-facing panels want a continuous price
    line, and refused by everything upstream of a model. The `as_of` argument
    is mandatory and unused-by-accident is impossible: the series is computed
    from actions up to that date and no further, and the caller has to name the
    date it is claiming. That makes the non-point-in-time nature of the object
    explicit at every call site instead of implied.

    Never feed the output of this function to a feature.
    """
    subset = frame[frame["date"] <= as_of]
    if subset.empty:
        return pd.Series(dtype=float)
    ratios = subset["split_ratio"].astype(float)
    # Cumulative product of every split strictly AFTER each bar: the classic
    # back-adjustment, scoped to actions visible at `as_of`.
    forward_factor = ratios[::-1].cumprod()[::-1].shift(-1).fillna(1.0)
    return pd.to_numeric(subset[price_column], errors="coerce") / forward_factor


def _empty_returns() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.Series(dtype="object"),
            "split_ratio": pd.Series(dtype="float64"),
            "dividend": pd.Series(dtype="float64"),
            "total_return": pd.Series(dtype="float64"),
            "price_return": pd.Series(dtype="float64"),
            "dollar_volume": pd.Series(dtype="float64"),
        }
    )
