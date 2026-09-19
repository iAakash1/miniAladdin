"""As-of attachment of identity / industry / shares and the coverage gate."""

import numpy as np
import pandas as pd
import pytest

from src.quant.pit import pit_coverage as C


def rows(*pairs):
    return pd.DataFrame({"date": pd.to_datetime([p[0] for p in pairs]), "symbol": [p[1] for p in pairs]})


IDS = pd.DataFrame({
    "ticker": ["AAA", "BBB", "CCC"], "security_id": ["s-a", "s-b", "s-c"], "cik": [1, 2, 3],
    "effective_from": pd.to_datetime(["2014-01-01"] * 3), "effective_to": pd.to_datetime([None, "2016-12-31", None]),
    "status": ["A_CONFIRMED", "B_CONSISTENT", "X_CONTRADICTED"]})


def test_identity_is_attached_only_inside_the_dated_window_and_only_if_trusted():
    out = C.attach_identity(rows(("2015-06-01", "AAA"), ("2013-06-01", "AAA"), ("2017-06-01", "BBB"), ("2015-06-01", "CCC"), ("2015-06-01", "ZZZ")), IDS)
    assert out["security_id"].tolist()[0] == "s-a" and pd.isna(out["security_id"].iloc[1])
    assert pd.isna(out["security_id"].iloc[2])                       # after BBB's window ended
    assert pd.isna(out["security_id"].iloc[3]) and out["identity_grade"].iloc[3] == "X_CONTRADICTED"   # graded but not trusted
    assert pd.isna(out["security_id"].iloc[4])


CLASS = pd.DataFrame({
    "cik": [1, 1], "sic": [3571, 7372], "ff12": ["BusEq", "BusEq"], "ff17": ["Machn", "Other"], "ff48": ["Mach", "Softw"],
    "effective_from": pd.to_datetime(["2012-01-01", "2018-01-01"]),
    "effective_to": [pd.Timestamp("2018-01-01") - pd.Timedelta(microseconds=1), pd.NaT],
    "evidenced_until": pd.to_datetime(["2025-03-01", "2025-03-01"])})


def test_industry_is_the_one_in_force_and_expires_without_evidence():
    base = C.attach_identity(rows(("2015-06-01", "AAA"), ("2019-06-01", "AAA"), ("2026-06-01", "AAA")), IDS)
    out = C.attach_classification(base, CLASS)
    assert out["sic"].iloc[0] == 3571 and out["sic"].iloc[1] == 7372
    assert pd.isna(out["sic"].iloc[2])                              # > 400 days past the last filing that evidences it


SHARES = pd.DataFrame({
    "security_id": ["s-a"] * 3, "accepted_at": pd.to_datetime(["2015-02-10 17:30", "2015-05-01 09:00", "2015-05-01 09:00"]),
    "available_session": pd.to_datetime(["2015-02-11", "2015-05-01", "2015-05-01"]),
    "period_end": pd.to_datetime(["2015-02-01", "2015-03-31", "2015-04-25"]),
    "value": [100.0, 110.0, 111.0], "basis": ["DEI_COVER", "BALANCE_SHEET", "DEI_COVER"], "multi_class_summed": [False] * 3})


def test_shares_are_used_only_from_their_availability_session_and_prefer_cover_page_on_ties():
    base = C.attach_identity(rows(("2015-02-10", "AAA"), ("2015-02-11", "AAA"), ("2015-05-01", "AAA")), IDS)
    out = C.attach_shares(base, SHARES)
    assert pd.isna(out["shares_outstanding"].iloc[0])               # the day before it was usable
    assert out["shares_outstanding"].iloc[1] == 100.0
    assert out["shares_outstanding"].iloc[2] == 111.0 and out["shares_basis"].iloc[2] == "DEI_COVER"


def test_a_stale_share_count_is_missing_not_carried_forever():
    base = C.attach_identity(rows(("2017-06-01", "AAA")), IDS)
    assert pd.isna(C.attach_shares(base, SHARES)["shares_outstanding"].iloc[0])


def test_shares_are_split_adjusted_by_splits_after_acceptance_only():
    splits = pd.DataFrame({"symbol": ["AAA", "AAA"], "date": ["2015-01-01", "2015-03-15"], "to_factor": [3.0, 2.0], "for_factor": [1.0, 1.0]})
    table = C.split_factor_table(splits)
    base = C.attach_identity(rows(("2015-03-01", "AAA"), ("2015-04-01", "AAA")), IDS)
    out = C.attach_shares(base, SHARES.iloc[:1], table)
    assert out["shares_outstanding"].iloc[0] == 100.0               # 2015-01 split predates acceptance: already reflected
    assert out["shares_outstanding"].iloc[1] == 200.0               # the 2015-03-15 2-for-1 is applied


def test_period_labels_and_the_master_gate():
    folds = [{"index": 0, "validation_start": "2017-05-05", "validation_end": "2018-05-04"}]
    labels = C.label_periods(pd.Series(pd.to_datetime(["2016-01-04", "2017-06-01", "2019-01-01"])), folds)
    assert labels.tolist() == ["train_only", "fold_0", "between"]
    good = {"by_year": {"2016": {"identity_trusted": 0.97}}, "by_period": {"fold_0": {
        "identity_trusted": 0.97, "identity_contradicted": 0.0, "sic_of_identified": 0.99, "market_cap_of_identified": 0.95}}}
    assert C.security_master_status(good)["security_master_pit"] is True
    bad = {"by_year": {"2016": {"identity_trusted": 0.80}}, "by_period": good["by_period"]}
    status = C.security_master_status(bad)
    assert status["security_master_pit"] is False and status["neutralization_allowed"] is False and status["failures"]


def test_the_weighted_average_proxy_is_used_only_where_no_primary_count_exists():
    proxy = pd.DataFrame({"security_id": ["s-a", "s-a"], "accepted_at": pd.to_datetime(["2015-03-01 09:00", "2016-01-15 09:00"]),
                          "available_session": pd.to_datetime(["2015-03-01", "2016-01-15"]), "period_end": pd.to_datetime(["2014-12-31", "2015-12-31"]),
                          "value": [90.0, 95.0], "basis": "WEIGHTED_AVG_PROXY", "multi_class_summed": False})
    combined = pd.concat([SHARES, proxy], ignore_index=True)
    base = C.attach_identity(rows(("2015-06-01", "AAA"), ("2016-02-01", "AAA")), IDS)
    out = C.attach_shares(base, combined)
    assert out["shares_outstanding"].iloc[0] == 111.0 and out["shares_basis"].iloc[0] == "DEI_COVER"   # primary wins although a proxy exists
    # by 2016-02-01 the primary count (2015-05-01) is 276 days old, still inside the window -> primary again
    assert out["shares_basis"].iloc[1] == "DEI_COVER"
    only_proxy = C.attach_shares(C.attach_identity(rows(("2016-02-01", "AAA")), IDS), proxy)
    assert only_proxy["shares_outstanding"].iloc[0] == 95.0 and only_proxy["shares_basis"].iloc[0] == "WEIGHTED_AVG_PROXY"


def test_the_proxy_never_fills_beyond_the_staleness_window():
    proxy = pd.DataFrame({"security_id": ["s-a"], "accepted_at": pd.to_datetime(["2015-03-01 09:00"]), "available_session": pd.to_datetime(["2015-03-01"]),
                          "period_end": pd.to_datetime(["2014-12-31"]), "value": [90.0], "basis": "WEIGHTED_AVG_PROXY", "multi_class_summed": False})
    out = C.attach_shares(C.attach_identity(rows(("2017-01-02", "AAA")), IDS), proxy)
    assert pd.isna(out["shares_outstanding"].iloc[0])
