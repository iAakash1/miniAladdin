"""The same instant must not become a different session because of its encoding.

Vendors deliver daily bars as an epoch stamp. Reading the calendar date off
that instant in UTC gives the right answer for a US venue — but only because
Eastern is behind UTC, so midnight ET lands at 04:00 or 05:00 UTC on the same
date. Nothing in the expression said that, and nothing would have failed if the
assumption stopped holding.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from src.quant.pit.calendar import EXCHANGE_TIMEZONE, session_date_from_epoch

ET = ZoneInfo("America/New_York")
TOKYO = ZoneInfo("Asia/Tokyo")


def _utc_reading(epoch_seconds: float) -> str:
    """The expression this replaced."""
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).strftime("%Y-%m-%d")


def _epoch(date: str, hour: int = 0, minute: int = 0, tz=ET) -> float:
    y, m, d = map(int, date.split("-"))
    return datetime(y, m, d, hour, minute, tzinfo=tz).timestamp()


# --- the sessions that actually matter --------------------------------------

@pytest.mark.parametrize(
    "session",
    ["2024-01-02", "2024-03-08", "2024-03-11", "2024-06-14",
     "2024-11-01", "2024-11-04", "2024-12-31", "2025-01-02"],
)
@pytest.mark.parametrize("hour", [0, 4, 9, 12, 16, 20, 23])
def test_every_hour_of_a_session_resolves_to_that_session(session: str, hour: int) -> None:
    assert session_date_from_epoch(_epoch(session, hour, 1)) == session


@pytest.mark.parametrize("session", ["2024-03-11", "2024-11-04"])
def test_dst_transitions_do_not_shift_a_session(session: str) -> None:
    """The Monday after each 2024 US clock change."""
    assert session_date_from_epoch(_epoch(session)) == session


def test_the_offset_actually_changes_across_the_transitions() -> None:
    """Proves the DST tests above are not vacuous."""
    winter = datetime(2024, 1, 15, 0, 0, tzinfo=ET).utcoffset()
    summer = datetime(2024, 7, 15, 0, 0, tzinfo=ET).utcoffset()
    assert winter != summer


# --- no historical bar moves -------------------------------------------------

@pytest.mark.parametrize(
    "session",
    ["2024-01-02", "2024-03-11", "2024-06-14", "2024-11-04", "2025-01-02"],
)
def test_midnight_et_bars_are_unchanged_by_the_fix(session: str) -> None:
    """Polygon stamps daily bars at midnight ET. Those must not move."""
    stamp = _epoch(session)
    assert session_date_from_epoch(stamp) == _utc_reading(stamp) == session


# --- the cases the old expression got wrong ----------------------------------

def test_a_late_session_stamp_was_pushed_into_the_next_day() -> None:
    """20:01 ET is 00:01 UTC the following date."""
    stamp = _epoch("2024-06-14", 20, 1)
    assert _utc_reading(stamp) == "2024-06-15"
    assert session_date_from_epoch(stamp) == "2024-06-14"


def test_an_eastern_venue_was_pulled_into_the_previous_day() -> None:
    """Midnight in Tokyo is 15:00 UTC the previous date."""
    stamp = _epoch("2024-06-14", 0, 0, tz=TOKYO)
    assert _utc_reading(stamp) == "2024-06-13"


def test_the_venue_is_named_rather_than_assumed() -> None:
    assert EXCHANGE_TIMEZONE == "America/New_York"


def test_round_trip_is_stable_across_representations() -> None:
    """The same instant, expressed three ways, is one session."""
    session = "2024-06-14"
    instant = datetime(2024, 6, 14, 14, 30, tzinfo=ET)
    as_utc = instant.astimezone(timezone.utc)
    as_tokyo = instant.astimezone(TOKYO)
    stamps = {instant.timestamp(), as_utc.timestamp(), as_tokyo.timestamp()}
    assert len(stamps) == 1
    assert session_date_from_epoch(stamps.pop()) == session
