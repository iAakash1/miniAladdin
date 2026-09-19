"""
Point-in-time forensics on the local research data.

    python -m scripts.quant.data_forensics analyst
    python -m scripts.quant.data_forensics earnings
    python -m scripts.quant.data_forensics fundamentals
    python -m scripts.quant.data_forensics options
    python -m scripts.quant.data_forensics security
    python -m scripts.quant.data_forensics all

Writes aggregate statistics only — counts, rates, distributions — to
`experiments/EXP-009-forensics/<domain>.json`. No vendor row is copied, so the
output is safe to commit. Nothing here reads a label or a forward return, and
nothing is dated after the last training-side date (2025-05-09): the holdout
window is never touched, and the firewall is armed for the run.

The questions asked of every source are the same:

* what is the schema and how much is there;
* is the `date` a vintage / publication date or a fiscal period end;
* what happens at a boundary that changes meaning (fiscal rollover, ticker
  reuse, restatement);
* how stale can a value get, and can the staleness be detected;
* how much of the traded universe is covered, by year;
* what stays missing, and does it stay missing.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date as Date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.quant.datasets.store import RawStore
from src.quant.study import exp009a

ROOT = Path("data/research")
OUTPUT = Path("experiments/EXP-009-forensics")
LAST_TRAINING_DATE = Date(2025, 5, 9)          # the last training-side date; nothing later is read


def _store() -> RawStore:
    return RawStore(str(ROOT))


def _universe_panel() -> pd.DataFrame:
    """In-universe (date, symbol) rows of the pre-holdout panel."""
    exp009a.arm_firewall(Path("."))
    panel = exp009a.build_returns_panel(LAST_TRAINING_DATE, root=Path("."))
    panel = panel[panel["in_universe"]][["date", "symbol"]].copy()
    panel["date"] = pd.to_datetime(panel["date"])
    panel["symbol"] = panel["symbol"].astype(str)
    return panel


def _clip_to_training(frame: pd.DataFrame, column: str = "date") -> pd.DataFrame:
    out = frame.copy()
    out[column] = pd.to_datetime(out[column])
    return out[out[column] <= pd.Timestamp(LAST_TRAINING_DATE)]


def _q(series: pd.Series, qs=(0.05, 0.25, 0.5, 0.75, 0.95, 0.99)) -> dict[str, float]:
    s = series.dropna()
    return {f"p{int(q * 100)}": float(s.quantile(q)) for q in qs} if len(s) else {}


# ── analyst estimates ────────────────────────────────────────────────────────

def analyst() -> dict[str, Any]:
    store = _store()
    out: dict[str, Any] = {"domain": "analyst_estimates", "last_training_date_read": str(LAST_TRAINING_DATE)}
    universe = _universe_panel()
    universe = universe[universe["date"] >= "2017-10-26"]

    for name, dataset in (("eps", "dolthub_earnings_eps_estimate"), ("sales", "dolthub_earnings_sales_estimate")):
        raw = store.read(dataset)
        manifest = store.manifest(dataset)
        raw["date"] = pd.to_datetime(raw["date"])
        raw["period_end_date"] = pd.to_datetime(raw["period_end_date"])
        raw["symbol"] = raw["symbol"].astype(str)
        full_rows, full_symbols = len(raw), int(raw["symbol"].nunique())
        d = raw[raw["date"] <= pd.Timestamp(LAST_TRAINING_DATE)]
        cy = d[d["period"] == "Current Year"].sort_values(["symbol", "date"]).reset_index(drop=True)
        g = cy.groupby("symbol", sort=False)

        distinct_dates = pd.Series(sorted(cy["date"].unique()))
        cy["gap_days"] = g["date"].diff().dt.days
        prev_end = g["period_end_date"].shift(1)
        rolled = (cy["period_end_date"] != prev_end) & prev_end.notna()
        backward = cy["period_end_date"] < prev_end
        same = (cy["consensus"] == g["consensus"].shift(1)) & (cy["period_end_date"] == prev_end)
        cy["run"] = (~same).groupby(cy["symbol"]).cumsum()
        runs = cy.groupby(["symbol", "run"]).size()
        change = (cy["consensus"] - g["consensus"].shift(1)).abs() / g["consensus"].shift(1).abs().clip(lower=0.05)

        right = cy[["symbol", "date", "consensus", "count"]].rename(columns={"date": "vdate"}).sort_values("vdate")
        matched = pd.merge_asof(universe.sort_values("date"), right, left_on="date", right_on="vdate",
                                by="symbol", direction="backward", allow_exact_matches=True)
        age = (matched["date"] - matched["vdate"]).dt.days
        usable = (age <= 45) & matched["consensus"].notna()
        by_year = matched.assign(usable=usable, year=matched["date"].dt.year).groupby("year")["usable"].mean()

        ordered_ok = cy[["high", "low", "consensus"]].notna().all(axis=1)
        out[name] = {
            "dataset": dataset,
            "manifest": {"point_in_time_status": manifest.point_in_time_status,
                         "retrieved_at": manifest.retrieved_at, "source_version": None},
            "rows_full_table": full_rows,
            "symbols_full_table": full_symbols,
            "rows_read_through_training_date": int(len(d)),
            "periods": d["period"].value_counts().to_dict(),
            "date_range_read": [str(d["date"].min().date()), str(d["date"].max().date())],
            "distinct_vintage_dates": int(len(distinct_dates)),
            "vintages_per_year": cy["date"].dt.year.pipe(lambda y: cy.groupby(y)["date"].nunique()).to_dict(),
            "share_vintage_dates_on_sunday": float((distinct_dates.dt.dayofweek == 6).mean()),
            "duplicate_symbol_date_period_rows": int(d.duplicated(["symbol", "date", "period"]).sum()),
            "per_symbol_gap_days_current_year": {
                "share_exactly_7": float((cy["gap_days"] == 7).mean()),
                "share_1_to_6": float(((cy["gap_days"] >= 1) & (cy["gap_days"] <= 6)).mean()),
                "share_over_7": float((cy["gap_days"] > 7).mean()),
                "share_over_28": float((cy["gap_days"] > 28).mean()),
                "share_over_365": float((cy["gap_days"] > 365).mean()),
                "max": float(cy["gap_days"].max()),
                "share_exactly_7_by_year": cy.groupby(cy["date"].dt.year)["gap_days"].apply(lambda s: float((s == 7).mean())).to_dict(),
            },
            "fiscal_rollover_current_year": {
                "events": int(rolled.sum()),
                "share_of_consecutive_vintage_pairs": float(rolled.mean()),
                "period_end_moves_backward": int(backward.sum()),
                "median_abs_relative_change_at_rollover": float(change[rolled].median()),
                "median_abs_relative_change_otherwise": float(change[~rolled & prev_end.notna()].median()),
                "rollover_events_by_month": cy.loc[rolled, "date"].dt.month.value_counts().sort_index().to_dict(),
            },
            "staleness_current_year": {
                "share_consecutive_vintages_identical_consensus": float(same.mean()),
                "identical_run_length_weeks": {**_q(runs, (0.5, 0.9, 0.99)), "max": int(runs.max())},
                "runs_of_13_weeks_or_more": int((runs >= 13).sum()),
                "runs_of_26_weeks_or_more": int((runs >= 26).sum()),
            },
            "contributor_count_current_year": {
                "null_share": float(cy["count"].isna().mean()),
                "share_equal_1": float((cy["count"] == 1).mean()),
                "quantiles": _q(cy["count"], (0.1, 0.5, 0.9, 0.99)),
            },
            "value_integrity_current_year": {
                "null_consensus_share": float(cy["consensus"].isna().mean()),
                "null_year_ago_share": float(cy["year_ago"].isna().mean()),
                "high_ge_consensus_ge_low_when_present": float(
                    ((cy["high"] >= cy["consensus"]) & (cy["consensus"] >= cy["low"]))[ordered_ok].mean()),
                "high_lt_low": int((cy["high"] < cy["low"]).sum()),
                "consensus_exactly_zero": int((cy["consensus"] == 0).sum()),
                "abs_consensus_below_0p05_share": float((cy["consensus"].abs() < 0.05).mean()),
                "spread_zero_share_when_count_is_1": float(
                    ((cy["high"] - cy["low"]).abs()[cy["count"] == 1] == 0).mean()),
            },
            "id_stability": {
                "symbols_with_gap_over_365_days": int(cy.loc[cy["gap_days"] > 365, "symbol"].nunique()),
                "gap_over_365_events": int((cy["gap_days"] > 365).sum()),
            },
            "universe_coverage": {
                "in_universe_rows_since_2017_10_26": int(len(matched)),
                "share_with_usable_vintage_within_45d": float(usable.mean()),
                "by_year": {int(k): round(float(v), 4) for k, v in by_year.items()},
                "median_vintage_age_days": float(age.median()),
                "p95_vintage_age_days": float(age.quantile(0.95)),
                "share_matched_to_same_day_vintage": float((age == 0).mean()),
                "universe_symbols_never_in_table": int(
                    len(set(universe["symbol"].unique()) - set(cy["symbol"].unique()))),
                "universe_symbols": int(universe["symbol"].nunique()),
            },
            "non_sunday_vintage_share": float((cy["date"].dt.dayofweek != 6).mean()),
        }
    return out


# ── earnings calendar and history ────────────────────────────────────────────

def earnings() -> dict[str, Any]:
    from src.quant.features.earnings import build_earnings_events

    store = _store()
    calendar = store.read("dolthub_earnings_calendar")
    history = store.read("dolthub_earnings_eps_history")
    calendar["date"] = pd.to_datetime(calendar["date"])
    retrieved = pd.Timestamp(store.manifest("dolthub_earnings_calendar").retrieved_at).tz_localize(None).normalize()
    universe = _universe_panel()

    calendar_read = calendar[calendar["date"] <= pd.Timestamp(LAST_TRAINING_DATE)]
    when = calendar["when"].fillna("UNKNOWN")
    events = build_earnings_events(history, calendar)
    events = events[events["announcement_date"] <= pd.Timestamp(LAST_TRAINING_DATE)]
    per_symbol_year = calendar_read.groupby(["symbol", calendar_read["date"].dt.year]).size()

    lookup = events[["symbol", "announcement_date"]].assign(symbol=lambda f: f["symbol"].astype(str))
    in_uni_symbols = set(universe["symbol"].unique())
    return {
        "domain": "earnings_calendar_and_history",
        "last_training_date_read": str(LAST_TRAINING_DATE),
        "calendar": {
            "rows_full_table": int(len(calendar)),
            "rows_read_through_training_date": int(len(calendar_read)),
            "symbols": int(calendar["symbol"].nunique()),
            "first_date": str(calendar["date"].min().date()),
            "last_date_in_snapshot": str(calendar["date"].max().date()),
            "rows_dated_after_retrieval": int((calendar["date"] > retrieved).sum()),
            "retrieved_on": str(retrieved.date()),
            "duplicate_symbol_date": int(calendar.duplicated(["symbol", "date"]).sum()),
            "weekend_dated_share": float((calendar["date"].dt.dayofweek >= 5).mean()),
            "rows_by_year": calendar["date"].dt.year.value_counts().sort_index().to_dict(),
            "timing_field": {
                "share_by_when": (when.value_counts(normalize=True)).round(4).to_dict(),
                "unknown_share_by_year": calendar.assign(u=calendar["when"].isna()).groupby(
                    calendar["date"].dt.year)["u"].mean().round(4).to_dict(),
            },
            "announcements_per_symbol_year": _q(per_symbol_year, (0.1, 0.5, 0.9)),
            "is_current_snapshot": True,
            "note": "the table carries dates after its own retrieval; every consumer must bound "
                    "availability at the observation date",
        },
        "eps_history": {
            "rows": int(len(history)),
            "symbols": int(history["symbol"].nunique()),
            "columns": list(history.columns),
            "has_announcement_date": False,
            "reported_null_share": float(history["reported"].isna().mean()),
            "estimate_null_share": float(history["estimate"].isna().mean()),
            "abs_reported_over_1000": int((history["reported"].abs() > 1000).sum()),
            "abs_estimate_over_1000": int((history["estimate"].abs() > 1000).sum()),
        },
        "matched_events": {
            "events_matched_through_training_date": int(len(events)),
            "with_sue": int(events["sue"].notna().sum()),
            "report_lag_days": _q(events["report_lag_days"]),
            "matched_by_year": events["announcement_date"].dt.year.value_counts().sort_index().to_dict(),
            "unknown_timing_share_of_events": float(events["when"].isna().mean()),
            "events_available_next_day_or_later_share": float(
                (events["available_from"] > events["announcement_date"]).mean()),
            "events_for_universe_symbols": int(events["symbol"].astype(str).isin(in_uni_symbols).sum()),
            "history_rows_dropped_no_announcement_before_2020": int(
                (pd.to_datetime(history["period_end_date"]) < "2019-12-01").sum()),
        },
        "timing_rule": {
            "before_market_open": "available the same trading day",
            "after_market_close": "available the next trading day",
            "during_market_hours_or_unknown": "treated as after-close (next day): conservative",
            "note": "an after-close result can never enter a same-close feature",
        },
    }


# ── fundamentals ─────────────────────────────────────────────────────────────

def fundamentals() -> dict[str, Any]:
    store = _store()
    calendar = store.read("dolthub_earnings_calendar")
    calendar["date"] = pd.to_datetime(calendar["date"])
    announced = calendar.sort_values("date")[["symbol", "date"]].rename(columns={"date": "announced"})
    out: dict[str, Any] = {"domain": "financial_statements", "last_training_date_read": str(LAST_TRAINING_DATE),
                           "tables": {}}
    for name in ("dolthub_earnings_income_statement", "dolthub_earnings_balance_sheet_assets",
                 "dolthub_earnings_balance_sheet_liabilities", "dolthub_earnings_balance_sheet_equity",
                 "dolthub_earnings_cash_flow_statement"):
        raw = store.read(name)
        raw["date"] = pd.to_datetime(raw["date"])
        manifest = store.manifest(name)
        d = raw[raw["date"] <= pd.Timestamp(LAST_TRAINING_DATE)]
        sized = d.sort_values("date")
        merged = pd.merge_asof(
            sized.assign(symbol=sized["symbol"].astype(str)).sort_values("date"),
            announced.assign(symbol=announced["symbol"].astype(str)).sort_values("announced"),
            left_on="date", right_on="announced", by="symbol", direction="forward",
            tolerance=pd.Timedelta(days=150))
        lag = (merged["announced"] - merged["date"]).dt.days
        out["tables"][name] = {
            "manifest_point_in_time_status": manifest.point_in_time_status,
            "rows_full_table": int(len(raw)),
            "rows_read_through_training_date": int(len(d)),
            "first_period_end": str(raw["date"].min().date()),
            "share_period_ends_on_month_end": float(raw["date"].dt.is_month_end.mean()),
            "period_kinds": raw["period"].value_counts().to_dict(),
            "duplicate_symbol_period_date_rows": int(d.duplicated(["symbol", "date", "period"]).sum()),
            "has_filing_or_acceptance_date": False,
            "has_restatement_vintage": False,
            "rows_before_calendar_start_2020_01_22": int((d["date"] < "2020-01-22").sum()),
            "share_rows_before_calendar_start": float((d["date"] < "2020-01-22").mean()),
            "share_gateable_via_calendar": float(merged["announced"].notna().mean()),
            "share_gateable_via_calendar_since_2020": float(
                merged.loc[merged["date"] >= "2019-11-01", "announced"].notna().mean()),
            "announcement_lag_days_when_matched": _q(lag),
            "null_share_by_column": raw.drop(columns=["date", "symbol", "period"]).isna().mean().round(4).to_dict(),
        }
    out["conclusion"] = (
        "The statements are keyed by fiscal period end with no filing date and no restatement "
        "vintage. They can be gated by the earnings calendar only from 2020-01-22, and even then "
        "the values are whatever the vendor holds today (possibly restated), not what was filed."
    )
    return out


# ── options ──────────────────────────────────────────────────────────────────

def options() -> dict[str, Any]:
    store = _store()
    universe = _universe_panel()
    universe = universe[universe["date"] >= "2019-02-09"]
    out: dict[str, Any] = {"domain": "options_aggregates", "last_training_date_read": str(LAST_TRAINING_DATE),
                           "tables": {}}
    for name in ("dolthub_options_chain_daily", "dolthub_options_volatility_history"):
        raw = store.read(name)
        raw["date"] = pd.to_datetime(raw["date"])
        raw["symbol"] = raw["symbol"].astype(str)
        manifest = store.manifest(name)
        d = raw[raw["date"] <= pd.Timestamp(LAST_TRAINING_DATE)]
        dates = pd.Series(sorted(d["date"].unique()))
        right = d.sort_values("date")
        matched = pd.merge_asof(universe.sort_values("date"), right[["symbol", "date"]].rename(columns={"date": "odate"}),
                                left_on="date", right_on="odate", by="symbol", direction="backward")
        age = (matched["date"] - matched["odate"]).dt.days
        fresh = age <= 7
        columns = [c for c in d.columns if c not in ("date", "symbol")]
        out["tables"][name] = {
            "manifest_point_in_time_status": manifest.point_in_time_status,
            "rows_full_table": int(len(raw)),
            "rows_read_through_training_date": int(len(d)),
            "symbols": int(d["symbol"].nunique()),
            "first_date": str(d["date"].min().date()),
            "distinct_dates": int(len(dates)),
            "dates_by_year": dates.dt.year.value_counts().sort_index().to_dict(),
            "day_of_week_of_dates": dates.dt.dayofweek.value_counts().sort_index().to_dict(),
            "symbols_per_date": _q(d.groupby("date")["symbol"].nunique(), (0.1, 0.5, 0.9)),
            "duplicate_symbol_date": int(d.duplicated(["symbol", "date"]).sum()),
            "null_share_by_column": d[columns].isna().mean().round(4).to_dict(),
            "universe_coverage": {
                "in_universe_rows_since_first_date": int(len(matched)),
                "share_with_row_within_7_days": float(fresh.mean()),
                "by_year": {int(k): round(float(v), 4) for k, v in
                            matched.assign(f=fresh, y=matched["date"].dt.year).groupby("y")["f"].mean().items()},
            },
            "timestamp_semantics": "date only; the intraday time at which quotes were observed is not recorded",
        }
    out["synchronisation_rule"] = (
        "Honarvar & Howard (Portfolio Management Research 2025 / SSRN 4766424) report options quotes "
        "recorded up to ~10 minutes after the stock close create look-ahead and that lagging the "
        "options data substantially reduces earlier predictability. Every options feature must be "
        "lagged by at least one session unless the quote time is known."
    )
    return out


# ── security master ──────────────────────────────────────────────────────────

def security() -> dict[str, Any]:
    store = _store()
    symbols = store.read("dolthub_stocks_symbol")
    manifest = store.manifest("dolthub_stocks_symbol")
    from src.quant.pit.universe import UniverseHistory

    history = UniverseHistory.load(ROOT / "universe")
    summary = history.summary()
    info = {k: summary[k] for k in ("name", "size", "snapshots", "start", "end", "unique_members", "ever_exited",
                                    "mean_entries_per_rebalance", "point_in_time", "coverage_classes")}
    info["mean_monthly_membership_turnover_share"] = summary["mean_entries_per_rebalance"] / summary["size"]
    info["notes"] = summary["notes"]
    return {
        "domain": "security_master",
        "symbol_table": {
            "rows": int(len(symbols)), "columns": list(symbols.columns),
            "point_in_time_status": manifest.point_in_time_status,
            "is_a_current_snapshot": True,
            "has_sector_or_industry": any(c in symbols.columns for c in ("sector", "industry", "sic", "gics")),
            "has_market_cap": "market_cap" in symbols.columns,
            "listing_exchange": symbols["listing_exchange"].value_counts(dropna=False).to_dict(),
            "etf_share": float(symbols["is_etf"].fillna(0).mean()),
            "date_range": [str(pd.to_datetime(symbols["date"]).min().date()), str(pd.to_datetime(symbols["date"]).max().date())],
            "distinct_symbols": int(symbols["symbol"].nunique()),
        },
        "universe_history": info,
    }


COMMANDS = {"analyst": analyst, "earnings": earnings, "fundamentals": fundamentals,
            "options": options, "security": security}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("domain", choices=[*COMMANDS, "all"])
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name in (COMMANDS if args.domain == "all" else [args.domain]):
        payload = COMMANDS[name]()
        (OUTPUT / f"{name}.json").write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
        print(f"wrote {OUTPUT / (name + '.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
