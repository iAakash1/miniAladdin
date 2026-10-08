"""How old a macro observation may be and still describe the present.

Macro series publish on different cadences, so a single threshold would be wrong
for most of them: a daily curve spread that is three weeks old has stopped
updating, while a monthly CPI print that is three weeks old is the latest there
is. The limits are generous on purpose - they catch a feed that has *stopped*,
not one that is merely late.

One definition, because the research route and the dashboard each compute a
regime and a regime computed from a dead series on one page and refused on the
other is the sort of disagreement this product exists not to have.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

#: Field -> the oldest latest-observation (in days) that still counts as current.
MAX_OBSERVATION_AGE_DAYS: dict[str, int] = {
    "yield_spread": 21,      # T10Y2Y: daily
    "inflation_rate": 120,   # CPIAUCNS: monthly, published ~2 weeks after month end
    "fed_funds_rate": 100,   # FEDFUNDS: monthly
}

#: The two observations the regime multiplier is computed from. The policy rate
#: is optional, so a stale one is dropped on its own instead of taking the regime.
GATING_FIELDS = ("yield_spread", "inflation_rate")

LABELS = {
    "yield_spread": "10Y-2Y term spread",
    "inflation_rate": "CPI inflation",
    "fed_funds_rate": "policy rate",
}


def stale_fields(observation_dates: Optional[dict[str, str]], today: Optional[date] = None) -> list[str]:
    """Fields whose latest observation is too old to describe the present.

    A field with no recorded date is not judged: the absence of a date is a gap
    in provenance, not evidence that the value is old. A date that cannot be
    read, however, cannot vouch for its value.
    """
    today = today or datetime.now(timezone.utc).date()
    stale: list[str] = []
    for field, limit in MAX_OBSERVATION_AGE_DAYS.items():
        raw = (observation_dates or {}).get(field)
        if not raw:
            continue
        try:
            observed = date.fromisoformat(str(raw)[:10])
        except ValueError:
            stale.append(field)
            continue
        if (today - observed).days > limit:
            stale.append(field)
    return stale


def describe(fields: list[str]) -> str:
    return " and ".join(LABELS[f] for f in fields)
