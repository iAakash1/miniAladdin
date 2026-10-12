"""EXP-014: samples, point-in-time treatment windows, the registered regressions and the mechanical decision rule, all on synthetic data."""

import numpy as np
import pandas as pd
import pytest

from src.quant.pit.calendar import TradingCalendar
from src.quant.study import exp014

SESSIONS = pd.bdate_range("2012-01-02", "2016-12-30")
CALENDAR = TradingCalendar.from_dates(SESSIONS.date)


def filing(adsh, cik, form, period, accepted):
    return {"adsh": adsh, "cik": cik, "name": "X", "sic": 1.0, "form": form, "period": period, "fy": 2013.0, "fp": "FY", "filed": accepted[:10].replace("-", ""), "accepted_at": pd.Timestamp(accepted),
            "prevrpt": 0, "former": None, "changed": None, "countryinc": "US", "stprinc": "NY", "ein": "1", "source_archive": "x"}


def classes(rows):
    base = {"classifiable": False, "core_changing_1pct": False, "unchanged_numbers": False}
    return pd.DataFrame([{"adsh": a, **{**base, **kw}} for a, kw in rows], columns=["adsh", *base])


def test_amendment_categories_are_exhaustive_and_exclusive():
    f = pd.DataFrame([filing("o1", 1, "10-K", "20121231", "2013-03-01 10:00"), filing("a1", 1, "10-K/A", "20121231", "2013-06-03 10:00"), filing("a2", 1, "10-Q/A", "20130331", "2013-07-01 10:00"),
                      filing("a3", 1, "10-Q/A", "20130630", "2013-08-01 10:00"), filing("a4", 1, "10-Q/A", "20130930", "2013-09-02 10:00")])
    c = classes([("a1", {"classifiable": True, "core_changing_1pct": True}), ("a2", {"classifiable": True, "unchanged_numbers": True}), ("a3", {"classifiable": True}), ("a4", {})])
    originals, amendments = exp014.amendment_events(f, c, CALENDAR, {1})
    assert len(originals) == 1
    assert dict(zip(amendments["adsh"], amendments["category"])) == {"a1": "core", "a2": "unchanged", "a3": "other_changed", "a4": "unclass"}


def test_treatment_windows_use_only_what_was_available_and_expire():
    f = pd.DataFrame([filing("o1", 1, "10-K", "20121231", "2013-03-01 10:00"), filing("a1", 1, "10-K/A", "20121231", "2013-06-03 10:00")])
    c = classes([("a1", {"classifiable": True, "core_changing_1pct": True})])
    originals, amendments = exp014.amendment_events(f, c, CALENDAR, {1})
    avail = int(amendments["avail_d"].iloc[0])
    days = np.array([avail - 400, avail - 1, avail, avail + 729, avail + 731])
    dates = pd.to_datetime(np.datetime64("1970-01-01") + days.astype("timedelta64[D]"))
    keys = pd.DataFrame({"date": dates, "cik": 1})
    t = exp014.treatment_frame(keys, originals, amendments)
    # 400 days before the amendment is before the first original report was usable? the original was usable from 2013-03-01
    assert t["core_730"].tolist()[1:] == [0.0, 1.0, 1.0, 0.0]                       # not yet; from its availability day; still inside 730 days; expired after 730
    assert t.loc[1, "core_next365"] == 1.0 and t.loc[2, "core_next365"] == 0.0 and t.loc[2, "core_prev365"] == 1.0   # anticipation windows look forward, past windows backward
    assert t.loc[3, "core_prev730b"] == 1.0 and t.loc[3, "core_prev365"] == 0.0                                          # 729 days later it sits in the (365, 730] past bin only
    assert np.isnan(t.loc[0, "core_730"])                                                                                 # 400 days before the amendment the firm had no original report yet


def test_no_treatment_before_the_firm_has_any_original_report():
    f = pd.DataFrame([filing("o1", 1, "10-K", "20121231", "2013-03-01 10:00")])
    originals, amendments = exp014.amendment_events(f, classes([]), CALENDAR, {1})
    keys = pd.DataFrame({"date": pd.to_datetime(["2013-02-01", "2013-04-01"]), "cik": 1})
    t = exp014.treatment_frame(keys, originals, amendments)
    assert np.isnan(t.loc[0, "core_730"]) and t.loc[1, "core_730"] == 0.0
    assert np.isnan(exp014.treatment_frame(pd.DataFrame({"date": pd.to_datetime(["2013-04-01"]), "cik": [np.nan]}), originals, amendments).loc[0, "core_730"])


def test_confirmatory_sample_drops_discovery_firms_untrusted_rows_and_dates_outside_the_window():
    panel = pd.DataFrame({
        "date": pd.to_datetime(["2015-01-02", "2015-01-02", "2015-01-02", "2015-01-02", "2013-12-31", "2025-06-06", "2015-01-09"]),
        "security_id": ["a", "b", None, "d", "e", "f", "g"], "cik": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0],
        "fwd_rank_21": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, np.nan], "in_universe": [True] * 7})
    out = exp014.confirmatory_sample(panel, frozen_ciks={20})
    assert out["security_id"].tolist() == ["a", "d"]        # b is a discovery company, c has no trusted identity, e and f are outside the dates, g has no label
    sep = exp014.time_separate_sample(panel.assign(date=pd.to_datetime(["2015-01-02"] * 5 + ["2017-06-02", "2016-01-01"])))
    assert set(sep["security_id"]) == {"a", "b", "d", "e"}      # f is dated after 2017-03-31; g has no label; c has no trusted identity; discovery firms are the point of this sample


def make_panel(n_firms=120, n_dates=40, effect=0.0, treated=12, seed=0, persistent=0.0):
    rng = np.random.default_rng(seed)
    firm = np.repeat(np.arange(n_firms), n_dates)
    date = np.tile(pd.date_range("2015-01-02", periods=n_dates, freq="W-FRI"), n_firms)
    sector = (firm % 6).astype(str)
    trait = rng.normal(size=n_firms)
    treat_firm = np.isin(firm, np.arange(treated))
    on = treat_firm & (np.tile(np.arange(n_dates), n_firms) >= n_dates // 3)
    x = rng.normal(size=len(firm))
    y = effect * on + persistent * treat_firm + 0.2 * x + 0.3 * trait[firm] + rng.normal(size=len(firm))
    f = pd.DataFrame({"firm": firm.astype(str), "date": date, "cell": sector, LABEL: y, "D_core_730": on.astype(float), "D_other_730": 0.0, "D_unchanged_730": 0.0, "D_unclass_730": 0.0,
                      "D_any_730": on.astype(float)})
    for c in exp014.BASE_CONTROLS:
        f[c] = rng.normal(size=len(f)) * 0.1
    f["mom_21_xs"] = x
    return f


LABEL = exp014.LABEL


def test_regression_recovers_a_planted_effect_and_not_an_absent_one():
    real = exp014.regress(make_panel(effect=-0.6, seed=1), "D_core_730", ["D_core_730"], exp014.BASE_CONTROLS, draws=999, seed=1)
    assert real["coef"] < -0.4 and real["wcr_p_negative"] < 0.01 and real["treated_firms"] == 12
    null = [exp014.regress(make_panel(effect=0.0, seed=10 + i), "D_core_730", ["D_core_730"], exp014.BASE_CONTROLS, draws=399, seed=i)["wcr_p_negative"] for i in range(40)]
    assert np.mean(np.array(null) < 0.05) <= 0.2                                   # 40 draws of a 5% test: very unlikely to see more than 8 rejections unless the test over-rejects


def test_a_treatment_without_variation_is_reported_not_crashed():
    f = make_panel(effect=-0.5, seed=3)
    f["D_core_730"] = 0.0
    out = exp014.regress(f, "D_core_730", ["D_core_730"], exp014.BASE_CONTROLS, draws=99, seed=1)
    assert out.get("degenerate") and out["wcr_p_negative"] == 1.0


def test_leave_out_and_influence_helpers():
    f = make_panel(effect=-0.6, seed=5)
    top = exp014.influential_treated(f, "D_core_730", ["D_core_730"], exp014.BASE_CONTROLS, 3)
    assert len(top) == 3 and set(top) <= set(f.loc[f["D_core_730"] > 0, "firm"])
    years = exp014.leave_out_fits(f.assign(date=f["date"] + pd.to_timedelta((f["firm"].astype(int) % 3) * 365, unit="D")), "D_core_730", ["D_core_730"], exp014.BASE_CONTROLS, "year")
    assert len(years) >= 2 and all(r["coef"] < 0 for r in years)
    sectors = exp014.leave_out_fits(f, "D_core_730", ["D_core_730"], exp014.BASE_CONTROLS, "sector")
    assert len(sectors) == 6


def passing():
    one = lambda coef, p, firms=60, rows=400: {"coef": coef, "wcr_p_negative": p, "treated_firms": firms, "treated_rows": rows}
    return {"H1": one(-0.2, 0.001), "H2": one(-0.1, 0.01, 90, 900), "holm_adjusted_p": {"H1": 0.002, "H2": 0.01},
            "R2_influence": {**one(-0.15, 0.01), "share_of_full_estimate": 0.75}, "R3_years": [{"coef": -0.1}] * 11 + [{"coef": 0.1}],
            "R4_full_controls": one(-0.14, 0.01), "R5_time_separate": one(-0.1, 0.5, 9, 161), "R5_time_separate_any": one(-0.09, 0.04, 58, 1798), "R7_within_firm": one(-0.1, 0.02), "R6_sector": [{"coef": -0.1}] * 10 + [{"coef": 0.1}] * 2,
            "event_time": {"anticipation_ratio": 0.2}}


def test_decision_rule_labels():
    res = passing()
    assert exp014.decide(res)["label"] == "SURVIVES" and exp014.decide(res)["interpretation"] == "TIME_SPECIFIC"
    res["event_time"]["anticipation_ratio"] = 0.9
    assert exp014.decide(res)["interpretation"] == "MARKER_OF_PERSISTENT_TROUBLE"
    for gate, change in (("R2_influence", lambda r: r["R2_influence"].update(share_of_full_estimate=0.3)), ("R3_years", lambda r: r.update(R3_years=[{"coef": -0.1}] * 8 + [{"coef": 0.1}] * 4)),
                         ("R4_full_controls", lambda r: r["R4_full_controls"].update(wcr_p_negative=0.2)), ("R5_time_separate", lambda r: r["R5_time_separate_any"].update(wcr_p_negative=0.3)),
                         ("R6_sector", lambda r: r.update(R6_sector=[{"coef": -0.1}] * 7 + [{"coef": 0.1}] * 5)),
                         ("R7_within_firm", lambda r: r["R7_within_firm"].update(wcr_p_negative=0.2))):
        broken = passing()
        change(broken)
        out = exp014.decide(broken)
        assert out["label"] == "FRAGILE" and out["failed_gates"] == [gate]
    weak = passing()
    weak["holm_adjusted_p"]["H1"] = 0.2
    assert exp014.decide(weak)["label"] == "NOT_REPLICATED"
    core_sign = passing()
    core_sign["R5_time_separate"]["coef"] = 0.02                      # the any-amendment coefficient may be significant, but the core sign must also replicate
    assert exp014.decide(core_sign)["failed_gates"] == ["R5_time_separate"]
    wrong_sign = passing()
    wrong_sign["H1"]["coef"] = 0.05
    assert exp014.decide(wrong_sign)["label"] == "NOT_REPLICATED"
    thin = passing()
    thin["H1"]["treated_firms"] = 30
    assert exp014.decide(thin)["label"] == "INCONCLUSIVE"            # too few treated firms: nothing is concluded, even with a tiny p


def test_definition_names_every_gate_the_code_applies():
    assert set(exp014.DEFINITION["robustness_gates"]) == {"R1_power", "R2_influence", "R3_years", "R4_full_controls", "R5_time_separate", "R6_sector", "R7_within_firm"}
    assert set(exp014.DEFINITION["decision"]) >= {"SURVIVES", "FRAGILE", "NOT_REPLICATED", "INCONCLUSIVE"}


# ── machine-learning helpers ─────────────────────────────────────────────────────────────────────────

def ml_toy(n_firms=30, n_dates=120):
    rng = np.random.default_rng(7)
    firm = np.repeat([f"f{i}" for i in range(n_firms)], n_dates)
    date = np.tile(pd.date_range("2014-04-04", periods=n_dates, freq="W-FRI"), n_firms)
    f = pd.DataFrame({"firm": firm, "date": date, "symbol": firm})
    for c in exp014.AMEND_BLOCK:
        f[c] = rng.integers(0, 2, size=len(f)).astype(float)
    return f.reset_index(drop=True)


def test_permuted_placebo_keeps_each_dates_values_and_shifted_placebo_is_the_firms_own_past():
    f = ml_toy()
    permuted = exp014.ml_frame(f, "P1", 3)
    for _, g in f.groupby("date"):
        assert sorted(permuted.loc[g.index, "D_core_730"]) == sorted(g["D_core_730"])
    assert not permuted["D_core_730"].equals(f["D_core_730"])
    shifted = exp014.ml_frame(f, "P1s", 0)
    g = f[f["firm"] == "f0"].sort_values("date")
    s = shifted.loc[g.index].sort_values("date")
    assert np.allclose(s["D_core_730"].to_numpy()[exp014.SHIFT_ROWS:], g["D_core_730"].to_numpy()[:-exp014.SHIFT_ROWS])
    assert s["D_core_730"].isna().sum() == exp014.SHIFT_ROWS
    assert exp014.ml_frame(f, "M1", 0) is f                     # real arms are untouched


def test_ml_label_requires_significance_folds_and_beating_the_placebos():
    c = lambda diff, adj, folds: {"mean_diff": diff, "holm_adjusted_p": adj, "positive_folds": folds}
    base = {"T_ridge": c(0.004, 0.01, 7), "T_boosted": c(0.002, 0.2, 5), "C_permute": {"mean_diff": 0.003}, "C_shift": {"mean_diff": 0.001}}
    assert exp014.ml_label(base) == {"T_ridge": "SUPPORTED", "T_boosted": "NOT_SUPPORTED"}
    base["C_shift"]["mean_diff"] = -0.001                        # a placebo does as well: the ridge gain is fragile
    assert exp014.ml_label(base)["T_ridge"] == "FRAGILE"
    base["T_ridge"] = c(0.004, 0.01, 4)
    assert exp014.ml_label(base)["T_ridge"] == "FRAGILE"


def test_artifact_round_trip_in_a_fresh_process(tmp_path):
    import subprocess
    import sys

    rng = np.random.default_rng(1)
    n = 400
    f = pd.DataFrame({c: rng.normal(size=n) for c in exp014.ML_ARMS["M1"]["features"]})
    f[exp014.LABEL] = f.iloc[:, 0] * 0.1 + rng.normal(size=n)
    f["date"] = pd.date_range("2015-01-02", periods=n, freq="B")
    path = exp014.train_artifact(f, "M1", tmp_path, fingerprint="test")
    bundle = exp014.exp012.load_artifact(path)
    assert bundle["features"] == exp014.ML_ARMS["M1"]["features"] and "NOT FOR PRODUCTION" in bundle["status"]
    rows = f.head(50).reset_index(drop=True)
    rows.to_parquet(tmp_path / "rows.parquet")
    exp014.exp012.predict_with_artifact(bundle, rows).to_frame("score").to_parquet(tmp_path / "expected.parquet")
    proc = subprocess.run([sys.executable, "-m", "src.quant.study.exp014", "reload-check", str(path), str(tmp_path / "rows.parquet"), str(tmp_path / "expected.parquet")], capture_output=True, text=True)
    import json
    assert proc.returncode == 0 and json.loads(proc.stdout.strip().splitlines()[-1])["ok"] is True
    broken = rows.copy()
    broken.loc[0, exp014.ML_ARMS["M1"]["features"][0]] = np.inf
    with pytest.raises(ValueError):
        exp014.exp012.predict_with_artifact(bundle, broken)


def test_placebo_event_calibration_does_not_reject_more_than_chance():
    f = make_panel(n_firms=80, n_dates=60, effect=-0.5, treated=8, seed=21)           # a real effect in the real treated firms; placebo events elsewhere carry none
    out = exp014.placebo_event_calibration(f, draws=60, seed=3, boot_draws=199)
    assert out["placebo_draws"] >= 55 and out["treated_firms_per_draw"] == 8
    assert out["rejection_rate_5pct_one_sided"] <= 0.2 and abs(out["coef_mean"]) < 0.2


def test_score_augmented_regression_holds_the_models_opinion_fixed():
    f = make_panel(n_firms=60, n_dates=40, effect=-0.5, treated=8, seed=33)
    rng = np.random.default_rng(2)
    f["symbol"] = f["firm"]
    pred = f[["date", "symbol"]].copy()
    pred["prediction"] = rng.normal(size=len(pred))
    out = exp014.score_augmented(f, pred, draws=199, seed=1)
    assert out["rows"] == len(f) and out["coef"] < -0.2 and out["treated_firms"] == 8
    half = pred.iloc[: len(pred) // 2]
    assert exp014.score_augmented(f, half, draws=99, seed=1)["rows"] == len(half)         # only rows the model scored enter


def test_firm_fixed_effects_remove_a_stable_trait_that_the_pooled_estimate_picks_up():
    f = make_panel(n_firms=100, n_dates=50, effect=0.0, treated=10, seed=51, persistent=-0.6)       # treated firms are persistently weak, but the amendment itself does nothing
    pooled = exp014.regress(f, "D_core_730", ["D_core_730"], exp014.BASE_CONTROLS, draws=399, seed=1)
    within = exp014.regress(f, "D_core_730", ["D_core_730"], exp014.BASE_CONTROLS, draws=399, seed=1, firm_fe=True)
    assert pooled["coef"] < -0.3 and abs(within["coef"]) < 0.15 and within["wcr_p_negative"] > 0.05 and within["firm_fe"] is True
    real = make_panel(n_firms=100, n_dates=50, effect=-0.8, treated=10, seed=52)
    assert exp014.regress(real, "D_core_730", ["D_core_730"], exp014.BASE_CONTROLS, draws=399, seed=1, firm_fe=True)["coef"] < -0.5


def test_registry_events_are_usable_from_the_session_after_their_event_date():
    edgar = pd.DataFrame({
        "cik": [1, 1, 1, 1, 1, 2], "accession": ["e1", "e2", "e3", "e4", "e5", "e6"],
        "form": ["8-K", "8-K", "NT 10-K", "10-K/A", "10-K/A", "8-K/A"],
        "event_date": pd.to_datetime(["2013-03-08", "2013-03-11", "2013-04-12", "2013-06-03", "2013-06-04", "2013-03-09"]),     # 2013-03-09 is a Saturday
        "items": ["2.02,4.02", "4.020", "", "", "", "4.02"]})
    out = exp014.registry_events(edgar, fsds_adsh={"e4"}, calendar=CALENDAR, ciks={1, 2})
    assert out["i402"].sort_values("cik")["cik"].tolist() == [1, 2]                         # '4.020' is not item 4.02
    day = lambda text: int((pd.Timestamp(text) - pd.Timestamp("1970-01-01")).days)
    assert out["i402"].loc[out["i402"]["cik"] == 1, "avail_d"].iloc[0] == day("2013-03-11")    # Friday event: usable from Monday
    assert out["i402"].loc[out["i402"]["cik"] == 2, "avail_d"].iloc[0] == day("2013-03-11")    # Saturday event: Monday as well
    assert out["nt"]["avail_d"].tolist() == [day("2013-04-15")]
    assert out["nonfsds_amend"]["avail_d"].tolist() == [day("2013-06-05")]                  # e4 is in the data sets; only e5 is an amendment without financial statements


def test_registry_windows_enter_the_treatment_frame_as_730_day_indicators():
    f = pd.DataFrame([filing("o1", 1, "10-K", "20121231", "2013-03-01 10:00")])
    originals, amendments = exp014.amendment_events(f, classes([]), CALENDAR, {1})
    extra = {"i402": pd.DataFrame({"cik": [1], "avail_d": [int((pd.Timestamp("2013-06-03") - pd.Timestamp("1970-01-01")).days)]})}
    keys = pd.DataFrame({"date": pd.to_datetime(["2013-05-01", "2013-07-01", "2015-07-01"]), "cik": 1})
    t = exp014.treatment_frame(keys, originals, amendments, extra)
    assert t["D_i402_730"].tolist() == [0.0, 1.0, 0.0]
