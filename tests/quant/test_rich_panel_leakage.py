"""Leakage tests for the rich PIT panel, run on a synthetic world that can be truncated and perturbed."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.quant.features import pit_fundamentals as F
from src.quant.pit import pit_coverage as C
from src.quant.pit import rich_panel as R

N = 12
FLOW = ("revenue", "gross_profit", "operating_income", "net_income", "operating_cash_flow", "capital_expenditure", "depreciation_amortization", "cost_of_revenue")
BAL = ("assets", "current_assets", "liabilities", "current_liabilities", "equity", "cash", "inventory", "accounts_receivable", "long_term_debt", "short_term_debt")


def facts_for(cik, rng):
    rows = []
    scale = 100 * (1 + cik)
    quarterly = {}      # (year, q) -> dict fact -> discrete value
    for year in (2017, 2018, 2019):
        for q in (1, 2, 3, 4):
            base = scale * (1 + 0.03 * ((year - 2017) * 4 + q)) * rng.uniform(0.9, 1.1)
            quarterly[(year, q)] = {"revenue": base, "gross_profit": 0.4 * base, "operating_income": 0.15 * base, "net_income": 0.1 * base,
                                    "operating_cash_flow": 0.12 * base, "capital_expenditure": 0.05 * base,
                                    "depreciation_amortization": 0.03 * base, "cost_of_revenue": 0.6 * base}

    def ytd(year, q, fact):
        return sum(quarterly[(year, k)][fact] for k in range(1, q + 1))

    reports = [(2017, 4), (2018, 1), (2018, 2), (2018, 3), (2018, 4), (2019, 1), (2019, 2), (2019, 3)]
    for year, q in reports:
        end = {1: f"{year}-03-31", 2: f"{year}-06-30", 3: f"{year}-09-30", 4: f"{year}-12-31"}[q]
        accepted = {1: f"{year}-05-06", 2: f"{year}-08-06", 3: f"{year}-11-05", 4: f"{year + 1}-03-01"}[q] + " 08:00"
        acc = f"{cik}-{year}-{q}"
        fp = "FY" if q == 4 else f"Q{q}"
        form = "10-K" if q == 4 else "10-Q"
        avail = pd.Timestamp(accepted).normalize()
        current_years = [(year, end)] + ([(year - 1, f"{year - 1}" + end[4:])] if year > 2017 else [])
        for y, e in current_years:
            for fact in FLOW:
                rows.append({"cik": cik, "accession": acc, "accepted_at": pd.Timestamp(accepted), "available_session": avail, "fp": fp,
                             "form": form, "report_period": pd.Timestamp(end), "canonical_fact": fact, "tag_priority": 0, "qtrs": q,
                             "period_end": pd.Timestamp(e), "value": ytd(y, q, fact), "unit": "USD"})
            for fact in BAL:
                v = scale * 10 * (1 + 0.02 * ((y - 2017) * 4 + q)) * {"assets": 1, "current_assets": .4, "liabilities": .5, "current_liabilities": .2,
                                                                       "equity": .5, "cash": .1, "inventory": .08, "accounts_receivable": .1,
                                                                       "long_term_debt": .2, "short_term_debt": .05}[fact]
                rows.append({"cik": cik, "accession": acc, "accepted_at": pd.Timestamp(accepted), "available_session": avail, "fp": fp,
                             "form": form, "report_period": pd.Timestamp(end), "canonical_fact": fact, "tag_priority": 0, "qtrs": 0,
                             "period_end": pd.Timestamp(e), "value": v, "unit": "USD"})
        if q == 4 and year - 1 >= 2017:      # FY comparatives already added via current_years loop with qtrs=4
            pass
    return pd.DataFrame(rows)


def world(seed=0):
    rng = np.random.default_rng(seed)
    symbols = [f"S{i:02d}" for i in range(N)]
    dates = pd.date_range("2018-06-01", "2019-12-27", freq="7D")
    base = pd.DataFrame([(d, s) for d in dates for s in symbols], columns=["date", "symbol"])
    base["close"] = 50 + rng.normal(0, 5, len(base))
    base["dollar_volume"] = 1e7
    base["in_universe"] = True
    for name in R.BASELINE_FEATURES:
        base[name] = rng.normal(size=len(base))
    for name in R.LABELS:
        base[name] = rng.normal(size=len(base))
    ciks = {s: 100 + i for i, s in enumerate(symbols)}
    identities = pd.DataFrame({"ticker": symbols, "security_id": [f"sid-{ciks[s]}" for s in symbols], "cik": [ciks[s] for s in symbols],
                               "effective_from": pd.Timestamp("2017-01-01"), "effective_to": pd.NaT, "status": "A_CONFIRMED"})
    classification = pd.DataFrame({"cik": list(ciks.values()), "sic": 3571, "ff12": ["BusEq" if i % 2 else "Manuf" for i in range(N)],
                                   "ff17": "Machn", "ff48": "Chips", "effective_from": pd.Timestamp("2017-01-01"),
                                   "effective_to": pd.NaT, "evidenced_until": pd.Timestamp("2020-06-01")})
    facts = pd.concat([facts_for(c, rng) for c in ciks.values()], ignore_index=True)
    shares = pd.DataFrame([{"security_id": f"sid-{c}", "cik": c, "period_end": pd.Timestamp(e), "accepted_at": pd.Timestamp(a),
                            "available_session": pd.Timestamp(a).normalize(), "accession": f"sh-{c}-{a}", "form": "10-Q", "tag": "x", "unit": "shares",
                            "value": 1e6 * (1 + c / 1000), "is_amendment": False, "basis": "BALANCE_SHEET", "multi_class_summed": False}
                           for c in ciks.values() for e, a in [("2018-03-31", "2018-05-06"), ("2018-12-31", "2019-03-01"), ("2019-06-30", "2019-08-06")]])
    return base, identities, classification, shares, facts


def build(base, identities, classification, shares, facts, controls=True):
    snapshots = F.build_snapshots(facts)
    return R.build_panel(base, identities=identities, classification=classification, shares=shares, snapshots=snapshots,
                         split_table=None, controls_allowed=controls)


NEW_XS = [f"{n}_xs" for n in R.NEW_FEATURES + R.CONTROL_FEATURES]
RAW = list(R.NEW_FEATURES + R.CONTROL_FEATURES)


@pytest.fixture(scope="module")
def full():
    args = world()
    return args, build(*args)


def rows_up_to(panel, cut):
    return panel[panel["date"] <= pd.Timestamp(cut)].reset_index(drop=True)


def test_the_panel_produces_new_characteristics_with_real_coverage(full):
    _, panel = full
    late = panel[panel["date"] >= pd.Timestamp("2019-09-01")]
    for name in ("roa", "book_to_market", "asset_growth", "revenue_growth", "shares_growth"):
        assert late[name].notna().mean() > 0.5, name


def test_source_truncation_at_t_leaves_every_feature_dated_up_to_t_identical(full):
    (base, identities, classification, shares, facts), panel = full
    cut = pd.Timestamp("2019-06-30")
    truncated_facts = facts[facts["accepted_at"] <= cut]
    truncated_shares = shares[shares["accepted_at"] <= cut]
    rebuilt = build(base[base["date"] <= cut], identities, classification, truncated_shares, truncated_facts)
    a, b = rows_up_to(panel, cut), rebuilt.reset_index(drop=True)
    columns = RAW + NEW_XS
    pd.testing.assert_frame_equal(a[["date", "symbol", *columns]], b[["date", "symbol", *columns]], check_exact=False, rtol=1e-12, atol=1e-12)


def test_features_do_not_change_when_future_prices_or_labels_change(full):
    (base, identities, classification, shares, facts), panel = full
    cut = pd.Timestamp("2019-03-01")
    perturbed = base.copy()
    future = perturbed["date"] > cut
    perturbed.loc[future, "close"] = perturbed.loc[future, "close"] * 3.0
    for name in R.LABELS:
        perturbed[name] = np.random.default_rng(9).normal(size=len(perturbed))
    rebuilt = build(perturbed, identities, classification, shares, facts)
    a, b = rows_up_to(panel, cut), rows_up_to(rebuilt, cut)
    pd.testing.assert_frame_equal(a[RAW + NEW_XS], b[RAW + NEW_XS], check_exact=False, rtol=1e-12, atol=1e-12)


def test_no_feature_name_contains_a_label_or_the_ticker(full):
    _, panel = full
    features = R.feature_columns(True)
    assert not any("fwd" in name or name in ("symbol", "ticker") for name in features)
    assert len(features) == len(set(features))


def test_market_cap_uses_only_shares_available_on_the_date(full):
    (base, identities, classification, shares, facts), panel = full
    row = panel[(panel["date"] == pd.Timestamp("2019-02-15")) & (panel["symbol"] == "S03")]
    without_later = shares[shares["accepted_at"] <= pd.Timestamp("2019-02-15")]
    rebuilt = build(base, identities, classification, without_later, facts)
    again = rebuilt[(rebuilt["date"] == pd.Timestamp("2019-02-15")) & (rebuilt["symbol"] == "S03")]
    pd.testing.assert_frame_equal(row[RAW].reset_index(drop=True), again[RAW].reset_index(drop=True), check_exact=False, rtol=1e-12)


def test_relabelling_tickers_cannot_change_any_feature(full):
    (base, identities, classification, shares, facts), panel = full
    mapping = {s: f"Z{i:02d}" for i, s in enumerate(sorted(base["symbol"].unique()))}
    renamed = build(base.assign(symbol=base["symbol"].map(mapping)), identities.assign(ticker=identities["ticker"].map(mapping)),
                    classification, shares, facts)
    a = panel.assign(symbol=panel["symbol"].map(mapping)).sort_values(["date", "symbol"]).reset_index(drop=True)
    b = renamed.sort_values(["date", "symbol"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(a[["date", "symbol", *RAW]], b[["date", "symbol", *RAW]], check_exact=False, rtol=1e-12)


def test_a_missing_input_gives_a_missing_feature_not_zero_or_a_fill(full):
    (base, identities, classification, shares, facts), panel = full
    reduced = facts[~((facts["cik"] == 103) & (facts["canonical_fact"] == "inventory"))]
    rebuilt = build(base, identities, classification, shares, reduced)
    row = rebuilt[(rebuilt["symbol"] == "S03") & (rebuilt["date"] == pd.Timestamp("2019-12-27"))].iloc[0]
    assert np.isnan(row["inventory_growth"]) and np.isnan(row["inventory_growth_xs"])
    other = rebuilt[(rebuilt["symbol"] == "S04") & (rebuilt["date"] == pd.Timestamp("2019-12-27"))].iloc[0]
    assert not np.isnan(other["inventory_growth"])


def test_baseline_features_pass_through_unchanged(full):
    (base, *_), panel = full
    merged = R.assemble(panel, True).merge(base[["date", "symbol", *R.BASELINE_FEATURES]], on=["date", "symbol"], suffixes=("", "_orig"))
    for name in R.BASELINE_FEATURES:
        np.testing.assert_array_equal(merged[name].to_numpy(), merged[f"{name}_orig"].to_numpy())


def test_controls_are_withheld_when_the_security_master_gate_says_so(full):
    (base, identities, classification, shares, facts), _ = full
    panel = build(base, identities, classification, shares, facts, controls=False)
    assert not any(c.startswith("industry_rel") or c.startswith("log_market_cap") for c in panel.columns)
    assert "roa_xs" in panel.columns and len(R.feature_columns(False)) == 26 + len(R.NEW_FEATURES)


def test_registered_feature_count_and_families():
    assert 60 <= len(R.feature_columns(False)) <= 120 and 60 <= len(R.feature_columns(True)) <= 120
    assert set(R.FAMILY) == set(R.NEW_FEATURES) | set(R.CONTROL_FEATURES)


def test_cross_sectional_rank_uses_only_that_dates_names(full):
    (base, identities, classification, shares, facts), panel = full
    doubled = pd.concat([base, base[base["date"] > pd.Timestamp("2019-09-01")].assign(symbol=lambda d: d["symbol"] + "X")], ignore_index=True)
    # extra (unresolved) names at later dates must not move any earlier date's ranks
    ids = identities
    rebuilt = build(doubled, ids, classification, shares, facts)
    a, b = rows_up_to(panel, "2019-08-25"), rows_up_to(rebuilt, "2019-08-25")
    pd.testing.assert_frame_equal(a[["date", "symbol", *NEW_XS]], b[["date", "symbol", *NEW_XS]], check_exact=False, rtol=1e-12)


def test_industry_relative_needs_a_minimum_group_and_never_fills():
    values = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, np.nan, 10.0])
    groups = pd.Series(["a"] * 6 + ["b"])
    dates = pd.Series(pd.Timestamp("2019-01-04"), index=values.index)
    out = R.industry_relative(values, groups, dates, min_per_group=5)
    assert out.iloc[0] == -2.0 and np.isnan(out.iloc[5]) and np.isnan(out.iloc[6])
