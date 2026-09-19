"""PIT fundamentals: TTM algebra from as-reported vintages, restatement invariance, as-of attachment."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.quant.features import pit_fundamentals as F


def fact(acc, accepted, avail, fp, form, report, name, qtrs, end, value, priority=0):
    return {"cik": 1, "accession": acc, "accepted_at": pd.Timestamp(accepted), "available_session": pd.Timestamp(avail), "fp": fp,
            "form": form, "report_period": pd.Timestamp(report), "canonical_fact": name, "tag_priority": priority, "qtrs": qtrs,
            "period_end": pd.Timestamp(end), "value": float(value), "unit": "USD"}


def filer(restate=True, drop_prior_ytd=False):
    rows = [
        fact("K19", "2020-02-20 08:00", "2020-02-20", "FY", "10-K", "2019-12-31", "revenue", 4, "2019-12-31", 400),
        fact("K19", "2020-02-20 08:00", "2020-02-20", "FY", "10-K", "2019-12-31", "assets", 0, "2019-12-31", 1000),
        fact("K19", "2020-02-20 08:00", "2020-02-20", "FY", "10-K", "2019-12-31", "net_income", 4, "2019-12-31", 40),
        fact("Q120", "2020-05-05 08:00", "2020-05-05", "Q1", "10-Q", "2020-03-31", "revenue", 1, "2020-03-31", 110),
        fact("Q120", "2020-05-05 08:00", "2020-05-05", "Q1", "10-Q", "2020-03-31", "revenue", 1, "2019-03-31", 90),
        fact("Q120", "2020-05-05 08:00", "2020-05-05", "Q1", "10-Q", "2020-03-31", "assets", 0, "2020-03-31", 1100),
        fact("Q120", "2020-05-05 08:00", "2020-05-05", "Q1", "10-Q", "2020-03-31", "net_income", 1, "2020-03-31", 12),
        fact("Q120", "2020-05-05 08:00", "2020-05-05", "Q1", "10-Q", "2020-03-31", "net_income", 1, "2019-03-31", 8),
        fact("Q220", "2020-08-05 08:00", "2020-08-05", "Q2", "10-Q", "2020-06-30", "revenue", 2, "2020-06-30", 230),
        fact("Q220", "2020-08-05 08:00", "2020-08-05", "Q2", "10-Q", "2020-06-30", "revenue", 2, "2019-06-30", 190),
        fact("Q220", "2020-08-05 08:00", "2020-08-05", "Q2", "10-Q", "2020-06-30", "assets", 0, "2020-06-30", 1200),
        fact("Q220", "2020-08-05 08:00", "2020-08-05", "Q2", "10-Q", "2020-06-30", "net_income", 2, "2020-06-30", 25),
        fact("Q220", "2020-08-05 08:00", "2020-08-05", "Q2", "10-Q", "2020-06-30", "net_income", 2, "2019-06-30", 18),
    ]
    if drop_prior_ytd:
        rows = [r for r in rows if not (r["accession"] == "Q220" and r["canonical_fact"] == "revenue" and r["period_end"] == pd.Timestamp("2019-06-30"))]
    if restate:
        rows.append(fact("Q2A20", "2020-12-01 08:00", "2020-12-01", "Q2", "10-Q/A", "2020-06-30", "revenue", 2, "2020-06-30", 220))
    return pd.DataFrame(rows)


def snap(facts=None):
    table = F.snapshots_for_filer(1, facts if facts is not None else filer())
    return table.set_index("accession")


def test_ttm_is_previous_fy_plus_ytd_minus_prior_year_ytd():
    s = snap()
    assert s.loc["K19", "revenue_ttm"] == 400                       # a 10-K's FY is its own TTM
    assert s.loc["Q220", "revenue_ttm"] == 400 + 230 - 190
    assert s.loc["Q120", "revenue_ttm"] == 400 + 110 - 90


def test_a_missing_leg_makes_the_ttm_missing_never_zero():
    s = snap(filer(restate=False, drop_prior_ytd=True))
    assert np.isnan(s.loc["Q220", "revenue_ttm"])
    assert s.loc["Q120", "revenue_ttm"] == 420                      # untouched


def test_a_later_restatement_creates_a_new_snapshot_and_never_rewrites_the_old_one():
    s = snap()
    assert s.loc["Q220", "revenue_ttm"] == 440                       # what was known on 2020-08-05
    assert s.loc["Q2A20", "revenue_ttm"] == 430                      # the restated view exists only from its own acceptance
    assert s.loc["Q2A20", "accepted_at"] > s.loc["Q220", "accepted_at"]


def test_truncating_the_facts_after_t_leaves_every_earlier_snapshot_identical():
    full = filer()
    cut = full[full["accepted_at"] <= pd.Timestamp("2020-08-05 23:59")]
    a, b = snap(full), snap(cut)
    common = b.index
    pd.testing.assert_frame_equal(a.loc[common].drop(columns=["available_session"]).reset_index(drop=True),
                                  b.loc[common].drop(columns=["available_session"]).reset_index(drop=True))


def test_balances_and_year_ago_values_come_from_vintages_available_then():
    s = snap()
    assert s.loc["Q220", "assets"] == 1200 and np.isnan(s.loc["Q220", "assets_1y"])   # no year-ago balance was reported
    assert s.loc["Q120", "assets"] == 1100


def test_discrete_quarter_and_seasonal_surprise_inputs():
    s = snap()
    assert s.loc["Q120", "net_income_q"] == 12 and s.loc["Q120", "net_income_q_1y"] == 8
    assert s.loc["Q220", "net_income_q"] == 25 - 12 and s.loc["Q220", "net_income_q_1y"] == 18 - 8


def test_non_positive_denominators_give_missing_ratios():
    frame = pd.DataFrame({"assets": [100.0, 0.0, -5.0, np.nan], "net_income_ttm": [10.0, 10.0, 10.0, 10.0]})
    ratio = F._ratio(frame["net_income_ttm"], frame["assets"])
    assert ratio.iloc[0] == 0.1 and ratio.iloc[1:].isna().all()


def test_growth_is_undefined_from_a_non_positive_base():
    assert F._growth(pd.Series([10.0, 10.0]), pd.Series([5.0, -5.0])).iloc[0] == 1.0
    assert np.isnan(F._growth(pd.Series([10.0]), pd.Series([-5.0])).iloc[0])


def test_characteristics_have_the_catalog_names_and_no_infinities():
    table = F.snapshots_for_filer(1, filer())
    out = F.snapshot_characteristics(table)
    assert tuple(out.columns) == F.CHARACTERISTIC_NAMES
    assert not np.isinf(out.to_numpy(dtype=float)).any()


def test_attach_uses_the_latest_snapshot_available_on_the_date_and_expires():
    table = F.snapshots_for_filer(1, filer())
    rows = pd.DataFrame({"date": pd.to_datetime(["2020-05-04", "2020-05-05", "2020-08-04", "2020-08-05", "2020-12-01", "2022-07-01"]),
                         "symbol": "A", "cik": [1.0] * 6})
    out = F.attach_snapshot(rows, table)
    assert out["accession"].tolist()[:5] == ["K19", "Q120", "Q120", "Q220", "Q2A20"]   # 05-05 is the day Q1 becomes usable
    assert pd.isna(out["accession"].iloc[5])                        # older than the staleness limit


def test_feature_count_is_in_the_registered_range():
    assert 30 <= len(F.CHARACTERISTIC_NAMES) <= 60 and len(set(F.CHARACTERISTIC_NAMES)) == len(F.CHARACTERISTIC_NAMES)
