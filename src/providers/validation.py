"""
Price series validation at the provider boundary.

## Why this exists

`OHLCVBar.close` was typed `float` and nothing else. `float` happily accepts
`0.0`, `-1.0`, `nan` and `inf`, and the schema layer had **zero validators**,
so a vendor returning garbage handed it straight to 25 consumption sites
across the scoring engine, the panel builder, the dashboard and the backtest
service — every one of which assumes prices are positive and finite.

That is not a hypothetical. A zero close was observed crashing four of eleven
sector rows with `float division by zero` while the primary vendor was in
cooldown and the chain had fallen through to a weaker source.

The crash was the *lucky* outcome. A zero close inside a return calculation
produces a −100% return, and −100% is a perfectly plausible-looking number:
it flows into the momentum factors as real signal, into the score, into the
verdict, and — once the panel builds — gets recorded as point-in-time truth.
Silent corruption is far worse than a stack trace.

## The policy, and the evidence behind it

Measured across 1,879 bars from three vendors (polygon, twelvedata,
yfinance): zero non-positive closes, zero non-finite values, zero bars with
`high < low`, zero closes outside `[low, high]`. Real data is clean, which
means strict rules cost nothing on the happy path.

So the rules split by *certainty*, not by severity:

**Dropped** — cannot possibly be a real price, no interpretation salvages it:

  - `close` non-finite (`nan`, `inf`)
  - `close <= 0`
  - `high < low` (an impossible bar)

**Recorded, not dropped** — suspicious but legitimately produced by real
vendors:

  - `close` outside `[low, high]`. Vendors that return *adjusted* closes
    apply dividend and split adjustments to the close but not always to the
    intraday high and low, so an out-of-range close is a known artifact of
    adjustment, not evidence of corruption. Dropping these would discard
    good data to satisfy a rule that does not hold in practice.

Dropping is silent data loss, which this repository does not do quietly:
every drop is counted in `SeriesQuality` and carried on the series itself,
so a consumer can see that a "252-bar year" was really 249 bars and three
rejections.

## Retention

A series that loses more than `MIN_RETENTION` of its bars is not a series
with a few bad ticks — it is a vendor malfunctioning. `is_trustworthy` says
so, letting the fallback chain move on rather than scoring a fiction.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

from pydantic import BaseModel, Field

#: Below this fraction of surviving bars, the vendor is malfunctioning rather
#: than merely imperfect. 0.95 is deliberately strict: measured real vendors
#: drop *nothing*, so anything losing 1-in-20 bars is an outlier worth
#: falling through for.
MIN_RETENTION = 0.95


class SeriesQuality(BaseModel):
    """What validation found. Attached to every series, never discarded.

    Exists so that dropping a bar is *visible*. A consumer that silently
    receives 249 bars where the vendor sent 252 cannot tell the difference
    between a short year and a rejected one.
    """

    bars_received: int = 0
    bars_kept: int = 0
    dropped_non_finite: int = 0
    dropped_non_positive: int = 0
    dropped_impossible_range: int = 0
    #: Not dropped — see the module docstring on adjusted closes.
    suspicious_close_outside_range: int = 0

    @property
    def dropped(self) -> int:
        return (
            self.dropped_non_finite
            + self.dropped_non_positive
            + self.dropped_impossible_range
        )

    @property
    def retention(self) -> float:
        """Fraction of received bars that survived. 1.0 for an empty series.

        Empty is not a validation failure — it is an absent series, which the
        callers above already handle. Reporting 0.0 retention would make
        `is_trustworthy` reject a vendor for having no data rather than for
        having bad data, and those need different responses.
        """
        if self.bars_received == 0:
            return 1.0
        return self.bars_kept / self.bars_received

    @property
    def is_clean(self) -> bool:
        return self.dropped == 0 and self.suspicious_close_outside_range == 0

    @property
    def is_trustworthy(self) -> bool:
        return self.retention >= MIN_RETENTION

    def summary(self) -> str:
        if self.is_clean:
            return f"{self.bars_kept} bars, clean"
        parts = []
        if self.dropped_non_finite:
            parts.append(f"{self.dropped_non_finite} non-finite")
        if self.dropped_non_positive:
            parts.append(f"{self.dropped_non_positive} non-positive")
        if self.dropped_impossible_range:
            parts.append(f"{self.dropped_impossible_range} high<low")
        if self.suspicious_close_outside_range:
            parts.append(f"{self.suspicious_close_outside_range} close outside range")
        return f"{self.bars_kept}/{self.bars_received} bars ({', '.join(parts)})"


def _is_finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def sanitize_bars(bars: Sequence[Any]) -> tuple[list[Any], SeriesQuality]:
    """Drop impossible bars, count everything, keep the rest in order.

    Order is preserved because every consumer treats bar order as chronological
    and `bars[-1]` as "latest". Returns the surviving bars and what happened.
    """
    quality = SeriesQuality(bars_received=len(bars))
    kept: list[Any] = []

    for bar in bars:
        close = getattr(bar, "close", None)

        if not _is_finite(close):
            quality.dropped_non_finite += 1
            continue
        if close <= 0:
            quality.dropped_non_positive += 1
            continue

        low, high = getattr(bar, "low", None), getattr(bar, "high", None)
        if _is_finite(low) and _is_finite(high):
            if high < low:
                quality.dropped_impossible_range += 1
                continue
            # Recorded, not dropped: adjusted closes legitimately sit outside
            # the unadjusted intraday range.
            if not (low <= close <= high):
                quality.suspicious_close_outside_range += 1

        kept.append(bar)

    quality.bars_kept = len(kept)
    return kept, quality
