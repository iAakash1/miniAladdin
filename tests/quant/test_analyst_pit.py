"""Analyst features: no future vintage may reach an earlier row.

The properties here are the ones an analyst-revision result cannot be trusted
without. Several are regression tests for defects the forensics found in the
earlier row-shift construction (irregular cadence, same-day vintages, a lone
analyst scored as zero dispersion, ticker reuse).
"""

import numpy as np
import pandas as pd
import pytest

from src.quant.features import analyst_pit as A


def vintages(symbol="AAA", start="2024-01-07", weeks=20, consensus=None, count=5, period_end="2024-12-31",
             step_days=7, period="Current Year"):
    dates = pd.to_datetime(start) + pd.to_timedelta(np.arange(weeks) * step_days, unit="D")
    values = consensus if consensus is not None else 1.0 + 0.02 * np.arange(weeks)
    return pd.DataFrame({
        "symbol": symbol, "date": dates, "period": period,
        "period_end_date": pd.Timestamp(period_end),
        "consensus": values, "high": np.asarray(values) + 0.1, "low": np.asarray(values) - 0.1,
        "count": count, "year_ago": 0.9,
    })


def features(eps, sales=None):
    return A.build_analyst_features(eps, sales)


def row(frame, date):
    return frame[frame["available_from"] == pd.Timestamp(date)].iloc[0]


# ── the arithmetic ──────────────────────────────────────────────────────────

def test_a_four_week_revision_is_a_28_calendar_day_change():
    f = features(vintages())
    r = row(f, "2024-02-04")                       # 28 days after 2024-01-07
    assert r["analyst_eps_rev_4w"] == pytest.approx((1.08 - 1.0) / 1.0)


def test_a_thirteen_week_revision_is_a_91_day_change():
    f = features(vintages(weeks=20))
    r = row(f, pd.Timestamp("2024-01-07") + pd.Timedelta(days=91))
    assert r["analyst_eps_rev_13w"] == pytest.approx((1.26 - 1.0) / 1.0)


def test_the_first_rows_have_no_revision_rather_than_a_zero():
    f = features(vintages())
    assert f.loc[f["available_from"] < "2024-02-04", "analyst_eps_rev_4w"].isna().all()


def test_acceleration_is_the_recent_revision_minus_the_earlier_one():
    consensus = np.array([1.0, 1.0, 1.0, 1.0, 1.1, 1.1, 1.1, 1.1, 1.3])
    f = features(vintages(weeks=9, consensus=consensus))
    r = row(f, pd.Timestamp("2024-01-07") + pd.Timedelta(days=56))
    assert r["analyst_eps_rev_acceleration"] == pytest.approx((1.3 - 1.1) / 1.1 - (1.1 - 1.0) / 1.0)


def test_acceleration_needs_three_consensus_points_of_the_same_period():
    f = features(vintages(weeks=9))
    assert f.loc[f["available_from"] < pd.Timestamp("2024-01-07") + pd.Timedelta(days=56),
                 "analyst_eps_rev_acceleration"].isna().all()


# ── boundaries that change meaning ──────────────────────────────────────────

def test_a_fiscal_rollover_is_not_a_revision():
    """Period A ends; from 2024-02-18 'Current Year' means period B and the consensus jumps 30%."""
    eps = pd.concat([
        vintages(weeks=6, period_end="2024-12-31", consensus=np.full(6, 2.0)),
        vintages(start="2024-02-18", weeks=6, period_end="2025-12-31", consensus=np.full(6, 2.6)),
    ], ignore_index=True)
    f = features(eps).set_index("available_from")
    # 4 weeks back from each of these still lands in period A: the +30% is a change of question.
    for date in ("2024-02-18", "2024-02-25", "2024-03-03", "2024-03-10"):
        assert np.isnan(f.loc[date, "analyst_eps_rev_4w"]), date
    # Once both ends are in period B the revision is real, and it is zero.
    assert f.loc["2024-03-17", "analyst_eps_rev_4w"] == pytest.approx(0.0)
    assert f.loc["2024-03-24", "analyst_eps_rev_4w"] == pytest.approx(0.0)


def test_a_missing_week_makes_the_revision_null_instead_of_stretching_the_lag():
    complete = vintages(weeks=10)
    gapped = complete[complete["date"] != complete["date"].iloc[4]]      # drop the week 28 days before row 8
    target = complete["date"].iloc[8]
    assert not np.isnan(row(features(complete), target)["analyst_eps_rev_4w"])
    assert np.isnan(row(features(gapped), target)["analyst_eps_rev_4w"])


def test_extra_vintages_do_not_shorten_the_lookback():
    """A row-shift construction would treat 4 vintages as 4 weeks; here time decides."""
    daily = vintages(step_days=1, weeks=60, consensus=1.0 + 0.01 * np.arange(60))
    f = features(daily)
    r = row(f, daily["date"].iloc[40])
    assert r["analyst_eps_rev_4w"] == pytest.approx((1.40 - 1.12) / 1.12)     # 28 rows back = 28 days


def test_ticker_reuse_after_a_long_gap_gives_no_revision():
    old = vintages(start="2018-01-07", weeks=8)
    new = vintages(start="2024-01-07", weeks=8, consensus=np.full(8, 5.0))
    f = features(pd.concat([old, new], ignore_index=True))
    assert f.loc[f["available_from"].between("2024-01-07", "2024-01-28"), "analyst_eps_rev_4w"].isna().all()


def test_a_near_zero_consensus_gives_null_not_a_huge_percentage():
    f = features(vintages(consensus=np.full(20, 0.01)))
    assert f["analyst_eps_rev_4w"].isna().all()


def test_dispersion_is_null_for_a_single_analyst():
    lone = features(vintages(count=1))
    pair = features(vintages(count=2))
    assert lone["analyst_eps_dispersion"].isna().all()
    assert pair["analyst_eps_dispersion"].notna().all()


def test_missing_inputs_stay_missing_and_are_not_zeroed():
    eps = vintages()
    eps.loc[5, "consensus"] = np.nan
    eps.loc[6, "count"] = np.nan
    f = features(eps)
    assert np.isnan(row(f, eps["date"].iloc[5])["analyst_eps_rev_4w"])      # its own consensus is missing
    assert np.isnan(row(f, eps["date"].iloc[9])["analyst_eps_rev_4w"])      # its 28-day-old prior is missing
    assert np.isnan(row(f, eps["date"].iloc[5])["analyst_eps_dispersion"])
    assert np.isnan(row(f, eps["date"].iloc[6])["analyst_eps_coverage"])
    assert not np.isnan(row(f, eps["date"].iloc[8])["analyst_eps_rev_4w"])  # unaffected neighbours stay computable


def test_only_the_current_year_period_is_used():
    eps = pd.concat([vintages(), vintages(period="Next Year", consensus=np.full(20, 9.0))], ignore_index=True)
    f = features(eps)
    assert len(f) == 20


# ── the leakage properties ──────────────────────────────────────────────────

def _panel(dates, symbol="AAA"):
    return pd.DataFrame({"date": pd.to_datetime(dates), "symbol": symbol})


def test_truncating_the_vintage_table_changes_no_earlier_feature():
    eps = vintages(weeks=40)
    cutoff = pd.Timestamp("2024-05-05")
    full = features(eps)
    cut = features(eps[eps["date"] <= cutoff])
    a = full[full["available_from"] <= cutoff].reset_index(drop=True)
    b = cut.reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)


def test_perturbing_future_vintages_changes_no_earlier_panel_feature():
    eps = vintages(weeks=40)
    cutoff = pd.Timestamp("2024-05-05")
    changed = eps.copy()
    future = changed["date"] > cutoff
    changed.loc[future, ["consensus", "high", "low", "count"]] = [99.0, 100.0, 98.0, 40]
    panel = _panel(pd.date_range("2024-02-01", cutoff + pd.Timedelta(days=1), freq="B"))
    original = A.attach_analyst_features(panel, features(eps))
    perturbed = A.attach_analyst_features(panel, features(changed))
    pd.testing.assert_frame_equal(original, perturbed)


def test_a_panel_row_cannot_see_a_vintage_dated_the_same_day():
    eps = vintages(weeks=10)
    f = features(eps)
    same_day = eps["date"].iloc[6]
    out = A.attach_analyst_features(_panel([same_day, same_day + pd.Timedelta(days=1)]), f)
    earlier = row(f, eps["date"].iloc[5])["analyst_eps_dispersion"]
    current = row(f, same_day)["analyst_eps_dispersion"]
    assert earlier != current                                             # the two vintages are distinguishable
    assert out.loc[0, "analyst_eps_dispersion"] == pytest.approx(earlier)   # same day: previous vintage
    assert out.loc[1, "analyst_eps_dispersion"] == pytest.approx(current)   # next day: now visible


def test_a_stale_vintage_attaches_as_null():
    f = features(vintages(weeks=6))
    late = pd.Timestamp("2024-01-07") + pd.Timedelta(days=35 + 60)
    out = A.attach_analyst_features(_panel([late]), f)
    assert out[list(A.FEATURE_NAMES)].isna().all().all()


def test_attach_aligns_by_label_not_by_position():
    eps = pd.concat([vintages("AAA", consensus=1.0 + 0.05 * np.arange(20)),
                     vintages("BBB", consensus=10.0 + 0.5 * np.arange(20))], ignore_index=True)
    f = features(eps)
    dates = pd.date_range("2024-03-01", "2024-05-15", freq="7D")
    panel = pd.concat([_panel(dates, "BBB"), _panel(dates, "AAA")], ignore_index=True)
    ordered = A.attach_analyst_features(panel, f)
    shuffled_panel = panel.sample(frac=1.0, random_state=3)
    shuffled = A.attach_analyst_features(shuffled_panel, f)
    pd.testing.assert_frame_equal(ordered.loc[shuffled.index.sort_values()].sort_index(),
                                  shuffled.sort_index())


def test_attach_does_not_mutate_its_inputs():
    eps = vintages()
    f = features(eps)
    panel = _panel(["2024-03-01"])
    before_panel, before_f = panel.copy(), f.copy()
    A.attach_analyst_features(panel, f)
    pd.testing.assert_frame_equal(panel, before_panel)
    pd.testing.assert_frame_equal(f, before_f)


def test_symbols_never_borrow_from_each_other():
    eps = vintages("AAA")
    out = A.attach_analyst_features(_panel(["2024-03-01"], "ZZZ"), features(eps))
    assert out[list(A.FEATURE_NAMES)].isna().all().all()


def test_empty_inputs_give_null_features_not_zeros():
    out = A.attach_analyst_features(_panel(["2024-03-01"]), A.build_analyst_features(None, None))
    assert out[list(A.FEATURE_NAMES)].isna().all().all()


def test_sales_revisions_are_computed_from_the_sales_table_only():
    eps = vintages(consensus=np.full(20, 1.0))
    sales = vintages(consensus=100.0 + 5.0 * np.arange(20))
    f = features(eps, sales)
    r = row(f, "2024-02-04")
    assert r["analyst_sales_rev_4w"] == pytest.approx((120.0 - 100.0) / 100.0)
    assert r["analyst_eps_rev_4w"] == pytest.approx(0.0)


# ── documentation of what is and is not reproducible ────────────────────────

def test_every_feature_has_a_reproducibility_statement_and_none_claims_exactness_against_the_literature():
    for name in A.FEATURE_NAMES:
        status = A.LITERATURE_STATUS[name]
        assert status["computational"] == "EXACT"
        assert status["literature"] in {"APPROXIMATED", "AUTHOR-DEFINED"}
    for name in ("analyst_stickiness", "recommendation_change", "target_price_revision"):
        assert A.LITERATURE_STATUS[name]["literature"] == "NOT REPRODUCIBLE"


def test_the_features_are_not_in_the_global_registry():
    from src.quant.features.registry import REGISTRY
    registered = set(REGISTRY.names())
    assert not registered & set(A.FEATURE_NAMES)


# ── the real vintage table (skipped where the licensed-data store is absent) ─

RAW = "data/research/raw/dolthub_earnings_eps_estimate/part-all.parquet"


@pytest.mark.skipif(not __import__("os").path.exists(RAW), reason="local research store not present")
def test_real_vintages_truncation_invariance_and_strict_attach():
    eps = pd.read_parquet(RAW)
    sales = pd.read_parquet(RAW.replace("eps_estimate", "sales_estimate"))
    symbols = sorted(eps["symbol"].astype(str).unique())[:150]
    eps = eps[eps["symbol"].astype(str).isin(symbols)]
    sales = sales[sales["symbol"].astype(str).isin(symbols)]
    cutoff = pd.Timestamp("2022-12-31")
    full = A.build_analyst_features(eps, sales)
    cut = A.build_analyst_features(eps[pd.to_datetime(eps["date"]) <= cutoff],
                                   sales[pd.to_datetime(sales["date"]) <= cutoff])
    before = full[full["available_from"] <= cutoff].reset_index(drop=True)
    pd.testing.assert_frame_equal(before, cut.reset_index(drop=True))

    sample = full.dropna(subset=["analyst_eps_rev_4w"]).sample(200, random_state=1)
    panel = pd.DataFrame({"symbol": sample["symbol"].to_numpy(),
                          "date": (sample["available_from"] + pd.Timedelta(days=2)).to_numpy()})
    out = A.attach_analyst_features(panel, full)
    merged = out.merge(full, left_on=["symbol", "date"], right_on=["symbol", "available_from"], how="left",
                       suffixes=("", "_same"))
    # A panel row two days after a vintage must never see a vintage dated on or after itself.
    assert (merged["available_from"].isna()).all()
