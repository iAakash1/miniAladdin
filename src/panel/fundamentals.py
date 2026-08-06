"""
Point-in-time fundamentals from SEC XBRL.

The panel's fundamental, quality and news columns have been NULL since it was
built, because computing them honestly needs the date each figure became
public — and the vendor fundamentals endpoints return only the current value,
with no filing date attached. Using those would date every fundamental to
today and backdate it silently through the whole history: look-ahead bias in
its most damaging form, because it makes results better rather than obviously
wrong.

SEC companyfacts carries `filed` on every fact. That single field is what
makes this possible.

## The rule

For an observation date **D**, a fact is visible only if `filed <= D`. Among
the visible filings, each fiscal period resolves to its **most recently filed**
value — which is the market's best knowledge of that period on D, restatements
included exactly when they were published and not a day earlier.

That is the whole design. It also means a figure can *change* for a past
period as later filings arrive, which is correct and is precisely what a
single-snapshot fundamentals API cannot represent.

## Why annual comparatives matter

A 10-K reports the current year and the prior year side by side, so a
year-over-year change is computable from one filing rather than stitched
across two. That avoids a subtle trap: two filings can restate the same period
differently, and differencing across them would measure the restatement rather
than the business.
"""

from __future__ import annotations

import bisect
import logging
from dataclasses import dataclass
from datetime import date as Date
from typing import Any, Optional

logger = logging.getLogger("omnisignal.panel.fundamentals")

#: Annual filings only for year-over-year work. Quarterlies carry seasonality
#: that a naive YoY on mixed periods would read as growth.
ANNUAL_FORM = "10-K"


@dataclass(frozen=True)
class Fact:
    label: str
    period_end: str
    value: float
    filed: str
    form: str


class PointInTimeFacts:
    """SEC facts for one symbol, queryable as of any date.

    Rows are sorted once by filing date so each query is a binary search
    rather than a scan — the panel calls this once per (symbol, date), which
    on a 30-name weekly panel is several thousand lookups.
    """

    __slots__ = ("_rows", "_filed_dates")

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        usable = [row for row in rows if row.get("filed") and row.get("value") is not None]
        self._rows = sorted(usable, key=lambda row: str(row["filed"]))
        self._filed_dates = [str(row["filed"]) for row in self._rows]

    def __len__(self) -> int:
        return len(self._rows)

    def visible(self, on: Date) -> list[dict[str, Any]]:
        """Every fact filed on or before `on`."""
        cutoff = bisect.bisect_right(self._filed_dates, on.isoformat())
        return self._rows[:cutoff]

    def annual_series(self, label: str, on: Date) -> list[Fact]:
        """Annual values for `label` as known on `on`, oldest period first.

        One entry per fiscal period end, resolved to the most recently filed
        value among filings visible on `on`. Restatements therefore appear
        exactly when they were published.
        """
        by_period: dict[str, dict[str, Any]] = {}
        for row in self.visible(on):
            if row.get("label") != label or row.get("form") != ANNUAL_FORM:
                continue
            period = row.get("period_end")
            if not period:
                continue
            known = by_period.get(period)
            if known is None or str(row["filed"]) >= str(known["filed"]):
                by_period[period] = row

        return [
            Fact(
                label=label,
                period_end=row["period_end"],
                value=float(row["value"]),
                filed=str(row["filed"]),
                form=str(row.get("form") or ""),
            )
            for _, row in sorted(by_period.items())
        ]

    def latest(self, label: str, on: Date) -> Optional[Fact]:
        series = self.annual_series(label, on)
        return series[-1] if series else None

    def year_over_year(self, label: str, on: Date) -> Optional[float]:
        """Fractional change between the two most recent annual periods.

        None when fewer than two periods are visible, or when the base is
        non-positive — a growth rate off a zero or negative base is not a
        growth rate.
        """
        series = self.annual_series(label, on)
        if len(series) < 2:
            return None
        base, current = series[-2].value, series[-1].value
        if base <= 0:
            return None
        return current / base - 1.0

    def ratio(self, numerator: str, denominator: str, on: Date) -> Optional[float]:
        """Ratio of two labels from the same point-in-time view."""
        top = self.latest(numerator, on)
        bottom = self.latest(denominator, on)
        if top is None or bottom is None or bottom.value <= 0:
            return None
        return top.value / bottom.value

    def as_of_summary(self, on: Date) -> dict[str, Any]:
        """What was knowable on `on` — for surfacing provenance in the product."""
        visible = self.visible(on)
        if not visible:
            return {"facts_visible": 0, "latest_filing": None}
        return {
            "facts_visible": len(visible),
            "latest_filing": str(visible[-1]["filed"]),
            "labels": sorted({row["label"] for row in visible}),
        }


def load(symbol: str) -> PointInTimeFacts:
    """Fetch a symbol's full filed history. Never raises; empty on failure."""
    from src.providers.vendors.sec_vendor import SECVendor

    try:
        return PointInTimeFacts(SECVendor().get_xbrl_timeline(symbol))
    except Exception:  # noqa: BLE001 — one symbol's filings never fail a build
        logger.exception("sec: xbrl timeline failed for %s", symbol)
        return PointInTimeFacts([])
