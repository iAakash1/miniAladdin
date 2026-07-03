"""
FOMC decision dates — public schedule, eight per year.
Source: federalreserve.gov/monetarypolicy/fomccalendars.htm
Update annually (one minute of maintenance; deliberately static — no
scraping dependency for eight known dates).
"""

from __future__ import annotations

from datetime import date

FOMC_DECISION_DATES: list[date] = [
    # 2026 (decision = second day of each two-day meeting)
    date(2026, 1, 28),
    date(2026, 3, 18),
    date(2026, 4, 29),
    date(2026, 6, 17),
    date(2026, 7, 29),
    date(2026, 9, 16),
    date(2026, 10, 28),
    date(2026, 12, 9),
]


def business_days_to_next_fomc(today: date) -> int | None:
    """Business days until the next scheduled FOMC decision, None if calendar exhausted."""
    upcoming = [d for d in FOMC_DECISION_DATES if d >= today]
    if not upcoming:
        return None
    target = min(upcoming)
    days = 0
    cursor = today
    while cursor < target:
        cursor = cursor.fromordinal(cursor.toordinal() + 1)
        if cursor.weekday() < 5:
            days += 1
    return days
