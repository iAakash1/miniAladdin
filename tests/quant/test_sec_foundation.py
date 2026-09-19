from datetime import date, datetime

import pandas as pd
import pytest

from src.quant.pit.calendar import TradingCalendar
from src.quant.pit.sec_foundation import (
    as_of, available_session, conflict_report, curate_sec_rows, ff12_from_sic,
    first_reported, validate_identity_intervals,
)


def _inputs():
    sub = pd.DataFrame([
        {"adsh": "a", "cik": 1, "form": "10-Q", "filed": 20240102, "accepted": "20240102153000", "fy": 2023, "fp": "Q3", "sic": 3571, "name": "Issuer"},
        {"adsh": "b", "cik": 1, "form": "10-Q/A", "filed": 20240103, "accepted": "20240103170000", "fy": 2023, "fp": "Q3", "sic": 3571, "name": "Issuer"},
    ])
    num = pd.DataFrame([
        {"adsh": "a", "tag": "Revenues", "version": "us-gaap/2023", "ddate": 20230930, "qtrs": 1, "uom": "USD", "value": 10.0, "frame": "CY2023Q3"},
        {"adsh": "b", "tag": "Revenues", "version": "us-gaap/2023", "ddate": 20230930, "qtrs": 1, "uom": "USD", "value": 12.0, "frame": "CY2023Q3"},
    ])
    return sub, num


def test_filing_vintages_do_not_rewrite_history_and_truncate_invariant():
    sub, num = _inputs()
    facts = curate_sec_rows(sub, num, archive_hash="abc")
    assert len(facts) == 2 and facts["amendment"].tolist() == [False, True]
    assert first_reported(facts).iloc[0]["value"] == 10
    assert as_of(facts, "2024-01-02 16:00").iloc[0]["value"] == 10
    assert as_of(facts, "2024-01-04").iloc[0]["value"] == 12
    truncated = curate_sec_rows(sub, num, archive_hash="abc", accepted_cutoff="2024-01-02 23:59:59")
    pd.testing.assert_frame_equal(facts[facts["accepted_at"] <= pd.Timestamp("2024-01-02 23:59:59")].reset_index(drop=True), truncated)


def test_formatted_sec_accepted_timestamp_is_preserved():
    sub, num = _inputs()
    sub.loc[0, "accepted"] = "2024-01-02 15:30:00.0"
    facts = curate_sec_rows(sub.iloc[:1], num.iloc[:1], archive_hash="abc")
    assert facts.iloc[0]["accepted_at"] == pd.Timestamp("2024-01-02 15:30:00")


def test_conflicts_are_surfaced_and_contexts_not_mixed():
    sub, num = _inputs()
    num = pd.concat([num, pd.DataFrame([{**num.iloc[0].to_dict(), "value": 11.0}]),
                     pd.DataFrame([{"adsh": "a", "tag": "Assets", "version": "us-gaap/2023", "ddate": 20230930, "qtrs": 1, "uom": "USD", "value": 99.0, "frame": "CY2023Q3I"}])], ignore_index=True)
    facts = curate_sec_rows(sub, num, archive_hash="abc")
    assert len(conflict_report(facts)) == 1
    assert "assets" not in set(facts["canonical_fact"])
    assert facts["source_archive_hash"].notna().all() and facts["accepted_at"].notna().all()


def test_after_close_moves_to_next_observed_session():
    calendar = TradingCalendar.from_dates([date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 5)])
    assert available_session(datetime(2024, 1, 2, 15, 59), calendar) == date(2024, 1, 2)
    assert available_session(datetime(2024, 1, 2, 16, 1), calendar) == date(2024, 1, 3)
    assert available_session(datetime(2024, 1, 4, 12), calendar) == date(2024, 1, 5)


def test_identity_overlap_ticker_reuse_and_sic_mapping():
    intervals = pd.DataFrame([
        {"security_id": "sec-cik1", "effective_from": "2020-01-01", "effective_to": "2021-01-01"},
        {"security_id": "sec-cik1", "effective_from": "2021-01-02", "effective_to": None},
        {"security_id": "sec-cik2", "effective_from": "2021-01-01", "effective_to": None},
    ])
    validate_identity_intervals(intervals)
    assert len({"sec-cik1", "sec-cik2"}) == 2
    assert ff12_from_sic(3571) == "BusEq" and ff12_from_sic(6021) == "Money"
    overlap = intervals.iloc[:2].copy()
    overlap.loc[overlap.index[1], "effective_from"] = "2020-12-31"
    with pytest.raises(ValueError):
        validate_identity_intervals(overlap)
    open_overlap = intervals.iloc[:2].copy()
    open_overlap.loc[open_overlap.index[0], "effective_to"] = None
    with pytest.raises(ValueError):
        validate_identity_intervals(open_overlap)
