"""Point-in-time company characteristics from as-reported SEC facts.

Every number is computed *at the acceptance time of a filing* using only facts accepted at or before
that instant (the AS_OF view), then attached to dates by availability session.  A later restatement is
a later filing with its own snapshot; it cannot alter an earlier one.

Trailing-twelve-month flows come from the accounting identity on as-reported year-to-date facts:

    TTM = FY(previous fiscal year) + YTD(current) - YTD(same period a year earlier)

and are NaN unless all three legs were reported and available at that instant.  Nothing is filled,
defaulted, forward-carried beyond its staleness limit, or set to zero.
"""

from __future__ import annotations

from bisect import bisect_right
from typing import Any, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

FEATURE_VERSION = "pit-fundamentals-v1"
FLOWS = ("revenue", "cost_of_revenue", "gross_profit", "operating_income", "net_income", "operating_cash_flow",
         "capital_expenditure", "depreciation_amortization", "eps_diluted")
BALANCES = ("assets", "current_assets", "liabilities", "current_liabilities", "equity", "cash", "inventory",
            "accounts_receivable", "long_term_debt", "short_term_debt")
YTD_QUARTERS = {"Q1": 1, "Q2": 2, "Q3": 3, "FY": 4}
PERIOD_TOLERANCE_DAYS = 12      # 52/53-week fiscal calendars move a period end by a few days
STALE_SNAPSHOT_DAYS = 550       # an annual filer can be ~15 months between reports at worst
HISTORY = 8


class _Vintages:
    """Per-filer lookup of the value of (fact, period end, quarters) as it stood at any instant."""

    def __init__(self, facts: pd.DataFrame):
        canonical = facts.sort_values(["canonical_fact", "period_end", "qtrs", "accession", "tag_priority"], kind="stable")
        canonical = canonical.drop_duplicates(["canonical_fact", "period_end", "qtrs", "accession"], keep="first")
        self.series: dict[tuple[str, np.datetime64, int], tuple[np.ndarray, np.ndarray]] = {}
        self.ends: dict[tuple[str, int], np.ndarray] = {}
        canonical = canonical.assign(period_end=pd.to_datetime(canonical["period_end"]), accepted_at=pd.to_datetime(canonical["accepted_at"]))
        for (fact, end, qtrs), group in canonical.groupby(["canonical_fact", "period_end", "qtrs"], sort=False):
            group = group.sort_values(["accepted_at", "accession"], kind="stable")
            self.series[(fact, end.to_datetime64(), int(qtrs))] = (
                group["accepted_at"].to_numpy("datetime64[ns]"), group["value"].to_numpy(dtype=float))
        buckets: dict[tuple[str, int], list[np.datetime64]] = {}
        for fact, end, qtrs in self.series:
            buckets.setdefault((fact, qtrs), []).append(end)
        self.ends = {k: np.sort(np.array(v, dtype="datetime64[ns]")) for k, v in buckets.items()}

    def nearest_end(self, fact: str, qtrs: int, target: np.datetime64, tolerance_days: int = PERIOD_TOLERANCE_DAYS) -> Optional[np.datetime64]:
        ends = self.ends.get((fact, qtrs))
        if ends is None or len(ends) == 0:
            return None
        position = np.searchsorted(ends, target)
        candidates = [ends[i] for i in (position - 1, position) if 0 <= i < len(ends)]
        best = min(candidates, key=lambda e: abs((e - target) / np.timedelta64(1, "D")))
        return best if abs((best - target) / np.timedelta64(1, "D")) <= tolerance_days else None

    def value_at(self, fact: str, end: Optional[np.datetime64], qtrs: int, instant: np.datetime64) -> float:
        if end is None:
            return np.nan
        entry = self.series.get((fact, end, qtrs))
        if entry is None:
            return np.nan
        times, values = entry
        index = bisect_right(times, instant) - 1
        return float(values[index]) if index >= 0 else np.nan

    def value_near(self, fact: str, qtrs: int, target: np.datetime64, instant: np.datetime64) -> float:
        return self.value_at(fact, self.nearest_end(fact, qtrs, target), qtrs, instant)


def _months_back(stamp: np.datetime64, months: int) -> np.datetime64:
    ts = pd.Timestamp(stamp) - pd.DateOffset(months=months)
    return np.datetime64(ts.to_datetime64())


def _ttm(v: _Vintages, fact: str, end: np.datetime64, quarters: int, instant: np.datetime64) -> float:
    current = v.value_at(fact, end, quarters, instant)
    if quarters == 4:
        return current
    prior_year_end = _months_back(end, 12)
    prior_ytd = v.value_near(fact, quarters, prior_year_end, instant)
    fiscal_year_end = _months_back(end, 3 * quarters)
    prior_fy = v.value_near(fact, 4, fiscal_year_end, instant)
    return prior_fy + current - prior_ytd     # NaN if any leg is missing


def _discrete_quarter(v: _Vintages, fact: str, end: np.datetime64, quarters: int, instant: np.datetime64) -> float:
    current = v.value_at(fact, end, quarters, instant)
    if quarters == 1:
        return current
    earlier = v.value_near(fact, quarters - 1, _months_back(end, 3), instant)
    return current - earlier


def snapshots_for_filer(cik: int, facts: pd.DataFrame) -> pd.DataFrame:
    """One snapshot per periodic filing of `cik`, each computed as of that filing's acceptance time."""
    if facts.empty:
        return pd.DataFrame()
    v = _Vintages(facts)
    meta = facts.drop_duplicates("accession")[["accession", "form", "fp", "report_period", "accepted_at", "available_session"]]
    meta = meta.assign(accepted_at=pd.to_datetime(meta["accepted_at"]), report_period=pd.to_datetime(meta["report_period"]))
    meta = meta.sort_values(["accepted_at", "accession"], kind="stable")
    rows: list[dict[str, Any]] = []
    for filing in meta.itertuples(index=False):
        quarters = YTD_QUARTERS.get(str(filing.fp))
        if quarters is None or pd.isna(filing.report_period):
            continue
        end = filing.report_period.to_datetime64()
        instant = filing.accepted_at.to_datetime64()
        row: dict[str, Any] = {"cik": cik, "accession": filing.accession, "form": filing.form, "fp": filing.fp,
                               "report_period": filing.report_period, "accepted_at": filing.accepted_at,
                               "available_session": filing.available_session, "ytd_quarters": quarters,
                               "filing_lag_days": (filing.accepted_at - filing.report_period).days}
        year_ago = _months_back(end, 12)
        for fact in FLOWS:
            row[f"{fact}_ttm"] = _ttm(v, fact, end, quarters, instant)
        row["net_income_q"] = _discrete_quarter(v, "net_income", end, quarters, instant)
        prior_quarter_end = v.nearest_end("net_income", quarters, year_ago)
        row["net_income_q_1y"] = _discrete_quarter(v, "net_income", prior_quarter_end, quarters, instant) if prior_quarter_end is not None else np.nan
        for fact in BALANCES:
            row[fact] = v.value_at(fact, end, 0, instant)
            row[f"{fact}_1y"] = v.value_near(fact, 0, year_ago, instant)
        rows.append(row)
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    table = _year_ago_ttm_and_history(table)
    return table


def _year_ago_ttm_and_history(table: pd.DataFrame) -> pd.DataFrame:
    """Add year-ago TTMs (from the snapshot that existed then) and eight-filing stability statistics."""
    table = table.sort_values(["accepted_at", "accession"], kind="stable").reset_index(drop=True)
    ends = table["report_period"].to_numpy("datetime64[ns]")
    fps = table["fp"].to_numpy()
    accepted = table["accepted_at"].to_numpy("datetime64[ns]")
    for fact in ("revenue", "gross_profit", "operating_income", "net_income", "operating_cash_flow", "capital_expenditure"):
        table[f"{fact}_ttm_1y"] = np.nan
    for i in range(len(table)):
        target = _months_back(ends[i], 12)
        gap = np.abs((ends - target) / np.timedelta64(1, "D"))
        candidates = np.where((gap <= 20) & (fps == fps[i]) & (accepted <= accepted[i]) & (np.arange(len(table)) < i))[0]
        if len(candidates):
            j = candidates[np.argmin(gap[candidates])]
            for fact in ("revenue", "gross_profit", "operating_income", "net_income", "operating_cash_flow", "capital_expenditure"):
                table.loc[i, f"{fact}_ttm_1y"] = table.loc[j, f"{fact}_ttm"]
    margin = np.where(table["revenue_ttm"] > 0, table["gross_profit_ttm"] / table["revenue_ttm"], np.nan)
    roa = np.where(table["assets"] > 0, table["net_income_ttm"] / table["assets"], np.nan)
    surprise = table["net_income_q"] - table["net_income_q_1y"]
    table["gross_margin_std8"] = pd.Series(margin).rolling(HISTORY, min_periods=5).std(ddof=1).to_numpy()
    table["roa_std8"] = pd.Series(roa).rolling(HISTORY, min_periods=5).std(ddof=1).to_numpy()
    scale = surprise.shift(1).rolling(HISTORY, min_periods=4).std(ddof=1)
    table["seasonal_ni_surprise"] = np.where(scale > 0, surprise / scale, np.nan)
    return table


def build_snapshots(facts: pd.DataFrame, ciks: Optional[Sequence[int]] = None) -> pd.DataFrame:
    """Snapshots for every requested filer."""
    parts = []
    grouped = facts.groupby("cik", sort=True)
    for cik, group in grouped:
        if ciks is not None and int(cik) not in set(map(int, ciks)):
            continue
        part = snapshots_for_filer(int(cik), group)
        if len(part):
            parts.append(part)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


# ── raw characteristics from a snapshot row (no prices needed) ───────────────

def _ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """numerator / denominator where the denominator is a positive, present number; else NaN (never 0, never inf)."""
    denominator = pd.to_numeric(denominator, errors="coerce")
    valid = denominator > 0
    return (pd.to_numeric(numerator, errors="coerce") / denominator).where(valid)


def _growth(now: pd.Series, before: pd.Series) -> pd.Series:
    """Relative change; defined only when the earlier value is positive (a change from a loss has no clean sign)."""
    return _ratio(now - before, before)


def snapshot_characteristics(s: pd.DataFrame) -> pd.DataFrame:
    """Price-free characteristics.  Column names are the catalog names (raw, before the cross-sectional rank)."""
    assets = s["assets"]
    liabilities = s["liabilities"].where(s["liabilities"].notna(), assets - s["equity"])
    # A debt tag that is absent is not read as zero debt: both legs must have been reported.
    debt = (s["long_term_debt"] + s["short_term_debt"])
    debt_1y = (s["long_term_debt_1y"] + s["short_term_debt_1y"])
    gross_profit = s["gross_profit_ttm"].where(s["gross_profit_ttm"].notna(), s["revenue_ttm"] - s["cost_of_revenue_ttm"])
    fcf = s["operating_cash_flow_ttm"] - s["capital_expenditure_ttm"]
    fcf_1y = s["operating_cash_flow_ttm_1y"] - s["capital_expenditure_ttm_1y"]
    working_capital = (s["current_assets"] - s["cash"]) - s["current_liabilities"]        # non-cash working capital
    working_capital_1y = (s["current_assets_1y"] - s["cash_1y"]) - s["current_liabilities_1y"]
    out = pd.DataFrame(index=s.index)
    # profitability
    out["gross_profitability"] = _ratio(gross_profit, assets)
    out["roa"] = _ratio(s["net_income_ttm"], assets)
    out["roe"] = _ratio(s["net_income_ttm"], s["equity"])
    out["operating_profitability"] = _ratio(s["operating_income_ttm"], assets)
    out["cash_profitability"] = _ratio(s["operating_cash_flow_ttm"], assets)
    out["gross_margin"] = _ratio(gross_profit, s["revenue_ttm"])
    out["operating_margin"] = _ratio(s["operating_income_ttm"], s["revenue_ttm"])
    out["net_margin"] = _ratio(s["net_income_ttm"], s["revenue_ttm"])
    out["cash_flow_margin"] = _ratio(s["operating_cash_flow_ttm"], s["revenue_ttm"])
    out["ebitda_margin"] = _ratio(s["operating_income_ttm"] + s["depreciation_amortization_ttm"], s["revenue_ttm"])
    out["asset_turnover"] = _ratio(s["revenue_ttm"], assets)
    # investment
    out["asset_growth"] = _growth(assets, s["assets_1y"])
    out["capex_to_assets"] = _ratio(s["capital_expenditure_ttm"], assets)
    out["capex_to_revenue"] = _ratio(s["capital_expenditure_ttm"], s["revenue_ttm"])
    out["capex_growth"] = _growth(s["capital_expenditure_ttm"], s["capital_expenditure_ttm_1y"])
    out["inventory_growth"] = _growth(s["inventory"], s["inventory_1y"])
    out["inventory_to_assets_change"] = _ratio(s["inventory"] - s["inventory_1y"], s["assets_1y"])
    out["working_capital_growth"] = _ratio(working_capital - working_capital_1y, s["assets_1y"])
    out["receivables_growth"] = _growth(s["accounts_receivable"], s["accounts_receivable_1y"])
    # quality
    out["accruals"] = _ratio(s["net_income_ttm"] - s["operating_cash_flow_ttm"], assets)
    out["cash_flow_quality"] = _ratio(s["operating_cash_flow_ttm"], s["net_income_ttm"].where(s["net_income_ttm"] > 0))
    out["gross_margin_stability"] = -s["gross_margin_std8"]        # higher = more stable
    out["roa_stability"] = -s["roa_std8"]
    out["cash_conversion"] = _ratio(fcf, s["net_income_ttm"].where(s["net_income_ttm"] > 0))
    # leverage
    out["debt_to_assets"] = _ratio(debt, assets)
    out["debt_to_equity"] = _ratio(debt, s["equity"])
    out["net_debt_to_assets"] = (debt - s["cash"]) / assets.where(assets > 0)
    out["liabilities_to_assets"] = _ratio(liabilities, assets)
    out["current_ratio"] = _ratio(s["current_assets"], s["current_liabilities"])
    out["cash_to_assets"] = _ratio(s["cash"], assets)
    # growth
    out["revenue_growth"] = _growth(s["revenue_ttm"], s["revenue_ttm_1y"])
    out["gross_profit_growth"] = _ratio(gross_profit - s["gross_profit_ttm_1y"], s["assets_1y"])
    out["earnings_growth"] = _ratio(s["net_income_ttm"] - s["net_income_ttm_1y"], s["assets_1y"])
    out["operating_income_growth"] = _ratio(s["operating_income_ttm"] - s["operating_income_ttm_1y"], s["assets_1y"])
    out["ocf_growth"] = _ratio(s["operating_cash_flow_ttm"] - s["operating_cash_flow_ttm_1y"], s["assets_1y"])
    out["fcf_growth"] = _ratio(fcf - fcf_1y, s["assets_1y"])
    # capital structure
    out["debt_growth"] = _ratio(debt - debt_1y, s["assets_1y"])
    out["equity_issuance_proxy"] = _ratio((s["equity"] - s["equity_1y"]) - s["net_income_ttm"], s["assets_1y"])
    # event timing
    out["seasonal_ni_surprise"] = s["seasonal_ni_surprise"]
    out["filing_lag_days"] = s["filing_lag_days"].astype(float)
    return out


CHARACTERISTIC_NAMES = (
    "gross_profitability", "roa", "roe", "operating_profitability", "cash_profitability", "gross_margin", "operating_margin",
    "net_margin", "cash_flow_margin", "ebitda_margin", "asset_turnover",
    "asset_growth", "capex_to_assets", "capex_to_revenue", "capex_growth", "inventory_growth", "inventory_to_assets_change",
    "working_capital_growth", "receivables_growth",
    "accruals", "cash_flow_quality", "gross_margin_stability", "roa_stability", "cash_conversion",
    "debt_to_assets", "debt_to_equity", "net_debt_to_assets", "liabilities_to_assets", "current_ratio", "cash_to_assets",
    "revenue_growth", "gross_profit_growth", "earnings_growth", "operating_income_growth", "ocf_growth", "fcf_growth",
    "debt_growth", "equity_issuance_proxy", "seasonal_ni_surprise", "filing_lag_days",
)


def attach_snapshot(rows: pd.DataFrame, snapshots: pd.DataFrame, staleness_days: int = STALE_SNAPSHOT_DAYS) -> pd.DataFrame:
    """As-of join of the latest available snapshot to (date, cik) rows.  Stale or absent -> missing.

    Adds `snapshot_age_days`, `sessions_since_report` inputs and the raw snapshot columns needed downstream.
    """
    known = rows[rows["cik"].notna()]
    left = known[["date", "cik"]].reset_index()
    left["date"] = pd.to_datetime(left["date"]).astype("datetime64[ns]")
    left = left.sort_values("date", kind="mergesort")
    left["cik"] = left["cik"].astype("int64")
    right = snapshots.copy()
    right["available"] = pd.to_datetime(right["available_session"]).astype("datetime64[ns]")
    right = right.dropna(subset=["available"]).sort_values(["available", "accepted_at", "accession"], kind="stable")
    right["cik"] = right["cik"].astype("int64")
    merged = pd.merge_asof(left, right, left_on="date", right_on="available", by="cik", direction="backward",
                           tolerance=pd.Timedelta(days=staleness_days))
    merged["snapshot_age_days"] = (merged["date"] - merged["available"]).dt.days
    return merged.set_index("index")
