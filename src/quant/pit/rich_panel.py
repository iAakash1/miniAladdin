"""The rich point-in-time characteristic panel: baseline 26 features plus documented PIT company characteristics.

`build_panel` is a pure function of in-memory tables so every leakage property can be tested by
truncating or perturbing its inputs.  The baseline columns are passed through **unchanged** (same
values as `ds-491d761b9f2a6fc4`), so any difference in a later study is the added information, not a
re-derivation of the old features.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from src.quant.features import cross_section as xs
from src.quant.features import pit_fundamentals as F
from src.quant.pit import pit_coverage as C

PANEL_VERSION = "rich-pit-panel-v1"
BASELINE_DATASET_ID = "ds-491d761b9f2a6fc4"
BASELINE_FEATURES = (
    "acceleration_xs", "dist_52w_high_xs", "ma_gap_xs", "mom_21_xs", "mom_252_21_xs", "mom_63_xs", "reversal_5_xs",
    "trend_strength_63_xs", "downside_vol_63_xs", "vol_21_xs", "vol_63_xs", "vol_ratio_xs", "amihud_21_xs",
    "log_dollar_volume_21_xs", "volume_shock_xs", "market_drawdown", "market_mom_21", "market_mom_252", "market_vol_21",
    "market_vol_63", "market_vol_percentile", "rates_change_63", "rates_curvature", "rates_level", "rates_short", "rates_slope",
)
LABELS = ("fwd_rank_21", "fwd_ret_5", "fwd_ret_21")
PASSTHROUGH = ("dollar_volume", "in_universe", "close")
VALUE_FEATURES = ("book_to_market", "earnings_yield", "sales_yield", "fcf_yield", "ocf_yield", "operating_income_to_ev",
                  "gross_profit_to_ev", "sales_to_ev")
MARKET_FEATURES = ("shares_growth", "days_since_report")
CONTROL_FEATURES = ("log_market_cap", "industry_rel_roa", "industry_rel_gross_profitability", "industry_rel_book_to_market",
                    "industry_rel_operating_margin", "industry_rel_asset_growth", "industry_rel_earnings_yield")
NEW_FEATURES = tuple(F.CHARACTERISTIC_NAMES) + VALUE_FEATURES + MARKET_FEATURES
FAMILY = {
    **{n: "profitability" for n in ("gross_profitability", "roa", "roe", "operating_profitability", "cash_profitability", "gross_margin",
                                    "operating_margin", "net_margin", "cash_flow_margin", "ebitda_margin", "asset_turnover")},
    **{n: "value" for n in VALUE_FEATURES},
    **{n: "investment" for n in ("asset_growth", "capex_to_assets", "capex_to_revenue", "capex_growth", "inventory_growth",
                                 "inventory_to_assets_change", "working_capital_growth", "receivables_growth")},
    **{n: "quality" for n in ("accruals", "cash_flow_quality", "gross_margin_stability", "roa_stability", "cash_conversion")},
    **{n: "leverage" for n in ("debt_to_assets", "debt_to_equity", "net_debt_to_assets", "liabilities_to_assets", "current_ratio", "cash_to_assets")},
    **{n: "growth" for n in ("revenue_growth", "gross_profit_growth", "earnings_growth", "operating_income_growth", "ocf_growth", "fcf_growth")},
    **{n: "capital_structure" for n in ("debt_growth", "equity_issuance_proxy", "shares_growth")},
    **{n: "event" for n in ("seasonal_ni_surprise", "filing_lag_days", "days_since_report")},
    **{n: "control" for n in CONTROL_FEATURES},
}


def _positive_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return F._ratio(numerator, denominator)


def price_dependent_characteristics(frame: pd.DataFrame) -> pd.DataFrame:
    """Value, size and share-count characteristics from a frame already carrying snapshot columns and market_cap."""
    cap = frame["market_cap"]
    debt = frame["long_term_debt"] + frame["short_term_debt"]
    enterprise_value = cap + debt - frame["cash"]
    gross_profit = frame["gross_profit_ttm"].where(frame["gross_profit_ttm"].notna(), frame["revenue_ttm"] - frame["cost_of_revenue_ttm"])
    fcf = frame["operating_cash_flow_ttm"] - frame["capital_expenditure_ttm"]
    out = pd.DataFrame(index=frame.index)
    out["book_to_market"] = _positive_ratio(frame["equity"], cap)
    out["earnings_yield"] = _positive_ratio(frame["net_income_ttm"], cap)
    out["sales_yield"] = _positive_ratio(frame["revenue_ttm"], cap)
    out["fcf_yield"] = _positive_ratio(fcf, cap)
    out["ocf_yield"] = _positive_ratio(frame["operating_cash_flow_ttm"], cap)
    out["operating_income_to_ev"] = _positive_ratio(frame["operating_income_ttm"], enterprise_value)
    out["gross_profit_to_ev"] = _positive_ratio(gross_profit, enterprise_value)
    out["sales_to_ev"] = _positive_ratio(frame["revenue_ttm"], enterprise_value)
    out["shares_growth"] = _positive_ratio(frame["shares_outstanding"] - frame["shares_1y"], frame["shares_1y"])
    out["days_since_report"] = frame["snapshot_age_days"].astype(float)
    out["log_market_cap"] = np.log(cap.where(cap > 0))
    return out


def industry_relative(values: pd.Series, groups: pd.Series, dates: pd.Series, *, min_per_group: int = 5) -> pd.Series:
    """Value minus its (date, industry) mean over names with a value; groups thinner than `min_per_group` stay missing."""
    frame = pd.DataFrame({"v": pd.to_numeric(values, errors="coerce"), "g": groups, "d": dates})
    valid = frame["v"].notna() & frame["g"].notna()
    counts = frame[valid].groupby(["d", "g"])["v"].transform("size")
    means = frame[valid].groupby(["d", "g"])["v"].transform("mean")
    out = pd.Series(np.nan, index=values.index, dtype=float)
    out[valid] = np.where(counts >= min_per_group, frame.loc[valid, "v"] - means, np.nan)
    return out


def build_panel(base: pd.DataFrame, *, identities: pd.DataFrame, classification: pd.DataFrame, shares: pd.DataFrame,
                snapshots: pd.DataFrame, split_table: Optional[Mapping[str, Any]], controls_allowed: bool,
                staleness_days: int = F.STALE_SNAPSHOT_DAYS) -> pd.DataFrame:
    """Add PIT characteristics to `base` (date, symbol, close, baseline features, labels).  Returns the new panel."""
    frame = base.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = C.attach_identity(frame, identities)
    frame = C.attach_classification(frame, classification)
    frame = C.attach_shares(frame, shares, split_table)
    lagged = C.attach_shares(frame[["date", "symbol", "security_id"]], shares, split_table, lookback_days=365)
    frame["shares_1y"] = lagged["shares_outstanding"]
    frame["market_cap"] = frame["shares_outstanding"] * frame["close"]

    joined = F.attach_snapshot(frame, snapshots, staleness_days)
    if len(joined) and (joined["available"].notna()).any():
        # the structural PIT guarantee: nothing is attached before it was usable
        assert (joined.loc[joined["available"].notna(), "available"] <= frame.loc[joined.index[joined["available"].notna()], "date"]).all()
    raw_columns = [c for c in joined.columns if c not in ("date", "cik", "available", "accession", "form", "fp", "report_period", "accepted_at",
                                                        "available_session")]
    for column in raw_columns:
        frame[column] = joined[column].reindex(frame.index)
    characteristics = pd.concat([F.snapshot_characteristics(frame), price_dependent_characteristics(frame)], axis=1)
    if controls_allowed:
        characteristics["industry_rel_roa"] = industry_relative(characteristics["roa"], frame["ff12"], frame["date"])
        characteristics["industry_rel_gross_profitability"] = industry_relative(characteristics["gross_profitability"], frame["ff12"], frame["date"])
        characteristics["industry_rel_book_to_market"] = industry_relative(characteristics["book_to_market"], frame["ff12"], frame["date"])
        characteristics["industry_rel_operating_margin"] = industry_relative(characteristics["operating_margin"], frame["ff12"], frame["date"])
        characteristics["industry_rel_asset_growth"] = industry_relative(characteristics["asset_growth"], frame["ff12"], frame["date"])
        characteristics["industry_rel_earnings_yield"] = industry_relative(characteristics["earnings_yield"], frame["ff12"], frame["date"])
    names = list(NEW_FEATURES) + (list(CONTROL_FEATURES) if controls_allowed else [])
    frame = frame.drop(columns=[n for n in names if n in frame.columns])
    frame = pd.concat([frame, characteristics[names].astype(float)], axis=1)

    members = {day: set(group["symbol"]) for day, group in frame.groupby("date")}
    ranked = xs.cross_sectional_frame(frame[["date", "symbol", *names]], names, universe_for=members, method="rank")
    return pd.concat([frame, ranked[[f"{n}_xs" for n in names]]], axis=1)


def feature_columns(controls_allowed: bool) -> list[str]:
    names = list(NEW_FEATURES) + (list(CONTROL_FEATURES) if controls_allowed else [])
    return [*BASELINE_FEATURES, *[f"{n}_xs" for n in names]]


def assemble(frame: pd.DataFrame, controls_allowed: bool) -> pd.DataFrame:
    """Keep identifiers, metadata, labels, the baseline features (unchanged) and the new `_xs` features."""
    meta = ["date", "symbol", "security_id", "cik", "identity_grade", "ff12", "ff17", "ff48", "sic"]
    keep = [*meta, *PASSTHROUGH, *LABELS, *feature_columns(controls_allowed)]
    return frame[keep].sort_values(["date", "symbol"], kind="mergesort").reset_index(drop=True)


def content_hash(panel: pd.DataFrame, columns: Sequence[str]) -> str:
    ordered = panel[list(columns)].copy()
    ordered["date"] = pd.to_datetime(ordered["date"]).dt.strftime("%Y-%m-%d")
    ordered = ordered.sort_values(["date", "symbol"], kind="mergesort")
    return hashlib.sha256(pd.util.hash_pandas_object(ordered, index=False).to_numpy().tobytes()).hexdigest()


def feature_hash(columns: Sequence[str]) -> str:
    return hashlib.sha256(json.dumps(list(columns), separators=(",", ":")).encode()).hexdigest()
