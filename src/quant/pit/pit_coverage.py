"""As-of attachment of identity, industry and shares to (date, ticker) rows, and the coverage they achieve.

The same three attach functions build the rich panel and measure its coverage, so a coverage number can
never describe a join the panel did not use.  Every join is as-of: a value is attached only if it was
available (accepted, next-session rule) on or before the row's date, and never older than the staleness
limit.  A row with no such value gets a missing value, never a zero.
"""

from __future__ import annotations

from datetime import date as Date
from typing import Any, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

TRUSTED_GRADES = ("A_CONFIRMED", "B_CONSISTENT")
STALENESS_DAYS = 400
BASIS_ORDER = {"WEIGHTED_AVG_PROXY": 0, "BALANCE_SHEET": 1, "DEI_COVER": 2}

# Written before the coverage was measured.  security_master_pit is True only if every one holds.
THRESHOLDS = {
    "identity_trusted_share_min_each_year_from_2015": 0.95,
    "identity_trusted_share_min_each_validation_fold": 0.95,
    "identity_contradicted_share_max": 0.02,
    "sic_share_of_identified_min": 0.95,
    "note": "shares / market-cap coverage gate size-dependent features and neutralisation separately (>= 0.90 in every fold)",
    "size_feature_share_min_each_validation_fold": 0.90,
}


def _ns(values: pd.Series) -> pd.Series:
    """Datetime keys of one resolution: merge_asof refuses ns against s."""
    return pd.to_datetime(values).astype("datetime64[ns]")


def attach_identity(rows: pd.DataFrame, identities: pd.DataFrame, grades: Sequence[str] = TRUSTED_GRADES) -> pd.DataFrame:
    """Add security_id, cik, identity_grade to rows(date, symbol).  Ticker windows come from price data."""
    ids = identities[["ticker", "security_id", "cik", "effective_from", "effective_to", "status"]]
    merged = rows[["date", "symbol"]].reset_index().merge(ids, left_on="symbol", right_on="ticker", how="left")
    live = (merged["effective_from"] <= merged["date"]) & (merged["effective_to"].isna() | (merged["date"] <= merged["effective_to"]))
    graded = merged[live].copy()
    graded["trusted"] = graded["status"].isin(grades)
    graded = graded.sort_values(["index", "trusted"], ascending=[True, False], kind="stable").drop_duplicates("index", keep="first")
    out = rows.copy()
    lookup = graded.set_index("index")
    out["security_id"] = lookup["security_id"].where(lookup["trusted"]).reindex(out.index)
    out["cik"] = lookup["cik"].where(lookup["trusted"]).reindex(out.index)
    out["identity_grade"] = lookup["status"].reindex(out.index)
    return out


def attach_classification(rows: pd.DataFrame, classification: pd.DataFrame) -> pd.DataFrame:
    """Add sic, ff12, ff17, ff48 in force on `date` (as filed), never beyond the evidence window."""
    known = rows[rows["cik"].notna()].copy()
    known["cik"] = known["cik"].astype("int64")
    left = known[["date", "cik"]].reset_index()
    left["date"] = _ns(left["date"])
    left = left.sort_values("date", kind="mergesort")
    right = classification.assign(cik=classification["cik"].astype("int64"))[
        ["cik", "effective_from", "effective_to", "evidenced_until", "sic", "ff12", "ff17", "ff48"]].copy()
    for column in ("effective_from", "effective_to", "evidenced_until"):
        right[column] = _ns(right[column])
    right = right.sort_values("effective_from", kind="mergesort")
    merged = pd.merge_asof(left, right, left_on="date", right_on="effective_from", by="cik", direction="backward")
    inside = merged["effective_to"].isna() & (merged["date"] <= merged["evidenced_until"] + pd.Timedelta(days=STALENESS_DAYS))
    inside |= merged["effective_to"].notna() & (merged["date"] <= merged["effective_to"])
    merged.loc[~inside, ["sic", "ff12", "ff17", "ff48"]] = np.nan
    merged = merged.set_index("index")
    out = rows.copy()
    for column in ("sic", "ff12", "ff17", "ff48"):
        out[column] = merged[column].reindex(out.index)
    return out


def split_factor_table(splits: pd.DataFrame) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Per symbol: sorted ex-dates and the running product of to/for factors."""
    out = {}
    frame = splits.copy()
    frame["ex"] = pd.to_datetime(frame["date"])
    frame["ratio"] = frame["to_factor"].astype(float) / frame["for_factor"].astype(float)
    for symbol, group in frame.sort_values("ex").groupby("symbol"):
        out[symbol] = (group["ex"].to_numpy("datetime64[ns]"), np.cumprod(group["ratio"].to_numpy()))
    return out


def cumulative_split(table: Mapping[str, tuple[np.ndarray, np.ndarray]], symbols: pd.Series, dates: pd.Series) -> np.ndarray:
    """Product of split ratios with ex-date <= each date (1.0 where the symbol has none)."""
    out = np.ones(len(symbols))
    stamps = pd.to_datetime(dates).to_numpy("datetime64[ns]")
    symbol_values = symbols.to_numpy()
    for symbol in np.unique(symbol_values):
        if symbol not in table:
            continue
        ex, cumulative = table[symbol]
        mask = symbol_values == symbol
        position = np.searchsorted(ex, stamps[mask], side="right")
        out[mask] = np.where(position > 0, cumulative[np.maximum(position - 1, 0)], 1.0)
    return out


def _shares_asof(rows: pd.DataFrame, shares: pd.DataFrame, split_table: Optional[Mapping[str, tuple[np.ndarray, np.ndarray]]],
                 staleness_days: int, lookback_days: int) -> pd.DataFrame:
    known = rows[rows["security_id"].notna()]
    left = known[["date", "security_id", "symbol"]].reset_index()
    left["date"] = _ns(left["date"])
    left["lookup"] = left["date"] - pd.Timedelta(days=lookback_days)   # a share count as it stood `lookback_days` earlier
    left = left.sort_values("lookup", kind="mergesort")
    right = shares.dropna(subset=["available_session"]).copy()
    right["available"] = _ns(right["available_session"])
    right["accepted_at"] = _ns(right["accepted_at"])
    right["period_end"] = _ns(right["period_end"])
    right["basis_order"] = right["basis"].map(BASIS_ORDER)
    right = right.sort_values(["available", "accepted_at", "period_end", "basis_order"], kind="mergesort")
    merged = pd.merge_asof(left, right[["security_id", "available", "accepted_at", "value", "basis", "multi_class_summed"]],
                           left_on="lookup", right_on="available", by="security_id", direction="backward",
                           tolerance=pd.Timedelta(days=staleness_days))
    merged["shares_age_days"] = (merged["lookup"] - merged["available"]).dt.days
    adjusted = merged["value"].to_numpy(dtype=float)
    if split_table:
        anchor = cumulative_split(split_table, merged["symbol"], merged["accepted_at"].fillna(merged["date"]))
        now = cumulative_split(split_table, merged["symbol"], merged["date"])
        adjusted = adjusted * (now / anchor)
    merged["shares_outstanding"] = adjusted
    return merged.set_index("index")


def attach_shares(rows: pd.DataFrame, shares: pd.DataFrame, split_table: Optional[Mapping[str, tuple[np.ndarray, np.ndarray]]] = None,
                  staleness_days: int = STALENESS_DAYS, lookback_days: int = 0) -> pd.DataFrame:
    """Add shares_outstanding (split-adjusted to `date`), shares_basis, shares_age_days.

    A share count is used from its filing's availability session.  It is restated to the decision date
    by splits whose ex-date falls after the filing was accepted (splits before acceptance are assumed
    already reflected in the reported count, per retroactive-restatement practice).

    Two tiers.  The primary tier (cover-page or balance-sheet count) is used wherever one is available in
    the staleness window.  The WEIGHTED_AVG_PROXY tier - a period's weighted-average share count, which is
    not a point-in-time count - is used **only** where the primary tier has nothing, and its basis is
    carried so no consumer can mistake it for an outstanding count.
    """
    primary = _shares_asof(rows, shares[shares["basis"] != "WEIGHTED_AVG_PROXY"], split_table, staleness_days, lookback_days)
    proxy_source = shares[shares["basis"] == "WEIGHTED_AVG_PROXY"]
    if len(proxy_source):
        proxy = _shares_asof(rows, proxy_source, split_table, staleness_days, lookback_days)
        gap = primary["shares_outstanding"].isna()
        for column in ("shares_outstanding", "basis", "shares_age_days", "multi_class_summed"):
            primary.loc[gap, column] = proxy.loc[gap.index[gap], column].to_numpy() if gap.any() else primary.loc[gap, column]
    out = rows.copy()
    for column in ("shares_outstanding", "basis", "shares_age_days", "multi_class_summed"):
        target = "shares_basis" if column == "basis" else column
        out[target] = primary[column].reindex(out.index)
    return out


# ── coverage ─────────────────────────────────────────────────────────────────

def label_periods(dates: pd.Series, folds: Sequence[Mapping[str, Any]]) -> pd.Series:
    """'fold_k' inside a validation window; 'train_only' before the first; 'between' otherwise."""
    stamps = pd.to_datetime(dates)
    labels = pd.Series("between", index=dates.index, dtype=object)
    labels[stamps < pd.Timestamp(folds[0]["validation_start"])] = "train_only"
    for fold in folds:
        inside = (stamps >= pd.Timestamp(fold["validation_start"])) & (stamps <= pd.Timestamp(fold["validation_end"]))
        labels[inside] = f"fold_{fold['index']}"
    return labels


def _share(mask: pd.Series) -> float:
    return float(mask.mean()) if len(mask) else float("nan")


def coverage_tables(panel: pd.DataFrame, folds: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Coverage by year and by period for a panel already carrying the attach_* columns and `market_cap`."""
    frame = panel.copy()
    frame["year"] = pd.to_datetime(frame["date"]).dt.year
    frame["period"] = label_periods(frame["date"], folds)
    frame["identity_trusted"] = frame["security_id"].notna()
    frame["identity_contradicted"] = frame["identity_grade"].isin(["X_CONTRADICTED"])
    frame["identity_partial"] = frame["identity_grade"].isin(["C_PARTIAL"])
    frame["no_periodic_filings"] = frame["identity_grade"].isin(["D_NO_PERIODIC_FILINGS"])
    frame["unresolved"] = frame["identity_grade"].isna()
    frame["cik_present"] = frame["cik"].notna()
    frame["sic_present"] = frame["sic"].notna()
    frame["shares_present"] = frame["shares_outstanding"].notna()
    frame["market_cap_present"] = frame["market_cap"].notna()

    def table(key: str) -> dict[str, Any]:
        out = {}
        for label, group in frame.groupby(key):
            trusted = group[group["identity_trusted"]]
            out[str(label)] = {
                "rows": int(len(group)), "symbols": int(group["symbol"].nunique()),
                "identity_trusted": _share(group["identity_trusted"]), "cik_present": _share(group["cik_present"]),
                "identity_contradicted": _share(group["identity_contradicted"]), "identity_partial": _share(group["identity_partial"]),
                "no_periodic_filings": _share(group["no_periodic_filings"]), "unresolved": _share(group["unresolved"]),
                "sic_of_identified": _share(trusted["sic_present"]) if len(trusted) else None,
                "shares_of_identified": _share(trusted["shares_present"]) if len(trusted) else None,
                "market_cap_of_identified": _share(trusted["market_cap_present"]) if len(trusted) else None,
                "shares_present": _share(group["shares_present"]), "market_cap_present": _share(group["market_cap_present"]),
            }
        return out

    return {"by_year": table("year"), "by_period": table("period")}


def security_master_status(coverage: Mapping[str, Any]) -> dict[str, Any]:
    """Apply THRESHOLDS mechanically.  `security_master_pit` is True only if all pass."""
    failures = []
    for year, row in coverage["by_year"].items():
        if int(year) >= 2015 and row["identity_trusted"] < THRESHOLDS["identity_trusted_share_min_each_year_from_2015"]:
            failures.append(f"year {year}: trusted identity {row['identity_trusted']:.3f} < {THRESHOLDS['identity_trusted_share_min_each_year_from_2015']}")
    for period, row in coverage["by_period"].items():
        if not period.startswith("fold_"):
            continue
        if row["identity_trusted"] < THRESHOLDS["identity_trusted_share_min_each_validation_fold"]:
            failures.append(f"{period}: trusted identity {row['identity_trusted']:.3f} < {THRESHOLDS['identity_trusted_share_min_each_validation_fold']}")
        if row["identity_contradicted"] > THRESHOLDS["identity_contradicted_share_max"]:
            failures.append(f"{period}: contradicted identity {row['identity_contradicted']:.3f} > {THRESHOLDS['identity_contradicted_share_max']}")
        if row["sic_of_identified"] is not None and row["sic_of_identified"] < THRESHOLDS["sic_share_of_identified_min"]:
            failures.append(f"{period}: SIC of identified {row['sic_of_identified']:.3f} < {THRESHOLDS['sic_share_of_identified_min']}")
    size_ok = all((row["market_cap_of_identified"] or 0) >= THRESHOLDS["size_feature_share_min_each_validation_fold"]
                  for period, row in coverage["by_period"].items() if period.startswith("fold_"))
    return {"security_master_pit": not failures, "failures": failures, "size_features_allowed": bool(size_ok and not failures),
            "neutralization_allowed": bool(size_ok and not failures), "thresholds": THRESHOLDS}
