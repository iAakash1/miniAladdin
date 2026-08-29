"""
Trading calendar — discovered from observed data, never hardcoded.

A hardcoded holiday table is wrong the first time an exchange closes
unexpectedly, and wrong silently: a study that expects a bar on a day the
market did not open reads the absence as missing data and either fills it or
drops the name. Both are errors, and neither announces itself.

So the calendar here is the set of dates on which the market **was observed to
trade**, taken from the ingested price data. Its authority is the same as the
data's, which is the only defensible arrangement: a date is a session because
bars exist for it.

The consequence worth stating: this calendar cannot describe a date outside
the ingested range, and `sessions_between` says so rather than extrapolating.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import date as Date
from typing import Iterable, Optional, Sequence


class CalendarRangeError(ValueError):
    """Raised when a query falls outside the observed range."""


@dataclass(frozen=True)
class TradingCalendar:
    """An immutable, sorted set of observed trading sessions."""

    sessions: tuple[Date, ...]

    @classmethod
    def from_dates(cls, dates: Iterable[Date]) -> "TradingCalendar":
        cleaned = sorted({_as_date(value) for value in dates})
        if not cleaned:
            raise ValueError("a trading calendar needs at least one observed session")
        return cls(sessions=tuple(cleaned))

    def __len__(self) -> int:
        return len(self.sessions)

    @property
    def start(self) -> Date:
        return self.sessions[0]

    @property
    def end(self) -> Date:
        return self.sessions[-1]

    def contains(self, day: Date) -> bool:
        day = _as_date(day)
        index = bisect.bisect_left(self.sessions, day)
        return index < len(self.sessions) and self.sessions[index] == day

    def index_of(self, day: Date) -> int:
        """Position of an observed session. Raises for a non-session."""
        day = _as_date(day)
        index = bisect.bisect_left(self.sessions, day)
        if index >= len(self.sessions) or self.sessions[index] != day:
            raise CalendarRangeError(f"{day} is not an observed trading session")
        return index

    def on_or_before(self, day: Date) -> Optional[Date]:
        """The latest session at or before `day` — the point-in-time anchor.

        This is the function that converts a wall-clock cutoff into an
        observable one. A model asked for its view "as of Sunday" must be
        answered from Friday's close, and doing that anywhere other than here
        invites a different answer in each caller.
        """
        index = bisect.bisect_right(self.sessions, _as_date(day)) - 1
        return self.sessions[index] if index >= 0 else None

    def on_or_after(self, day: Date) -> Optional[Date]:
        index = bisect.bisect_left(self.sessions, _as_date(day))
        return self.sessions[index] if index < len(self.sessions) else None

    def shift(self, day: Date, sessions: int) -> Optional[Date]:
        """Move `sessions` trading days from an observed session.

        Returns None past either end rather than clamping. Clamping is how a
        forward-return label at the end of a sample silently becomes a shorter
        horizon than it claims, which flatters the final window of every
        walk-forward study.
        """
        index = self.index_of(day) + sessions
        if index < 0 or index >= len(self.sessions):
            return None
        return self.sessions[index]

    def sessions_between(self, start: Date, end: Date) -> tuple[Date, ...]:
        start, end = _as_date(start), _as_date(end)
        left = bisect.bisect_left(self.sessions, start)
        right = bisect.bisect_right(self.sessions, end)
        return self.sessions[left:right]

    def count_between(self, start: Date, end: Date) -> int:
        return len(self.sessions_between(start, end))

    def covers(self, start: Date, end: Date) -> bool:
        return self.start <= _as_date(start) and _as_date(end) <= self.end

    def sample(self, step: int) -> tuple[Date, ...]:
        """Every `step`-th session, for observation strides."""
        if step < 1:
            raise ValueError("step must be >= 1")
        return self.sessions[::step]


def _as_date(value: object) -> Date:
    if isinstance(value, Date):
        return value
    if hasattr(value, "date"):
        return value.date()  # type: ignore[no-any-return]
    return Date.fromisoformat(str(value)[:10])


def calendar_from_frame(frame, column: str = "date") -> TradingCalendar:
    """Build a calendar from any frame carrying a date column."""
    if column not in frame.columns:
        raise ValueError(f"frame has no {column!r} column")
    return TradingCalendar.from_dates(frame[column].dropna().unique())


def align_to_sessions(
    dates: Sequence[Date], calendar: TradingCalendar
) -> list[Date]:
    """Snap arbitrary dates back to the latest session at or before each.

    Dates before the calendar begins are dropped, not snapped forward — a
    request for information as of 2009 cannot be answered by 2011's first
    session without inventing two years of history.
    """
    out: list[Date] = []
    for day in dates:
        anchored = calendar.on_or_before(day)
        if anchored is not None:
            out.append(anchored)
    return out
