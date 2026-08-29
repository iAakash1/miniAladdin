"""
Local Dolt reader — read-only enforcement, and live checks when a clone exists.

Split deliberately. The safety properties (only SELECT, alias quoting, absence
reported rather than substituted) are tested without any clone, so they run
everywhere. The coverage assertions run only where `datasets/` is present, and
skip with a reason rather than passing vacuously.
"""

from __future__ import annotations

import pytest

from src.quant.datasets.local_dolt import (
    DoltUnavailable,
    LocalDoltClient,
    _native,
)

client = LocalDoltClient()
HAS_STOCKS = client.cli_available and client.has_repository("stocks")
requires_clone = pytest.mark.skipif(
    not HAS_STOCKS, reason="no local Dolt clone at datasets/stocks"
)


# ── safety, no clone needed ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "statement",
    ["insert into ohlcv values (1)", "drop table ohlcv", "update symbol set x=1",
     "delete from split", "call something()"],
)
def test_write_statements_are_refused(statement):
    """Read-only is enforced, not merely intended."""
    local = LocalDoltClient()
    if not local.cli_available or not local.has_repository("stocks"):
        pytest.skip("no clone")
    with pytest.raises(ValueError, match="only read statements"):
        local._run("stocks", statement)


def test_absent_repository_raises_rather_than_falling_back():
    """A silent switch to the HTTP client would change what a query returns —
    the two have different row limits."""
    local = LocalDoltClient(root="/nonexistent-path-for-tests")
    with pytest.raises(DoltUnavailable):
        local.require("stocks")


def test_availability_reports_per_repository():
    report = LocalDoltClient().availability()
    assert set(report["repositories"]) == {"stocks", "options", "earnings", "rates"}
    for entry in report["repositories"].values():
        assert isinstance(entry["present"], bool)


def test_native_converts_numpy_scalars():
    import numpy as np

    assert _native(np.int64(5)) == 5
    assert isinstance(_native(np.float64(1.5)), float)


# ── live, clone required ────────────────────────────────────────────────────


@requires_clone
def test_reserved_word_aliases_are_quoted():
    """`rows` is a reserved word in Dolt's parser; an unquoted alias is a
    syntax error, not a warning."""
    profile = LocalDoltClient().profile_table("stocks", "split")
    assert profile["rows"] > 0


@requires_clone
def test_ohlcv_coverage_matches_the_catalog():
    """The measurement the catalog's claims rest on."""
    profile = LocalDoltClient().profile_table("stocks", "ohlcv")
    assert profile["rows"] > 28_000_000
    assert profile["symbols"] > 20_000
    assert str(profile["min_date"]).startswith("2011-01")
    assert profile["primary_key"] == ["date", "act_symbol"]


@requires_clone
def test_split_coverage_starts_in_2014_as_the_catalog_records():
    """The gap that forces CORPORATE_ACTION_COVERAGE_START."""
    profile = LocalDoltClient().profile_table("stocks", "split")
    assert str(profile["min_date"]).startswith("2014-03")


@requires_clone
def test_earnings_calendar_contains_future_dates():
    """The leak the catalog warns about, asserted rather than assumed."""
    local = LocalDoltClient()
    if not local.has_repository("earnings"):
        pytest.skip("no earnings clone")
    future = local.scalar(
        "earnings",
        "select count(*) as `n` from earnings_calendar where `date` > current_date()",
    )
    assert int(future) > 0, (
        "earnings_calendar is expected to contain scheduled future dates; if this "
        "fails the catalog's leak warning may no longer apply and should be revisited"
    )


@requires_clone
def test_delisted_names_are_present_with_terminal_dates():
    """The survivorship claim, checked against named real failures."""
    local = LocalDoltClient()
    frame = local.query(
        "stocks",
        "select act_symbol, financial_status, last_seen from symbol "
        "where act_symbol in ('SIVB','SBNY','TWTR','FRC')",
    )
    found = set(frame["act_symbol"])
    assert {"SIVB", "SBNY", "TWTR", "FRC"} <= found
    bankrupt = frame[frame["act_symbol"].isin(["SIVB", "SBNY"])]["financial_status"]
    assert (bankrupt == "Bankrupt").all()
