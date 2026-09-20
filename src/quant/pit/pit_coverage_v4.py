"""Point-in-time attach functions for the data-completion cycle (new module: the EXP-011 method files are not modified).

`pit_coverage.attach_classification` decides whether an industry code is stale using the CIK's *last filing overall*.  For an open-ended interval
that lets a filing accepted years after a row's date make that row's value valid - a small look-ahead that the source-truncation test exposes
(build with data through T, and with everything: a row dated before T must not change).  It affected only the industry controls that EXP-011
withheld, so EXP-011 is unaffected; here the corrected rule is used everywhere.

Corrected rule: a row's industry code is the one in force by the latest SIC-change filing accepted <= the row's date, and it is valid only if the
CIK's latest filing accepted <= the row's date is at most 400 days old.
"""

from __future__ import annotations

from typing import Mapping, Optional

import numpy as np
import pandas as pd

from src.quant.pit import pit_coverage as C

INDUSTRY_COLUMNS = ("sic", "ff12", "ff17", "ff48")


def attach_classification_pit(rows: pd.DataFrame, classification: pd.DataFrame, filings: pd.DataFrame,
                              staleness_days: int = C.STALENESS_DAYS) -> pd.DataFrame:
    """Add sic, ff12, ff17, ff48 using only filings accepted on or before each row's date."""
    known = rows[rows["cik"].notna()]
    left = known[["date", "cik"]].reset_index()
    left["date"] = C._ns(left["date"])
    left["cik"] = left["cik"].astype("int64")
    left = left.sort_values("date", kind="mergesort")
    right = classification.assign(cik=classification["cik"].astype("int64"))[["cik", "effective_from", "sic", "ff12", "ff17", "ff48"]].copy()
    right["effective_from"] = C._ns(right["effective_from"])
    merged = pd.merge_asof(left, right.sort_values("effective_from", kind="mergesort"), left_on="date", right_on="effective_from", by="cik", direction="backward")
    seen = filings[["cik", "accepted_at"]].copy()
    seen["cik"] = seen["cik"].astype("int64")
    seen["accepted_at"] = C._ns(seen["accepted_at"])
    seen = seen.sort_values("accepted_at", kind="mergesort")
    merged = pd.merge_asof(merged.sort_values("date", kind="mergesort"), seen.rename(columns={"accepted_at": "last_filing"}),
                           left_on="date", right_on="last_filing", by="cik", direction="backward")
    stale = merged["last_filing"].isna() | ((merged["date"] - merged["last_filing"]) > pd.Timedelta(days=staleness_days))
    merged.loc[stale, list(INDUSTRY_COLUMNS)] = np.nan
    merged = merged.set_index("index")
    out = rows.copy()
    for column in INDUSTRY_COLUMNS:
        out[column] = merged[column].reindex(out.index)
    return out


def apply_foreign_policy(panel: pd.DataFrame, regimes: Mapping[int, str]) -> pd.DataFrame:
    """Definition D2: shares, share basis and market capitalisation are undefined for foreign filers (ADS ratio and FX are not point-in-time)."""
    out = panel.copy()
    out["foreign"] = out["cik"].map(regimes).eq("FOREIGN_20F_40F")
    for column in ("shares_outstanding", "shares_basis", "shares_age_days", "multi_class_summed"):
        if column in out:
            out[column] = out[column].where(~out["foreign"])
    if "close" in out:
        out["market_cap"] = out["shares_outstanding"] * out["close"]
    return out
