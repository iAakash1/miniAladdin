"""Security master v3: identity keys, ticker reuse, evidence grades, dated SIC, exits, shares."""

from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from src.quant.pit import security_master as M

FRENCH_EXCERPT = """
 1 NoDur  Consumer Nondurables -- Food, Tobacco, Textiles, Apparel, Leather, Toys
          0100-0999
          2000-2399
 5 BusEq  Business Equipment -- Computers, Software, and Electronic Equipment
          3570-3579
          7370-7379
12 Other  Other -- Mines, Constr, BldMt, Trans, Hotels, Bus Serv, Entertainment
"""


def registry(rows):
    frame = pd.DataFrame(rows, columns=["adsh", "cik", "name", "former", "sic", "accepted_at"])
    frame["accepted_at"] = pd.to_datetime(frame["accepted_at"])
    return frame


# ── keys and names ──────────────────────────────────────────────────────────

def test_ticker_normalisation_matches_sec_share_class_style():
    assert M.normalize_ticker("BRK.B") == "BRK-B" and M.normalize_ticker(" brk/a ") == "BRK-A"


@pytest.mark.parametrize("left,right", [
    ("Aetna Inc. Common Stock", "AETNA INC /PA/"),
    ("Alexion Pharmaceuticals, Inc. - Common Stock", "ALEXION PHARMACEUTICALS INC"),
    ("Allergan plc Ordinary Shares", "ALLERGAN PLC"),
])
def test_names_normalise_to_one_issuer_key(left, right):
    assert M.normalize_name(left) == M.normalize_name(right) != ""


def test_different_issuers_do_not_collide():
    assert M.normalize_name("Apple Inc.") != M.normalize_name("Applied Materials, Inc.")
    assert M.normalize_name(None) == "" and M.normalize_name(float("nan")) == ""


def test_security_id_is_cik_based_and_ticker_independent():
    assert M.security_id(320193) == M.security_id("320193") == M.security_id(320193, "")
    assert M.security_id(320193) != M.security_id(320194)
    assert M.security_id(1652044, "GOOG") != M.security_id(1652044, "GOOGL")


# ── French industries ───────────────────────────────────────────────────────

def test_french_parser_and_lookup():
    rows = M.parse_french_sic(FRENCH_EXCERPT)
    assert {r["code"] for r in rows} == {"NoDur", "BusEq"}
    lookup = M.french_lookup(rows, M.french_residual(FRENCH_EXCERPT))
    assert M.french_residual(FRENCH_EXCERPT) == "Other"                 # a header with no ranges is the residual industry
    assert lookup(2050) == "NoDur" and lookup(7372) == "BusEq" and lookup(6199) == "Other"
    assert M.french_lookup(rows)(6199) is None                          # without a declared residual an unlisted SIC stays missing
    assert lookup(None) is None and lookup(float("nan")) is None


def test_classification_intervals_are_dated_and_repeat_sics_open_nothing():
    reg = registry([("a1", 1, "X", None, 3571, "2015-03-01"), ("a2", 1, "X", None, 3571, "2015-06-01"),
                    ("a3", 1, "X", None, 7372, "2017-03-01"), ("a4", 2, "Y", None, None, "2016-01-01")])
    ids = pd.DataFrame({"security_id": ["s1", "s2"], "cik": [1, 2]})
    maps = {k: M.french_lookup(M.parse_french_sic(FRENCH_EXCERPT), "Other") for k in ("ff12", "ff17", "ff48")}
    out = M.classification_intervals(reg, ids, maps, version="t")
    assert list(out["sic"]) == [3571, 7372] and list(out["ff12"]) == ["BusEq", "BusEq"]
    assert out.loc[0, "effective_to"] == pd.Timestamp("2017-03-01") - pd.Timedelta(microseconds=1)
    assert pd.isna(out.loc[1, "effective_to"]) and out.loc[0, "source_accession"] == "a1"
    assert 2 not in set(out["cik"])  # a filer with no SIC gets no invented classification


# ── price windows and ticker reuse ──────────────────────────────────────────

def test_a_long_gap_in_prices_splits_the_ticker_window():
    days = list(pd.bdate_range("2013-01-01", "2013-12-31")) + list(pd.bdate_range("2016-06-01", "2016-12-31"))
    windows = M.price_windows(pd.DataFrame({"symbol": "TKR", "date": days}))
    assert len(windows["TKR"].segments) == 2
    assert windows["TKR"].segments[0][1] < date(2014, 1, 1) < windows["TKR"].segments[1][0]


def test_contiguous_prices_stay_one_window():
    days = pd.bdate_range("2013-01-01", "2016-12-31")
    assert len(M.price_windows(pd.DataFrame({"symbol": "OK", "date": days}))["OK"].segments) == 1


# ── grading ─────────────────────────────────────────────────────────────────

def span(first, last):
    return pd.Series({"first_filing": pd.Timestamp(first), "last_filing": pd.Timestamp(last), "filings": 20})


@pytest.mark.parametrize("window,filings,confirmed,expected", [
    ((date(2014, 1, 2), date(2025, 1, 2)), ("2012-03-01", "2025-03-01"), True, "A_CONFIRMED"),
    ((date(2014, 1, 2), date(2025, 1, 2)), ("2012-03-01", "2025-03-01"), False, "B_CONSISTENT"),
    ((date(2014, 1, 2), date(2025, 1, 2)), ("2012-03-01", "2019-03-01"), True, "C_PARTIAL"),          # stops filing early
    ((date(2014, 1, 2), date(2025, 1, 2)), ("2019-03-01", "2025-03-01"), True, "X_CONTRADICTED"),    # started filing years after trading
])
def test_link_grades(window, filings, confirmed, expected):
    grade, _ = M.grade_link(window, span(*filings), confirmed, date(2025, 5, 9))
    assert grade == expected


def test_no_periodic_filings_at_all_is_its_own_grade_not_a_contradiction_and_not_trusted():
    assert M.grade_link((date(2014, 1, 2), date(2020, 1, 2)), None, False, date(2025, 5, 9))[0] == "D_NO_PERIODIC_FILINGS"


def test_windows_before_the_registry_begins_cannot_be_falsified_at_their_start():
    grade, _ = M.grade_link((date(2011, 2, 1), date(2020, 1, 2)), span("2011-05-01", "2020-03-01"), False, date(2025, 5, 9))
    assert grade == "B_CONSISTENT"


# ── resolution ──────────────────────────────────────────────────────────────

def world():
    reg = registry([("a1", 100, "ACME CORP", None, 3571, "2012-03-01"), ("a2", 100, "ACME CORP", None, 3571, "2025-03-01"),
                    ("b1", 200, "OLDCO INC", None, 3571, "2012-03-01"), ("b2", 200, "OLDCO INC", None, 3571, "2019-03-01"),
                    ("c1", 300, "SAMENAME INC", None, 3571, "2012-03-01"), ("c2", 300, "SAMENAME INC", None, 3571, "2025-03-01"),
                    ("d1", 400, "SAMENAME CORP", None, 3571, "2012-03-01"), ("d2", 400, "SAMENAME CORP", None, 3571, "2025-03-01")])
    current = pd.DataFrame({"ticker": ["ACME"], "cik": [100], "exchange": ["Nasdaq"], "name": ["Acme Corp"]})
    vendor = pd.DataFrame({"symbol": ["ACME", "OLDT", "AMBI", "GONE"],
                           "security_name": ["Acme Corporation Common Stock", "OldCo, Inc. - Common Stock",
                                             "SameName Inc. Common Stock", "Nobody Ltd Common Stock"]})
    days = pd.bdate_range("2013-01-01", "2018-12-31")
    ohlcv = pd.concat([pd.DataFrame({"symbol": s, "date": days}) for s in ("ACME", "OLDT", "AMBI", "GONE")])
    return reg, current, vendor, M.price_windows(ohlcv)


def test_current_map_bootstraps_but_filings_grade_the_link():
    reg, current, vendor, windows = world()
    out = M.resolve_universe(["ACME"], current, vendor, reg, windows)
    row = out.iloc[0]
    assert row["cik"] == 100 and row["method"] == "CURRENT_TICKER_MAP" and row["grade"] == "A_CONFIRMED"


def test_a_delisted_name_resolves_only_through_exact_filing_name_evidence():
    reg, current, vendor, windows = world()
    row = M.resolve_universe(["OLDT"], current, vendor, reg, windows).iloc[0]
    assert row["cik"] == 200 and row["method"] == "EXACT_NAME_EVIDENCE"


def test_a_shared_normalised_name_is_ambiguous_and_left_unresolved():
    reg, current, vendor, windows = world()
    row = M.resolve_universe(["AMBI"], current, vendor, reg, windows).iloc[0]
    assert row["grade"] == "UNRESOLVED" and row["method"] == "AMBIGUOUS_NAME"


def test_a_name_with_no_evidence_is_unresolved_not_guessed():
    reg, current, vendor, windows = world()
    row = M.resolve_universe(["GONE"], current, vendor, reg, windows).iloc[0]
    assert row["grade"] == "UNRESOLVED" and pd.isna(row["cik"])


def test_ticker_reuse_gives_two_securities_that_never_overlap():
    reg = registry([("a1", 100, "FIRST CO", None, 3571, "2012-03-01"), ("a2", 100, "FIRST CO", None, 3571, "2015-03-01"),
                    ("b1", 200, "SECOND CO", None, 3571, "2016-09-01"), ("b2", 200, "SECOND CO", None, 3571, "2025-03-01")])
    current = pd.DataFrame({"ticker": ["REUSE"], "cik": [200], "exchange": ["NYSE"], "name": ["Second Co"]})
    vendor = pd.DataFrame({"symbol": ["REUSE"], "security_name": ["Second Co Common Stock"]})
    days = list(pd.bdate_range("2013-01-01", "2014-12-31")) + list(pd.bdate_range("2017-01-02", "2024-12-31"))
    windows = M.price_windows(pd.DataFrame({"symbol": "REUSE", "date": days}))
    out = M.resolve_universe(["REUSE"], current, vendor, reg, windows)
    assert len(out) == 2
    grades = dict(zip(out["window_from"], out["grade"]))
    assert grades[date(2013, 1, 1)] in ("C_PARTIAL", "X_CONTRADICTED")   # the early window is NOT the current holder's history
    assert grades[date(2017, 1, 2)] in ("A_CONFIRMED", "B_CONSISTENT")


def test_identity_intervals_carry_dates_from_prices_and_never_from_the_snapshot():
    reg, current, vendor, windows = world()
    resolution = M.resolve_universe(["ACME", "OLDT"], current, vendor, reg, windows)
    ids = M.identity_intervals(resolution, retrieved_at=datetime(2026, 9, 1), last_data_date=date(2026, 8, 28))
    assert (ids["effective_from"] == pd.Timestamp("2013-01-01")).all()           # first price date, not 2026-09-01
    assert ids["effective_to"].notna().all()                                      # both stop trading in 2018
    assert set(ids["source"]) <= {"PRICE_WINDOW+SEC_CURRENT_TICKER_MAP", "PRICE_WINDOW+SEC_FILING_NAME"}
    M.check_no_overlap(ids)


def test_overlapping_identities_for_one_ticker_are_rejected():
    frame = pd.DataFrame({"ticker": ["T", "T"], "cik": [1, 2], "effective_from": pd.to_datetime(["2015-01-01", "2016-01-01"]),
                          "effective_to": pd.to_datetime(["2017-01-01", None])})
    with pytest.raises(ValueError, match="two securities"):
        M.check_no_overlap(frame)


def test_multi_listing_cik_gets_distinct_class_ids():
    resolution = pd.DataFrame({"ticker": ["GOOG", "GOOGL"], "cik": [7, 7], "grade": ["B_CONSISTENT"] * 2, "method": ["X"] * 2,
                               "reason": [""] * 2, "exchange": [None] * 2, "sec_name": [None] * 2,
                               "window_from": [date(2014, 1, 2)] * 2, "window_to": [date(2026, 8, 28)] * 2})
    ids = M.identity_intervals(resolution, retrieved_at=datetime(2026, 9, 1), last_data_date=date(2026, 8, 28))
    assert ids["security_id"].nunique() == 2 and ids["effective_to"].isna().all()


# ── exits ───────────────────────────────────────────────────────────────────

def test_exit_grades_follow_the_surrounding_filings_and_never_invent_returns():
    ids = pd.DataFrame({"security_id": ["s1", "s2", "s3"], "cik": [1, 2, 3], "ticker": ["A", "B", "C"],
                        "effective_to": pd.to_datetime(["2020-06-30", "2020-06-30", "2020-06-30"])})
    evidence = {1: [{"form": "25", "kind": "EXCHANGE_DELISTING_FORM_25", "event_date": "2020-07-05", "accession": "x"}],
                2: [{"form": "15-12B", "kind": "DEREGISTRATION_FORM_15", "event_date": "2020-07-10", "accession": "y"}]}
    out = M.exit_events(ids, evidence, {"A": date(2020, 6, 30), "B": date(2020, 6, 30), "C": date(2020, 6, 30)}).set_index("ticker")
    assert out.loc["A", "quality"] == "EXACT" and out.loc["B", "quality"] == "APPROXIMATED"
    assert out.loc["C", "quality"] == "APPROXIMATED" and out.loc["C", "reason"] == "LOCAL_LAST_PRICE_DATE"
    assert set(out["return_treatment"]) == {"UNKNOWN_NO_DELISTING_RETURN_INVENTED"}


def test_exit_evidence_extracts_forms_and_8k_items():
    payload = {"filings": {"recent": {"form": ["10-K", "25", "8-K", "8-K"], "filingDate": ["2020-01-01", "2020-07-05", "2020-07-06", "2020-07-07"],
                                      "accessionNumber": ["a", "b", "c", "d"], "items": ["", "", "3.01,9.01", "5.02"]}}}
    kinds = [e["kind"] for e in M.exit_evidence(payload)]
    assert kinds == ["EXCHANGE_DELISTING_FORM_25", "8K_DELISTING_NOTICE"]


# ── names and shares ────────────────────────────────────────────────────────

def test_name_history_is_dated_from_former_names():
    payload = {"name": "META PLATFORMS INC", "formerNames": [{"name": "Facebook Inc", "from": "2012-05-01T00:00:00.000Z", "to": "2021-10-27T00:00:00.000Z"}]}
    rows = M.name_history(payload)
    assert rows[1]["name"] == "Facebook Inc" and rows[1]["name_from"] == "2012-05-01" and rows[0]["kind"] == "CURRENT"


def test_dei_shares_are_dated_by_acceptance_and_unregistered_accessions_are_dropped():
    concept = {"units": {"shares": [
        {"end": "2022-01-28", "val": 100, "accn": "K-1", "form": "10-K", "filed": "2022-02-10"},
        {"end": "2022-01-28", "val": 50, "accn": "K-1", "form": "10-K", "filed": "2022-02-10"},     # a second class in the same filing
        {"end": "2022-04-20", "val": 999, "accn": "S1-1", "form": "S-1", "filed": "2022-04-21"}]}}
    by_accession = pd.DataFrame({"accepted_at": [pd.Timestamp("2022-02-10 17:30")], "form": ["10-K"], "cik": [1]}, index=["K-1"])
    out = M.dei_share_rows(concept, by_accession)
    assert len(out) == 1 and out.iloc[0]["value"] == 150 and bool(out.iloc[0]["multi_class_summed"])
    assert out.iloc[0]["accepted_at"] == pd.Timestamp("2022-02-10 17:30")


def test_split_adjustment_uses_only_splits_after_the_report_and_before_the_decision():
    splits = pd.DataFrame({"symbol": ["A", "A", "A"], "ex_date": pd.to_datetime(["2019-01-01", "2020-06-01", "2022-01-01"]),
                           "to_factor": [2, 4, 2], "for_factor": [1, 1, 1]})
    value = M.split_adjust(100.0, splits, "A", pd.Timestamp("2019-06-01"), pd.Timestamp("2021-01-01"))
    assert value == 400.0                                        # only the 2020 4-for-1 lies in (report, decision]
    assert M.split_adjust(100.0, splits, "A", pd.Timestamp("2019-06-01"), pd.Timestamp("2019-12-31")) == 100.0
    assert M.split_adjust(100.0, splits, "B", pd.Timestamp("2019-06-01"), pd.Timestamp("2021-01-01")) == 100.0


def test_a_successor_cik_borrows_its_predecessors_early_history_only_on_exact_name_continuity():
    reg = registry([("o1", 100, "HOLDCO CORP", None, 3571, "2012-03-01"), ("o2", 100, "HOLDCO CORP", None, 3571, "2019-03-01"),
                    ("n1", 200, "HOLDCO CORP", None, 3571, "2019-06-01"), ("n2", 200, "HOLDCO CORP", None, 3571, "2025-03-01")])
    current = pd.DataFrame({"ticker": ["HLDC"], "cik": [200], "exchange": ["NYSE"], "name": ["Holdco Corp"]})
    vendor = pd.DataFrame({"symbol": ["HLDC"], "security_name": ["Holdco Corporation Common Stock"]})
    days = pd.bdate_range("2013-01-01", "2024-12-31")
    windows = M.price_windows(pd.DataFrame({"symbol": "HLDC", "date": days}))
    out = M.resolve_universe(["HLDC"], current, vendor, reg, windows).sort_values("window_from")
    assert list(out["cik"]) == [100, 200] and out.iloc[0]["method"] == "SUCCESSOR_NAME_CONTINUITY"
    assert out.iloc[0]["window_to"] < out.iloc[1]["window_from"] and set(out["grade"]) <= {"A_CONFIRMED", "B_CONSISTENT"}
    ids = M.identity_intervals(out, retrieved_at=datetime(2026, 9, 1), last_data_date=date(2025, 5, 9))
    assert ids["security_id"].nunique() == 2       # two CIKs are two securities; the ticker links them only by window
    M.check_no_overlap(ids)


def test_a_different_name_predecessor_is_not_guessed():
    reg = registry([("o1", 100, "GOOGLE ALPHA", None, 3571, "2012-03-01"), ("o2", 100, "GOOGLE ALPHA", None, 3571, "2015-03-01"),
                    ("n1", 200, "OMEGA HOLDINGS", None, 3571, "2015-06-01"), ("n2", 200, "OMEGA HOLDINGS", None, 3571, "2025-03-01")])
    current = pd.DataFrame({"ticker": ["OMG"], "cik": [200], "exchange": ["NYSE"], "name": ["Omega Holdings"]})
    vendor = pd.DataFrame({"symbol": ["OMG"], "security_name": ["Omega Holdings Common Stock"]})
    windows = M.price_windows(pd.DataFrame({"symbol": "OMG", "date": pd.bdate_range("2013-01-01", "2024-12-31")}))
    out = M.resolve_universe(["OMG"], current, vendor, reg, windows)
    assert list(out["cik"]) == [200] and out.iloc[0]["grade"] in ("C_PARTIAL", "X_CONTRADICTED")
