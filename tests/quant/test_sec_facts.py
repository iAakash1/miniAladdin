"""SEC fact store v3: curation exclusions, availability, the two PIT views, restatement invariance."""

from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from src.quant.pit import sec_facts as S
from src.quant.pit.calendar import TradingCalendar

SESSIONS = [d.date() for d in pd.bdate_range("2023-03-01", "2023-04-30") if d.date() != date(2023, 4, 7)]
CAL = TradingCalendar.from_dates(SESSIONS)


def num_rows(**overrides):
    base = {"adsh": "A-1", "tag": "Assets", "version": "us-gaap/2022", "ddate": "20221231", "qtrs": 0, "uom": "USD",
            "segments": pd.NA, "coreg": pd.NA, "value": 100.0, "footnote": pd.NA}
    base.update(overrides)
    return base


def registry(*rows):
    frame = pd.DataFrame(list(rows))
    frame["accepted_at"] = pd.to_datetime(frame["accepted_at"])
    return frame


def reg(adsh="A-1", cik=1, form="10-K", accepted="2023-03-10 09:00:00", **extra):
    base = {"adsh": adsh, "cik": cik, "name": "X CORP", "sic": 3571, "form": form, "period": "20221231", "fy": 2022,
            "fp": "FY", "filed": "20230310", "accepted_at": accepted, "prevrpt": 0, "former": pd.NA, "changed": pd.NA,
            "countryinc": "US", "stprinc": "DE", "ein": "1", "source_archive": "2023q1.zip"}
    base.update(extra)
    return base


def curate(rows, regs):
    frame = pd.DataFrame(rows)
    for column in ("segments", "coreg"):
        if column not in frame:
            frame[column] = pd.NA
    out, counts = S.curate_num(frame, registry(*regs), archive_name="2023q1.zip", archive_sha256="h" * 64, calendar=CAL)
    return out, counts


# ── curation ────────────────────────────────────────────────────────────────

def test_dimensional_rows_never_enter_the_store_and_are_counted():
    rows = [num_rows(), num_rows(segments="ProductOrService=Service;", value=5.0),
            num_rows(coreg="SUBSIDIARY", value=7.0)]
    out, counts = curate(rows, [reg()])
    assert list(out["value"]) == [100.0]
    assert counts["dimensional_excluded"] == 2


def test_unit_is_populated_and_wrong_currency_or_taxonomy_is_rejected():
    rows = [num_rows(), num_rows(uom="EUR", value=9.0), num_rows(version="ifrs-full/2022", value=8.0),
            num_rows(adsh="A-1", tag="Assets", version="A-1", value=6.0)]  # company extension carries the accession as version
    out, _ = curate(rows, [reg()])
    assert list(out["unit"]) == ["USD"] and list(out["value"]) == [100.0]
    assert out["unit"].notna().all()


def test_instant_and_duration_contexts_cannot_be_mixed():
    rows = [num_rows(tag="Assets", qtrs=4, value=1.0),           # instant fact with a duration
            num_rows(tag="NetIncomeLoss", qtrs=0, value=2.0),     # duration fact with no duration
            num_rows(tag="NetIncomeLoss", qtrs=4, value=3.0)]
    out, counts = curate(rows, [reg()])
    assert list(out["canonical_fact"]) == ["net_income"] and list(out["value"]) == [3.0]
    assert counts["context_mismatch_excluded"] == 2


def test_missing_values_are_dropped_not_zeroed():
    out, counts = curate([num_rows(value=np.nan), num_rows(tag="Liabilities", value=4.0)], [reg()])
    assert list(out["canonical_fact"]) == ["liabilities"] and counts["null_value_excluded"] == 1


def test_fallback_tags_are_kept_with_their_priority_not_coalesced():
    rows = [num_rows(tag="Revenues", qtrs=4, value=50.0), num_rows(tag="RevenueFromContractWithCustomerExcludingAssessedTax", qtrs=4, value=48.0)]
    out, _ = curate(rows, [reg()])
    assert sorted(zip(out["tag"], out["tag_priority"])) == [
        ("RevenueFromContractWithCustomerExcludingAssessedTax", 0), ("Revenues", 1)]


def test_shares_family_accepts_dei_and_us_gaap_only_in_shares_unit():
    rows = [num_rows(tag="EntityCommonStockSharesOutstanding", version="dei/2022", uom="shares", value=10.0),
            num_rows(tag="CommonStockSharesOutstanding", uom="shares", value=11.0),
            num_rows(tag="CommonStockSharesOutstanding", uom="USD", value=12.0)]
    out, _ = curate(rows, [reg()])
    assert sorted(out["value"]) == [10.0, 11.0]


def test_period_start_is_derived_and_labelled():
    out, _ = curate([num_rows(tag="NetIncomeLoss", qtrs=4, ddate="20221231")], [reg()])
    row = out.iloc[0]
    assert row["period_start"] == date(2022, 1, 1) and row["period_start_method"] == "derived_from_fsds_qtrs"


# ── availability (US Eastern wall clock, explicit) ──────────────────────────

@pytest.mark.parametrize("stamp,expected", [
    ("2023-03-10 09:00:00", date(2023, 3, 10)),     # pre-open: usable that session
    ("2023-03-10 15:59:59", date(2023, 3, 10)),     # before the close
    ("2023-03-10 16:00:00", date(2023, 3, 13)),     # at the close: next session (conservative)
    ("2023-03-10 16:30:00", date(2023, 3, 13)),     # after close, Friday: Monday
    ("2023-03-12 10:00:00", date(2023, 3, 13)),     # Sunday: Monday
    ("2023-04-06 17:00:00", date(2023, 4, 10)),     # Thursday after close, Friday 04-07 is a closed session
    ("2023-03-13 18:00:00", date(2023, 3, 14)),     # ordinary after-close
])
def test_after_close_acceptance_is_available_next_session(stamp, expected):
    assert S.available_session(pd.Timestamp(stamp), CAL) == expected


def test_timezone_is_explicit_and_dst_does_not_move_the_cutoff():
    assert S.ACCEPTANCE_TIMEZONE == "America/New_York"
    # 2023-03-13 is the first Monday after DST began; wall-clock 16:30 is still after the close
    assert S.available_session(pd.Timestamp("2023-03-13 16:30:00"), CAL) == date(2023, 3, 14)
    # an aware UTC stamp is converted to Eastern wall clock before the rule: 20:30Z on 03-13 = 16:30 EDT
    assert S.available_session(pd.Timestamp("2023-03-13 20:30:00", tz="UTC"), CAL) == date(2023, 3, 14)
    assert S.available_session(pd.Timestamp("2023-03-13 19:30:00", tz="UTC"), CAL) == date(2023, 3, 13)


def test_availability_beyond_the_calendar_is_none_never_clamped():
    assert S.available_session(pd.Timestamp("2023-04-28 10:00:00"), CAL) == date(2023, 4, 28)
    assert S.available_session(pd.Timestamp("2023-04-28 17:00:00"), CAL) is None  # the next session is not observed
    assert S.available_session(pd.Timestamp("2023-06-30 10:00:00"), CAL) is None


def test_curated_rows_carry_the_available_session():
    out, _ = curate([num_rows()], [reg(accepted="2023-03-10 17:00:00")])
    assert out.iloc[0]["available_session"] == date(2023, 3, 13)


# ── views ───────────────────────────────────────────────────────────────────

def vintage(accession, accepted, value, *, tag="Revenues", priority=1, cik=1, period_end=date(2022, 12, 31), form="10-K"):
    return {"cik": cik, "accession": accession, "form": form, "accepted_at": pd.Timestamp(accepted),
            "available_session": None, "canonical_fact": "revenue", "tag": tag, "tag_priority": priority,
            "context_type": "duration", "qtrs": 4, "unit": "USD", "value": value,
            "period_start": date(2022, 1, 1), "period_end": period_end}


def test_as_of_prefers_the_primary_tag_within_the_same_filing():
    facts = pd.DataFrame([vintage("A", "2023-03-10 09:00", 48.0, tag="RevenueFromContractWithCustomerExcludingAssessedTax", priority=0),
                          vintage("A", "2023-03-10 09:00", 50.0, tag="Revenues", priority=1)])
    assert S.as_of(facts, "2023-04-01")["value"].tolist() == [48.0]
    assert S.first_reported(facts)["value"].tolist() == [48.0]


def test_first_reported_is_the_earliest_vintage_and_as_of_the_latest_available():
    facts = pd.DataFrame([vintage("A", "2023-03-10 09:00", 100.0), vintage("B", "2023-05-15 17:00", 90.0, form="10-K/A")])
    assert S.first_reported(facts)["value"].tolist() == [100.0]
    assert S.as_of(facts, "2023-05-15 16:59:59")["value"].tolist() == [100.0]
    assert S.as_of(facts, "2023-05-15 17:00:00")["value"].tolist() == [90.0]
    assert S.as_of(facts, "2023-03-09")["value"].tolist() == []


def test_amendments_are_new_rows_and_the_original_vintage_survives():
    facts = pd.DataFrame([vintage("A", "2023-03-10 09:00", 100.0), vintage("B", "2023-05-15 17:00", 90.0, form="10-K/A")])
    assert sorted(facts["value"]) == [90.0, 100.0] and len(S.canonical_per_filing(facts)) == 2


def test_as_of_session_uses_the_availability_session():
    rows = [vintage("A", "2023-03-10 17:00", 100.0), vintage("B", "2023-03-20 09:00", 80.0, form="10-K/A")]
    rows[0]["available_session"] = date(2023, 3, 13)
    rows[1]["available_session"] = date(2023, 3, 20)
    facts = pd.DataFrame(rows)
    assert S.as_of_session(facts, date(2023, 3, 10))["value"].tolist() == []
    assert S.as_of_session(facts, date(2023, 3, 13))["value"].tolist() == [100.0]
    assert S.as_of_session(facts, date(2023, 3, 20))["value"].tolist() == [80.0]


# ── restatement invariance ──────────────────────────────────────────────────

def test_source_truncation_at_t_leaves_every_pre_t_view_identical():
    facts = pd.DataFrame([
        vintage("A", "2023-03-10 09:00", 100.0),
        vintage("B", "2023-05-15 17:00", 90.0, form="10-K/A"),                      # restates the same period later
        vintage("C", "2023-08-01 09:00", 120.0, period_end=date(2023, 6, 30), form="10-Q"),
        vintage("D", "2024-02-20 09:00", 60.0, form="10-K/A"),                       # a much later restatement
    ])
    truncated = facts[facts["accepted_at"] <= pd.Timestamp("2023-06-01")]
    for t in ("2023-04-01", "2023-05-15 16:00", "2023-06-01"):
        pd.testing.assert_frame_equal(S.as_of(facts, t), S.as_of(truncated, t))
    assert S.content_hash(facts[facts["accepted_at"] <= pd.Timestamp("2023-06-01")]) == S.content_hash(truncated)
    # the first-reported value of a period never changes when a later restatement arrives
    early = S.first_reported(truncated).set_index("period_end")["value"]
    full = S.first_reported(facts).set_index("period_end")["value"]
    assert early.loc[date(2022, 12, 31)] == full.loc[date(2022, 12, 31)] == 100.0


def test_a_later_restatement_cannot_rewrite_history_at_any_decision_time():
    facts = pd.DataFrame([vintage("A", "2023-03-10 09:00", 100.0), vintage("B", "2024-01-05 09:00", 55.0, form="10-K/A")])
    for t in pd.date_range("2023-03-11", "2024-01-04", freq="30D"):
        assert S.as_of(facts, t)["value"].tolist() == [100.0]


def test_conflicting_duplicates_and_tag_disagreements_are_reported_not_resolved():
    facts = pd.DataFrame([vintage("A", "2023-03-10 09:00", 100.0, tag="Revenues", priority=1),
                          vintage("A", "2023-03-10 09:00", 100.0, tag="Revenues", priority=1),
                          vintage("A", "2023-03-10 09:00", 101.0, tag="Revenues", priority=1),
                          vintage("A", "2023-03-10 09:00", 98.0, tag="SalesRevenueNet", priority=2)])
    assert len(S.duplicate_conflicts(facts)) == 1
    assert len(S.tag_disagreements(facts)) == 1


def test_content_hash_is_order_independent_and_sensitive():
    facts = pd.DataFrame([vintage("A", "2023-03-10 09:00", 100.0), vintage("B", "2023-05-15 17:00", 90.0)])
    for column in S.CURATED_COLUMNS:
        if column not in facts:
            facts[column] = None
    assert S.content_hash(facts) == S.content_hash(facts.iloc[::-1])
    changed = facts.copy(); changed.loc[0, "value"] = 101.0
    assert S.content_hash(changed) != S.content_hash(facts)
