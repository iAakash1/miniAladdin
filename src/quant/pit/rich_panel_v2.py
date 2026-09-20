"""Rich PIT v2: the frozen EXP-011 block, unchanged, plus an incremental block admitted only through the frozen gates.

Nothing in `rich_panel.py`, `pit_fundamentals.py` or `pit_coverage.py` (the EXP-011 method files) is modified: this module imports them.

The 76 EXP-011 feature columns are **copied** from the frozen panel, never recomputed, so they cannot change.  The incremental block is
whatever `docs/DATA_COMPLETION_GATE_2026.md` admits:

* SIZE/INDUSTRY controls - the seven `CONTROL_FEATURES` withheld in EXP-011 - only if `security_master_pit` is true and the domestic
  market-cap gate passes (the old rule, unchanged);
* FOREIGN-FILER completion - `fc_*` currency-neutral characteristics from 20-F/40-F filings, ranked against the same-date *domestic*
  reference distribution so no domestic rank moves - only if its own coverage gate passes.

Outcome-blind: nothing here reads a return, a label statistic or a model result.
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
from src.quant.pit import rich_panel as R

V2_VERSION = "rich-pit-v2"
FOREIGN_FEATURES = (
    "roa", "roe", "operating_profitability", "cash_profitability", "gross_margin", "operating_margin", "net_margin",
    "cash_flow_margin", "asset_turnover", "asset_growth", "capex_to_assets", "accruals", "cash_flow_quality",
    "liabilities_to_assets", "current_ratio", "cash_to_assets", "revenue_growth", "earnings_growth",
)
FOREIGN_COLUMNS = tuple(f"fc_{n}_xs" for n in FOREIGN_FEATURES)
CONTROL_COLUMNS = tuple(f"{n}_xs" for n in R.CONTROL_FEATURES)
OLD_BLOCK = tuple(R.BASELINE_FEATURES) + tuple(f"{n}_xs" for n in R.NEW_FEATURES)
MIN_REFERENCE = 10
# Frozen in docs/DATA_COMPLETION_GATE_2026.md before any coverage was measured.
GATE = {"foreign_min_share_with_columns": 0.50, "foreign_min_columns_present": 5, "foreign_min_securities_per_fold": 8,
        "foreign_min_column_coverage": 0.30, "minimum_incremental_columns": 5}


def rank_against_reference(values: pd.Series, dates: pd.Series, reference: pd.Series, reference_dates: pd.Series) -> pd.Series:
    """Percentile of each foreign value within the same-date domestic reference values, scaled to [-1, 1].

    (count(reference < v) + 0.5 * count(reference == v)) / n, then *2 - 1.  A date with fewer than MIN_REFERENCE reference values is missing.
    The reference is never altered, so no domestic rank changes.
    """
    out = pd.Series(np.nan, index=values.index, dtype=float)
    ref = pd.DataFrame({"d": reference_dates, "v": pd.to_numeric(reference, errors="coerce")}).dropna()
    grouped = {d: np.sort(g["v"].to_numpy()) for d, g in ref.groupby("d")}
    for day, index in values.dropna().groupby(dates[values.notna()]).groups.items():
        sample = grouped.get(day)
        if sample is None or len(sample) < MIN_REFERENCE:
            continue
        v = values.loc[index].to_numpy(dtype=float)
        below, at_or_below = np.searchsorted(sample, v, side="left"), np.searchsorted(sample, v, side="right")
        out.loc[index] = ((below + 0.5 * (at_or_below - below)) / len(sample)) * 2.0 - 1.0
    return out


def foreign_block(frame: pd.DataFrame, foreign_snapshots: pd.DataFrame, domestic_snapshots: pd.DataFrame,
                  domestic_raw: pd.DataFrame, staleness_days: int = F.STALE_SNAPSHOT_DAYS) -> pd.DataFrame:
    """The `fc_*_xs` columns for `frame` (date, cik, ...).  Non-null only where the latest available periodic snapshot is a foreign annual report."""
    known = frame[frame["cik"].notna()]
    foreign = F.attach_snapshot(known, foreign_snapshots, staleness_days) if len(foreign_snapshots) else pd.DataFrame(index=known.index)
    domestic = F.attach_snapshot(known, domestic_snapshots, staleness_days) if len(domestic_snapshots) else pd.DataFrame(index=known.index)
    foreign_available = foreign["available"] if "available" in foreign else pd.Series(pd.NaT, index=known.index)
    domestic_available = domestic["available"] if "available" in domestic else pd.Series(pd.NaT, index=known.index)
    latest_is_foreign = foreign_available.notna() & (domestic_available.isna() | (foreign_available > domestic_available))
    out = pd.DataFrame(np.nan, index=frame.index, columns=list(FOREIGN_COLUMNS), dtype=float)
    if not latest_is_foreign.any():
        return out
    rows = foreign[latest_is_foreign]
    raw_columns = [c for c in rows.columns if c not in ("date", "cik", "available", "accession", "form", "fp", "report_period", "accepted_at", "available_session")]
    snapshot = pd.DataFrame({c: rows[c] for c in raw_columns})
    characteristics = F.snapshot_characteristics(snapshot)
    dates = pd.to_datetime(frame.loc[rows.index, "date"])
    for name in FOREIGN_FEATURES:
        ranked = rank_against_reference(characteristics[name], dates, domestic_raw[name], pd.to_datetime(domestic_raw["date"]))
        out.loc[rows.index, f"fc_{name}_xs"] = ranked
    return out


def foreign_gate(coverage: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the frozen foreign-completion gate to measured per-fold coverage.  Pure function of the numbers."""
    failures, dropped = [], []
    folds = coverage["folds"]
    for fold, row in folds.items():
        if row["share_with_min_columns"] < GATE["foreign_min_share_with_columns"]:
            failures.append(f"{fold}: {row['share_with_min_columns']:.3f} of foreign trusted name-dates have >= {GATE['foreign_min_columns_present']} columns (< {GATE['foreign_min_share_with_columns']})")
        if row["securities"] < GATE["foreign_min_securities_per_fold"]:
            failures.append(f"{fold}: {row['securities']} foreign securities (< {GATE['foreign_min_securities_per_fold']})")
    for column in FOREIGN_COLUMNS:
        if any(row["column_coverage"].get(column, 0.0) < GATE["foreign_min_column_coverage"] for row in folds.values()):
            dropped.append(column)
    admitted = [] if failures else [c for c in FOREIGN_COLUMNS if c not in dropped]
    return {"passed": not failures, "failures": failures, "dropped_columns": dropped, "admitted_columns": admitted, "gate": GATE}


def foreign_coverage(frame: pd.DataFrame, block: pd.DataFrame, regimes: pd.Series, folds: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Per validation fold, over foreign (regime FOREIGN_20F_40F) trusted name-dates: share with >= K columns, securities, and per-column coverage."""
    periods = C.label_periods(frame["date"], folds)
    foreign_rows = frame["security_id"].notna() & frame["cik"].map(regimes).eq("FOREIGN_20F_40F")
    present = block.notna()
    out = {}
    for fold in sorted(p for p in periods.unique() if str(p).startswith("fold_")):
        mask = foreign_rows & (periods == fold)
        n = int(mask.sum())
        with_columns = present[mask].sum(axis=1) >= GATE["foreign_min_columns_present"]
        has_value = present[mask].any(axis=1)
        out[fold] = {"name_dates": n, "share_with_min_columns": float(with_columns.mean()) if n else 0.0,
                     "securities": int(frame.loc[mask & present.any(axis=1), "security_id"].nunique()),
                     "column_coverage": {c: float(present.loc[mask, c].mean()) if n else 0.0 for c in FOREIGN_COLUMNS},
                     "any_value_share": float(has_value.mean()) if n else 0.0}
    return {"folds": out}


INDUSTRY_SOURCES = {"industry_rel_roa": "roa", "industry_rel_gross_profitability": "gross_profitability", "industry_rel_book_to_market": "book_to_market",
                    "industry_rel_operating_margin": "operating_margin", "industry_rel_asset_growth": "asset_growth", "industry_rel_earnings_yield": "earnings_yield"}


def control_block(frame: pd.DataFrame, ff12: pd.Series) -> pd.DataFrame:
    """The seven withheld CONTROL columns, with the industry taken from the point-in-time attach (`pit_coverage_v4`), never from a rule that
    looks at later filings.  `frame` carries date, symbol, log_market_cap and the raw characteristics; same definitions as EXP-011's withheld controls."""
    raw = pd.DataFrame({"date": frame["date"], "symbol": frame["symbol"], "log_market_cap": frame["log_market_cap"]}, index=frame.index)
    for name, source in INDUSTRY_SOURCES.items():
        raw[name] = R.industry_relative(frame[source], ff12, frame["date"])
    members = {day: set(group["symbol"]) for day, group in raw.groupby("date")}
    ranked = xs.cross_sectional_frame(raw, list(R.CONTROL_FEATURES), universe_for=members, method="rank")
    return ranked[list(CONTROL_COLUMNS)]


def control_gate(status: Mapping[str, Any], domestic_market_cap_by_fold: Mapping[str, float]) -> dict[str, Any]:
    """The old rule, unchanged: security_master_pit true AND market cap >= 0.90 of identified domestic names in every fold."""
    floor = C.THRESHOLDS["size_feature_share_min_each_validation_fold"]
    market_ok = all(v >= floor for v in domestic_market_cap_by_fold.values())
    return {"passed": bool(status["security_master_pit"] and market_ok), "security_master_pit": bool(status["security_master_pit"]),
            "market_cap_gate_passed": bool(market_ok), "admitted_columns": list(CONTROL_COLUMNS) if status["security_master_pit"] and market_ok else []}


def block_hash(panel: pd.DataFrame, columns: Sequence[str]) -> str:
    ordered = panel[["date", "symbol", *columns]].copy()
    ordered["date"] = pd.to_datetime(ordered["date"]).dt.strftime("%Y-%m-%d")
    ordered = ordered.sort_values(["date", "symbol"], kind="mergesort")
    return hashlib.sha256(pd.util.hash_pandas_object(ordered, index=False).to_numpy().tobytes()).hexdigest()


def old_block_invariance(frozen: pd.DataFrame, v2: pd.DataFrame, columns: Sequence[str] = OLD_BLOCK) -> dict[str, Any]:
    """Value-by-value comparison of the old block on the common (date, symbol) rows; NaN equals NaN, nothing else does."""
    key = ["date", "symbol"]
    left = frozen[key + list(columns)].assign(date=lambda d: pd.to_datetime(d["date"])).set_index(key).sort_index()
    right = v2[key + list(columns)].assign(date=lambda d: pd.to_datetime(d["date"])).set_index(key).sort_index()
    common = left.index.intersection(right.index)
    a, b = left.loc[common].to_numpy(dtype=float), right.loc[common].to_numpy(dtype=float)
    changed = ~((a == b) | (np.isnan(a) & np.isnan(b)))
    return {"common_rows": int(len(common)), "rows_only_in_frozen": int(len(left) - len(common)), "rows_only_in_v2": int(len(right) - len(common)),
            "cells_compared": int(a.size), "changed_cells": int(changed.sum()), "columns": len(columns),
            "old_block_hash_frozen": block_hash(frozen, columns), "old_block_hash_v2": block_hash(v2, columns)}
