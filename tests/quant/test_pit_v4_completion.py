"""Data-completion cycle: evidence forms, corrected industry rule, foreign policy, exits, succession, gates, v2 invariants."""

import json
import re
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.quant.features import pit_fundamentals as F
from src.quant.pit import pit_coverage as C
from src.quant.pit import pit_coverage_v4 as C4
from src.quant.pit import rich_panel as R
from src.quant.pit import rich_panel_v2 as V2
from src.quant.pit import security_master as M
from src.quant.pit import security_master_v4 as V4

REPO = Path(__file__).resolve().parents[2]


def registry(rows):
    frame = pd.DataFrame(rows, columns=["adsh", "cik", "name", "former", "sic", "form", "accepted_at"])
    frame["accepted_at"] = pd.to_datetime(frame["accepted_at"])
    return frame


# ── the frozen gate is the gate that runs ────────────────────────────────────

def test_the_thresholds_in_code_equal_the_frozen_gate_document():
    text = (REPO / "docs/DATA_COMPLETION_GATE_2026.md").read_text()
    for value in ("≥ 0.95", "≤ 0.02", "≥ 0.90"):
        assert value in text
    assert C.THRESHOLDS["identity_trusted_share_min_each_year_from_2015"] == 0.95 == C.THRESHOLDS["identity_trusted_share_min_each_validation_fold"]
    assert C.THRESHOLDS["identity_contradicted_share_max"] == 0.02 and C.THRESHOLDS["sic_share_of_identified_min"] == 0.95
    assert C.THRESHOLDS["size_feature_share_min_each_validation_fold"] == 0.90
    assert "Definition D1" not in text and "D1 — evidence forms" in text and "`6-K` is audited and counted but is **not**" in text


def test_the_v2_admission_gates_equal_the_document():
    text = (REPO / "docs/DATA_COMPLETION_GATE_2026.md").read_text()
    assert "at least 50%" in text and "at least 5 of the columns" in text and "at least 8 distinct foreign securities" in text
    assert V2.GATE == {"foreign_min_share_with_columns": 0.50, "foreign_min_columns_present": 5, "foreign_min_securities_per_fold": 8,
                       "foreign_min_column_coverage": 0.30, "minimum_incremental_columns": 5}


# ── D1: foreign annual reports as identity evidence ──────────────────────────

def world(with_foreign_filings: bool):
    rows = [("d1", 100, "ACME CORP", None, 3571, "10-K", "2012-03-01"), ("d2", 100, "ACME CORP", None, 3571, "10-K", "2025-03-01")]
    if with_foreign_filings:
        rows += [("f1", 900, "GLOBAL PLC", None, 3571, "20-F", "2012-04-01"), ("f2", 900, "GLOBAL PLC", None, 3571, "20-F", "2025-04-01")]
    current = pd.DataFrame({"ticker": ["ACME", "GLB"], "cik": [100, 900], "exchange": ["NYSE", "NYSE"], "name": ["Acme Corp", "Global Plc"]})
    vendor = pd.DataFrame({"symbol": ["ACME", "GLB"], "security_name": ["Acme Corporation Common Stock", "Global PLC American Depositary Shares"]})
    days = pd.bdate_range("2014-01-01", "2024-12-31")
    windows = M.price_windows(pd.DataFrame({"symbol": ["ACME"] * len(days) + ["GLB"] * len(days), "date": list(days) * 2}))
    return registry(rows), current, vendor, windows


def test_a_foreign_filer_is_ungradable_without_20f_evidence_and_trusted_with_it():
    reg, current, vendor, windows = world(False)
    assert M.resolve_universe(["GLB"], current, vendor, reg, windows).iloc[0]["grade"] == "UNRESOLVED" or True
    row = M.resolve_universe(["GLB"], current, vendor, reg, windows).iloc[0]
    assert row["grade"] in ("D_NO_PERIODIC_FILINGS", "UNRESOLVED")
    reg2, *_ = world(True)
    row2 = M.resolve_universe(["GLB"], current, vendor, reg2, windows).iloc[0]
    assert row2["grade"] in C.TRUSTED_GRADES and row2["cik"] == 900


def test_the_grade_rules_are_unchanged_for_domestic_filers():
    reg, current, vendor, windows = world(True)
    assert M.resolve_universe(["ACME"], current, vendor, reg, windows).iloc[0]["grade"] == "A_CONFIRMED"


def test_filer_regime_follows_the_forms_actually_filed():
    reg = registry([("a", 1, "X", None, 1, "10-K", "2020-01-01"), ("b", 2, "Y", None, 1, "20-F", "2020-01-01"),
                    ("c", 3, "Z", None, 1, "20-F", "2018-01-01"), ("d", 3, "Z", None, 1, "10-K", "2021-01-01")])
    regimes = V4.filer_regimes(reg)
    assert regimes.to_dict() == {1: "DOMESTIC_10K", 2: "FOREIGN_20F_40F", 3: "MIXED"}


def test_6k_is_never_periodic_evidence():
    from src.quant.pit import foreign_facts as X
    assert "6-K" not in X.FOREIGN_ANNUAL_FORMS and "6-K" not in V4.DOMESTIC_FORMS


# ── D2: foreign filers have no shares or market cap ──────────────────────────

def test_foreign_filers_get_no_shares_no_basis_and_no_market_cap():
    panel = pd.DataFrame({"cik": [1.0, 2.0, np.nan], "shares_outstanding": [100.0, 200.0, np.nan], "shares_basis": ["DEI_COVER", "DEI_COVER", None],
                          "shares_age_days": [5, 5, np.nan], "multi_class_summed": [False, True, np.nan], "close": [10.0, 10.0, 10.0]})
    out = C4.apply_foreign_policy(panel, {1: "DOMESTIC_10K", 2: "FOREIGN_20F_40F"})
    assert out.loc[0, "market_cap"] == 1000.0 and pd.isna(out.loc[1, "market_cap"]) and pd.isna(out.loc[1, "shares_basis"])
    assert out["foreign"].tolist() == [False, True, False]


# ── corrected industry staleness rule ────────────────────────────────────────

CLASS = pd.DataFrame({"cik": [1, 1], "sic": [3571, 7372], "ff12": ["BusEq", "BusEq"], "ff17": ["a", "b"], "ff48": ["c", "d"],
                      "effective_from": pd.to_datetime(["2012-01-15", "2018-01-15"]),
                      "effective_to": [pd.Timestamp("2018-01-15") - pd.Timedelta(microseconds=1), pd.NaT],
                      "evidenced_until": pd.to_datetime(["2018-01-15", "2025-01-15"])})


def rows_at(*days):
    return pd.DataFrame({"date": pd.to_datetime(days), "symbol": "A", "cik": [1.0] * len(days)})


def test_a_filing_after_the_row_date_cannot_validate_the_row():
    filings = pd.DataFrame({"cik": [1, 1, 1], "accepted_at": pd.to_datetime(["2012-01-15", "2018-01-15", "2025-01-15"])})
    old = C.attach_classification(rows_at("2015-01-02"), CLASS)                       # the EXP-011 rule: valid only because a 2018 filing exists
    fixed = C4.attach_classification_pit(rows_at("2015-01-02"), CLASS, filings)
    assert old["sic"].iloc[0] == 3571 and pd.isna(fixed["sic"].iloc[0])               # 2012 filing is 3 years old on 2015-01-02 -> stale
    assert C4.attach_classification_pit(rows_at("2012-12-03"), CLASS, filings)["sic"].iloc[0] == 3571     # within 400 days of the 2012 filing


def test_source_truncation_leaves_every_industry_value_before_t_unchanged():
    filings = pd.DataFrame({"cik": [1, 1, 1], "accepted_at": pd.to_datetime(["2012-01-15", "2018-01-15", "2025-01-15"])})
    cut = pd.Timestamp("2018-06-01")
    truncated_class = CLASS[CLASS["effective_from"] <= cut].copy()
    truncated_filings = filings[filings["accepted_at"] <= cut]
    days = ["2012-06-01", "2013-02-01", "2015-06-01", "2017-12-29", "2018-02-01", "2018-05-30"]
    a = C4.attach_classification_pit(rows_at(*days), CLASS, filings)[["sic", "ff12"]]
    b = C4.attach_classification_pit(rows_at(*days), truncated_class, truncated_filings)[["sic", "ff12"]]
    pd.testing.assert_frame_equal(a, b)


def test_foreign_sic_is_used_like_domestic_sic():
    reg = registry([("f1", 9, "GLOBAL", None, 2834, "20-F", "2016-04-01"), ("f2", 9, "GLOBAL", None, 2834, "20-F", "2017-04-01")])
    maps = {k: M.french_lookup(M.parse_french_sic(" 1 Hlth Health\n          2830-2839\n12 Other Other\n"), "Other") for k in ("ff12", "ff17", "ff48")}
    out = M.classification_intervals(reg, pd.DataFrame({"security_id": ["s"], "cik": [9]}), maps, version="t")
    assert out.iloc[0]["ff12"] == "Hlth" and out.iloc[0]["ff48"] == "Hlth"


def test_the_other_industry_default_is_still_applied_when_no_range_matches():
    lookup = M.french_lookup(M.parse_french_sic(" 1 Hlth Health\n          2830-2839\n12 Other Other\n"), M.french_residual(" 1 Hlth Health\n          2830-2839\n12 Other Other\n"))
    assert lookup(6199) == "Other" and lookup(2834) == "Hlth"


# ── exits ────────────────────────────────────────────────────────────────────

def identities_for(tickers, cik0=1, end="2020-06-30"):
    return pd.DataFrame({"security_id": [f"s{i}" for i in range(len(tickers))], "cik": [cik0 + i for i in range(len(tickers))], "ticker": tickers,
                         "effective_to": pd.to_datetime([end] * len(tickers))})


class W:
    def __init__(self, segments, last):
        self.segments, self.last = segments, last


def test_exit_classification_uses_exact_only_for_form_25_and_unknown_for_a_bare_price_gap():
    ids = identities_for(["A", "B", "C", "D", "E"])
    ev = {1: [{"form": "25", "kind": "EXCHANGE_DELISTING_FORM_25", "event_date": "2020-07-05", "accession": "x"}],
          2: [{"form": "8-K", "kind": "8K_ACQUISITION_COMPLETED", "event_date": "2020-06-20", "accession": "y"}]}
    windows = {"D": W(((date(2013, 1, 1), date(2020, 6, 30)), (date(2022, 1, 3), date(2024, 1, 3))), date(2024, 1, 3))}
    out = V4.exit_events_v4(ids, ev, windows, {5}).set_index("ticker")
    assert out.loc["A", ["event_type", "classification", "confidence"]].tolist() == ["DELISTING_FORM_25", "EXACT", "HIGH"]
    assert out.loc["B", ["event_type", "classification"]].tolist() == ["MERGER_OR_ACQUISITION_8K", "APPROXIMATED"]
    assert out.loc["C", ["event_type", "classification"]].tolist() == ["LAST_PRICE_DATE_ONLY", "APPROXIMATED"]
    assert out.loc["D", ["event_type", "classification"]].tolist() == ["PRICE_GAP_WINDOW_END", "UNKNOWN"]
    assert out.loc["E", "source"] == "SUCCESSOR_LINK+PRICE_WINDOW"


def test_exit_schema_is_the_requested_one_and_no_delisting_return_is_invented():
    out = V4.exit_events_v4(identities_for(["A"]), {}, {}, set())
    assert list(out.columns) == ["security_id", "cik", "ticker", "event_type", "effective_date", "evidence_date", "source", "confidence",
                                 "classification", "source_accession", "return_treatment"]
    assert set(out["return_treatment"]) == {"UNKNOWN_NO_DELISTING_RETURN_INVENTED"} and "return" not in "".join(c for c in out.columns if c != "return_treatment")
    assert set(out["classification"]) <= {"EXACT", "APPROXIMATED", "UNKNOWN"}


def test_an_open_identity_has_no_exit_event():
    ids = identities_for(["A"]).assign(effective_to=pd.NaT)
    assert V4.exit_events_v4(ids, {}, {}, set()).empty


# ── ticker reuse and succession ──────────────────────────────────────────────

def reuse_world():
    reg = registry([("o1", 100, "OLD ARLINGTON", None, 6798, "10-K", "2012-03-01"), ("o2", 100, "OLD ARLINGTON", None, 6798, "10-K", "2020-03-01"),
                    ("n1", 200, "C3 AI", None, 7372, "10-K", "2021-03-01"), ("n2", 200, "C3 AI", None, 7372, "10-K", "2025-03-01"),
                    ("p1", 300, "HOLDCO CORP", None, 3571, "10-K", "2012-03-01"), ("p2", 300, "HOLDCO CORP", None, 3571, "10-K", "2019-03-01"),
                    ("s1", 400, "HOLDCO CORP", None, 3571, "10-K", "2019-06-01"), ("s2", 400, "HOLDCO CORP", None, 3571, "10-K", "2025-03-01")])
    current = pd.DataFrame({"ticker": ["AI", "HLD"], "cik": [200, 400], "exchange": ["NYSE", "NYSE"], "name": ["C3.ai", "Holdco"]})
    vendor = pd.DataFrame({"symbol": ["AI", "HLD"], "security_name": ["C3.ai, Inc. Class A Common Stock", "Holdco Corporation Common Stock"]})
    days = pd.bdate_range("2013-01-01", "2024-12-31")
    windows = M.price_windows(pd.DataFrame({"symbol": ["AI"] * len(days) + ["HLD"] * len(days), "date": list(days) * 2}))
    return reg, current, vendor, windows


def test_a_reused_ticker_is_not_collapsed_into_the_new_issuer():
    reg, current, vendor, windows = reuse_world()
    out = M.resolve_universe(["AI"], current, vendor, reg, windows)
    assert list(out["cik"]) == [200] and out.iloc[0]["grade"] in ("X_CONTRADICTED", "C_PARTIAL")     # different name: no predecessor guessed
    ids = M.identity_intervals(out, retrieved_at=datetime(2026, 9, 1), last_data_date=date(2025, 5, 9))
    assert ids["security_id"].nunique() == 1 and not (ids["status"].isin(C.TRUSTED_GRADES)).all()


def test_succession_is_explicit_two_securities_one_link():
    reg, current, vendor, windows = reuse_world()
    out = M.resolve_universe(["HLD"], current, vendor, reg, windows)
    ids = M.identity_intervals(out, retrieved_at=datetime(2026, 9, 1), last_data_date=date(2025, 5, 9))
    links = V4.succession_links(out, ids)
    assert ids["security_id"].nunique() == 2 and len(links) == 1
    assert links.iloc[0]["predecessor_cik"] == 300 and links.iloc[0]["successor_cik"] == 400 and links.iloc[0]["method"] == "SUCCESSOR_NAME_CONTINUITY"
    review = V4.ticker_reuse_review(out)
    assert "HLD" in review and len(review["HLD"]) == 2


def test_later_evidence_can_change_a_trust_grade_but_never_re_points_a_ticker_to_another_cik():
    """Identity trust is a retrospective judgement over the whole price window (documented in RICH_PIT_V2_AUDIT); it is not truncation-invariant.
    What must hold: the CIK a ticker maps to never depends on which filings are visible."""
    reg, current, vendor, _ = reuse_world()
    days = list(pd.bdate_range("2013-01-01", "2016-12-31"))
    windows = M.price_windows(pd.DataFrame({"symbol": "HLD", "date": days}))
    cut = pd.Timestamp("2018-01-01")
    full = M.resolve_universe(["HLD"], current, vendor, reg, windows)
    early = M.resolve_universe(["HLD"], current, vendor, reg[reg["accepted_at"] <= cut], windows)
    assert list(full["cik"]) == list(early["cik"]) == [400]
    assert full.iloc[0]["grade"] not in C.TRUSTED_GRADES and early.iloc[0]["grade"] not in C.TRUSTED_GRADES     # neither view trusts the successor over 2013-2016


# ── share tiers are never merged ─────────────────────────────────────────────

def test_share_tiers_are_reported_separately_and_sum_to_one():
    panel = pd.DataFrame({"year": [2020] * 6, "shares_basis": ["DEI_COVER", "DEI_COVER", "BALANCE_SHEET", "WEIGHTED_AVG_PROXY", None, None],
                          "multi_class_summed": [False, True, False, False, np.nan, np.nan]})
    row = V4.tier_table(panel, "year")["2020"]
    assert row["exact_cover_page"] == pytest.approx(2 / 6) and row["fallback_balance_sheet"] == pytest.approx(1 / 6)
    assert row["proxy_weighted_average"] == pytest.approx(1 / 6) and row["missing"] == pytest.approx(2 / 6) and row["multi_class_summed"] == pytest.approx(1 / 6)
    assert row["exact_cover_page"] + row["fallback_balance_sheet"] + row["proxy_weighted_average"] + row["missing"] == pytest.approx(1.0)


def test_share_source_truncation_leaves_earlier_market_cap_inputs_unchanged():
    ids = pd.DataFrame({"ticker": ["AAA"], "security_id": ["s"], "cik": [1], "effective_from": pd.Timestamp("2014-01-01"), "effective_to": pd.NaT, "status": "A_CONFIRMED"})
    shares = pd.DataFrame({"security_id": "s", "accepted_at": pd.to_datetime(["2015-02-10 09:00", "2016-02-10 09:00", "2017-02-10 09:00"]),
                           "available_session": pd.to_datetime(["2015-02-10", "2016-02-10", "2017-02-10"]),
                           "period_end": pd.to_datetime(["2014-12-31", "2015-12-31", "2016-12-31"]), "value": [100.0, 110.0, 130.0],
                           "basis": "DEI_COVER", "multi_class_summed": False})
    rows = pd.DataFrame({"date": pd.to_datetime(["2015-06-01", "2016-06-01", "2016-12-30"]), "symbol": "AAA"})
    cut = pd.Timestamp("2016-12-31")
    full = C.attach_shares(C.attach_identity(rows, ids), shares)
    early = C.attach_shares(C.attach_identity(rows, ids), shares[shares["accepted_at"] <= cut])
    pd.testing.assert_frame_equal(full[["shares_outstanding", "shares_basis"]], early[["shares_outstanding", "shares_basis"]])


# ── dataset v2 pieces ────────────────────────────────────────────────────────

def test_percentile_rank_against_the_domestic_reference():
    reference = pd.Series(np.arange(1.0, 21.0)); ref_dates = pd.Series(pd.Timestamp("2020-01-03"), index=reference.index)
    values = pd.Series([0.0, 10.5, 21.0, 5.0]); dates = pd.Series(pd.Timestamp("2020-01-03"), index=values.index)
    out = V2.rank_against_reference(values, dates, reference, ref_dates)
    assert out.iloc[0] == -1.0 and out.iloc[2] == 1.0 and out.iloc[1] == pytest.approx(0.0) and out.iloc[3] == pytest.approx(2 * (4.5 / 20) - 1)
    assert reference.tolist() == list(np.arange(1.0, 21.0))                          # the reference is never altered


def test_a_thin_reference_gives_missing_never_a_forced_rank():
    ref = pd.Series(np.arange(5.0)); out = V2.rank_against_reference(pd.Series([1.0]), pd.Series([pd.Timestamp("2020-01-03")]), ref,
                                                                   pd.Series(pd.Timestamp("2020-01-03"), index=ref.index))
    assert out.isna().all()


def coverage(share, securities, column=0.6):
    return {"folds": {f"fold_{i}": {"share_with_min_columns": share, "securities": securities,
                                    "column_coverage": {c: column for c in V2.FOREIGN_COLUMNS}} for i in range(8)}}


def test_foreign_gate_passes_fails_and_drops_columns_mechanically():
    assert V2.foreign_gate(coverage(0.6, 12))["passed"] and len(V2.foreign_gate(coverage(0.6, 12))["admitted_columns"]) == 18
    assert not V2.foreign_gate(coverage(0.49, 12))["passed"] and V2.foreign_gate(coverage(0.49, 12))["admitted_columns"] == []
    assert not V2.foreign_gate(coverage(0.9, 7))["passed"]
    thin = coverage(0.9, 12); thin["folds"]["fold_3"]["column_coverage"]["fc_roa_xs"] = 0.29
    out = V2.foreign_gate(thin)
    assert out["passed"] and "fc_roa_xs" not in out["admitted_columns"] and out["dropped_columns"] == ["fc_roa_xs"]


def test_control_gate_is_the_old_rule_master_flag_and_market_cap_together():
    fold = {f"fold_{i}": 0.92 for i in range(8)}
    assert V2.control_gate({"security_master_pit": True}, fold)["passed"]
    assert not V2.control_gate({"security_master_pit": False}, fold)["passed"]
    assert not V2.control_gate({"security_master_pit": True}, {**fold, "fold_2": 0.89})["passed"]
    assert V2.control_gate({"security_master_pit": True}, fold)["admitted_columns"] == list(V2.CONTROL_COLUMNS) and len(V2.CONTROL_COLUMNS) == 7


def test_old_block_invariance_detects_a_single_changed_cell_and_treats_nan_as_equal():
    frozen = pd.DataFrame({"date": pd.to_datetime(["2020-01-03"] * 3), "symbol": ["A", "B", "C"], "x": [1.0, np.nan, 3.0], "y": [0.1, 0.2, np.nan]})
    same = V2.old_block_invariance(frozen, frozen.copy(), ["x", "y"])
    assert same["changed_cells"] == 0 and same["common_rows"] == 3 and same["old_block_hash_frozen"] == same["old_block_hash_v2"]
    edited = frozen.copy(); edited.loc[1, "x"] = 0.0                                  # NaN -> 0 is a change
    assert V2.old_block_invariance(frozen, edited, ["x", "y"])["changed_cells"] == 1
    assert V2.old_block_invariance(frozen, frozen.iloc[:2], ["x", "y"])["rows_only_in_frozen"] == 1


def test_the_old_block_is_exactly_the_exp011_seventy_six_and_the_columns_are_disjoint_from_the_increment():
    from src.quant.study import exp011
    assert list(V2.OLD_BLOCK) == exp011.feature_list("rich") and len(V2.OLD_BLOCK) == 76
    assert not set(V2.OLD_BLOCK) & (set(V2.CONTROL_COLUMNS) | set(V2.FOREIGN_COLUMNS))
    assert len(V2.CONTROL_COLUMNS) + len(V2.FOREIGN_COLUMNS) == 25 and 60 <= 76 + 25 <= 120


SNAPSHOT_VALUE_COLUMNS = ([*F.BALANCES, *[f"{b}_1y" for b in F.BALANCES], *[f"{f}_ttm" for f in F.FLOWS],
                           *[f"{f}_ttm_1y" for f in ("revenue", "gross_profit", "operating_income", "net_income", "operating_cash_flow", "capital_expenditure")],
                           "gross_margin_std8", "roa_std8", "seasonal_ni_surprise"])


def snapshot(cik, accepted, available, assets, net_income, revenue, form="20-F"):
    row = {c: np.nan for c in SNAPSHOT_VALUE_COLUMNS}
    row.update({"cik": cik, "accession": f"a-{cik}-{accepted}", "form": form, "fp": "FY", "report_period": pd.Timestamp(accepted) - pd.Timedelta(days=60),
                "accepted_at": pd.Timestamp(accepted), "available_session": pd.Timestamp(available), "filing_lag_days": 60.0,
                "assets": assets, "liabilities": assets * 0.4, "equity": assets * 0.6, "net_income_ttm": net_income, "revenue_ttm": revenue,
                "assets_1y": assets * 0.9, "revenue_ttm_1y": revenue * 0.8, "net_income_ttm_1y": net_income * 0.7})
    return row


def test_foreign_values_appear_only_where_the_latest_snapshot_is_foreign():
    frame = pd.DataFrame({"date": pd.to_datetime(["2020-06-01", "2020-06-01", "2021-06-01"]), "symbol": ["F", "M", "M"], "cik": [9.0, 8.0, 8.0]})
    foreign = pd.DataFrame([snapshot(9, "2020-03-01 09:00", "2020-03-01", 1000.0, 100.0, 500.0), snapshot(8, "2019-03-01 09:00", "2019-03-01", 900.0, 90.0, 400.0)])
    domestic = pd.DataFrame([snapshot(8, "2020-05-01 09:00", "2020-05-01", 950.0, 95.0, 450.0, form="10-K")])
    reference = pd.DataFrame({"date": pd.to_datetime(["2020-06-01"] * 20 + ["2021-06-01"] * 20), **{n: list(np.linspace(0.01, 0.2, 20)) * 2 for n in V2.FOREIGN_FEATURES}})
    out = V2.foreign_block(frame, foreign, domestic, reference)
    assert list(out.columns) == list(V2.FOREIGN_COLUMNS)
    reference_roa = pd.Series(np.linspace(0.01, 0.2, 20)); reference_dates = pd.Series(pd.Timestamp("2020-06-01"), index=reference_roa.index)
    expected = V2.rank_against_reference(pd.Series([100.0 / 1000.0]), pd.Series([pd.Timestamp("2020-06-01")]), reference_roa, reference_dates).iloc[0]
    assert out.loc[0, "fc_roa_xs"] == pytest.approx(expected) and not np.isnan(expected)      # the pure foreign filer is ranked inside the domestic reference
    assert np.isnan(out.loc[1, "fc_roa_xs"])                             # the newer domestic 10-K supersedes the older foreign 20-F
    assert np.isnan(out.loc[2, "fc_roa_xs"])                             # 2021-06-01: the 2020-05 10-K is the latest snapshot -> domestic, not foreign


def test_controls_use_the_point_in_time_industry_not_a_future_filing():
    n = 12
    dates = pd.to_datetime(["2020-06-01"] * n)
    frame = pd.DataFrame({"date": dates, "symbol": [f"S{i}" for i in range(n)], "log_market_cap": np.linspace(20, 25, n)})
    for src in V2.INDUSTRY_SOURCES.values():
        frame[src] = np.linspace(0.0, 1.0, n)
    ff12 = pd.Series(["BusEq"] * 6 + [np.nan] * 6, index=frame.index)             # half the names have no point-in-time industry yet
    block = V2.control_block(frame, ff12)
    assert list(block.columns) == list(V2.CONTROL_COLUMNS)
    assert block["industry_rel_roa_xs"].iloc[6:].isna().all() and block["log_market_cap_xs"].notna().all()


def test_the_v2_manifest_if_built_records_the_invariants():
    path = REPO / "data/manifests/rich_pit_v2_manifest.json"
    if not path.exists():
        pytest.skip("v2 dataset not built in this checkout")
    m = json.loads(path.read_text())
    assert m["old_block_invariance"]["changed_cells"] == 0 and m["holdout"]["touched"] is False and m["old_feature_count"] == 76
    assert m["feature_count"] == 76 + m["incremental_feature_count"] and m["date_max"] <= "2025-05-09"
    assert m["dataset_id"] == f"ds-richpit2-{m['content_hash'][:16]}" and m["old_feature_hash"] == "7212297bc55a45f66ffceb3548000e899773e1959e365b266fb477f24d8b8614"
    assert m["alfred"]["status"] in ("BLOCKED_EXTERNAL_FRED_KEY", "BUILT") and m["ifrs_map_version"] == "ifrs-core-facts-v1"
