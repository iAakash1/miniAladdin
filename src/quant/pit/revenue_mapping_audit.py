"""Outcome-blind integrity audit of the frozen EXP-011 revenue mapping.

This module never reads a target or return column.  It builds a parallel
shadow view; the frozen SEC v3 store, rich panel, and EXP-011 outputs remain
immutable.
"""

from __future__ import annotations

import glob
import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from src.quant.features import pit_fundamentals as F
from src.quant.pit import pit_coverage as C
from src.quant.pit import rich_panel as R
from src.quant.pit import sec_facts as S
from src.quant.pit.rich_panel_build import FACT_COLUMNS
from src.quant.study import exp009b, exp011

REVENUE_TAGS = tuple(tag for family, tag in S.FACTS["revenue"].tags if family == "us-gaap")
GROUP_KEY = ("cik", "accession", "period_end", "qtrs")
EXPLICIT_TOTAL = re.compile(r"\b(?:total|net)\s+(?:operating\s+)?(?:revenue|revenues|sales)\b", re.I)

# Derived from the executable formulas in pit_fundamentals.py and rich_panel.py.
REVENUE_DEPENDENCIES: dict[str, str] = {
    "gross_profitability_xs": "conditional: gross profit falls back to revenue minus cost of revenue",
    "gross_margin_xs": "revenue denominator; conditional gross-profit fallback",
    "operating_margin_xs": "revenue denominator",
    "net_margin_xs": "revenue denominator",
    "cash_flow_margin_xs": "revenue denominator",
    "ebitda_margin_xs": "revenue denominator",
    "asset_turnover_xs": "revenue numerator",
    "capex_to_revenue_xs": "revenue denominator",
    "gross_margin_stability_xs": "rolling history of gross margin",
    "revenue_growth_xs": "current and year-ago revenue",
    "gross_profit_growth_xs": "conditional current gross-profit fallback uses revenue",
    "sales_yield_xs": "revenue divided by market capitalisation",
    "gross_profit_to_ev_xs": "conditional gross-profit fallback uses revenue",
    "sales_to_ev_xs": "revenue divided by enterprise value",
}


def _hash_frame(frame: pd.DataFrame, columns: Iterable[str]) -> str:
    ordered = frame[list(columns)].astype(str).sort_values(list(columns), kind="stable")
    return hashlib.sha256(pd.util.hash_pandas_object(ordered, index=False).to_numpy().tobytes()).hexdigest()


def load_population(root: Path) -> pd.DataFrame:
    """Read identifiers, inputs, and frozen features only.  Outcome columns are never loaded."""
    columns = ["date", "symbol", "cik", "close", "dollar_volume", "in_universe", *exp011.feature_list("rich")]
    frame = pd.read_parquet(root / exp011.RICH_PANEL, columns=columns)
    frame["date"] = pd.to_datetime(frame["date"])
    assert len(frame) == exp011.RICH_ROWS
    manifest = json.loads((root / exp011.RICH_MANIFEST).read_text())
    assert manifest["dataset_id"] == exp011.RICH_DATASET_ID
    assert manifest["content_hash"] == exp011.RICH_CONTENT_HASH
    assert manifest["feature_hash"] == exp011.RICH_FEATURE_HASH
    return frame


def load_population_facts(root: Path, ciks: set[int]) -> pd.DataFrame:
    parts = []
    for path in sorted(glob.glob(str(root / "data/curated/sec_v3/facts-*.parquet"))):
        frame = pd.read_parquet(path, columns=FACT_COLUMNS + ["tag", "source_archive"])
        part = frame[frame["cik"].isin(ciks)]
        if len(part):
            parts.append(part)
    return pd.concat(parts, ignore_index=True)


def _presentation_evidence(root: Path, candidates: pd.DataFrame) -> dict[tuple[str, str], dict[str, Any]]:
    """Income-statement presentation evidence for candidate accessions/tags."""
    wanted = candidates.groupby("source_archive")["accession"].agg(lambda x: set(map(str, x)))
    evidence: dict[tuple[str, str], dict[str, Any]] = {}
    for archive_name, accessions in wanted.items():
        path = root / "data/raw/sec" / str(archive_name)
        with zipfile.ZipFile(path) as archive:
            member = next(m for m in archive.namelist() if Path(m).name.lower() == "pre.txt")
            with archive.open(member) as handle:
                pre = pd.read_csv(handle, sep="\t", dtype=str, low_memory=False)
        pre.columns = pre.columns.str.lower()
        pre = pre[pre["adsh"].isin(accessions) & pre["tag"].isin(REVENUE_TAGS)]
        for (accession, tag), rows in pre.groupby(["adsh", "tag"], sort=False):
            is_rows = rows[rows["stmt"].eq("IS")]
            labels = sorted(set(is_rows["plabel"].dropna().astype(str)))
            lines = sorted(set(pd.to_numeric(is_rows["line"], errors="coerce").dropna().astype(int)))
            evidence[(str(accession), str(tag))] = {
                "income_statement": bool(len(is_rows)), "labels": labels, "lines": lines,
                "explicit_total": any(EXPLICIT_TOTAL.search(label) for label in labels),
            }
    return evidence


def reconcile_filings(root: Path, facts: pd.DataFrame) -> tuple[pd.DataFrame, dict[tuple[Any, ...], int]]:
    revenue = facts[
        (facts["canonical_fact"] == "revenue")
        & facts["form"].astype(str).str.startswith("10-K")
        & (facts["qtrs"] == 4)
        & facts["tag"].isin(REVENUE_TAGS)
    ].copy()
    grouped = revenue.groupby(list(GROUP_KEY), dropna=False)
    candidate_keys = [key for key, rows in grouped if rows["tag"].nunique() > 1]
    candidates = revenue.set_index(list(GROUP_KEY)).loc[candidate_keys].reset_index() if candidate_keys else revenue.iloc[0:0]
    presentations = _presentation_evidence(root, candidates) if len(candidates) else {}
    records: list[dict[str, Any]] = []
    selected_rows: dict[tuple[Any, ...], int] = {}

    for key in candidate_keys:
        rows = grouped.get_group(key).sort_values(["tag_priority", "tag"], kind="stable")
        per_tag = rows.groupby("tag", sort=False)["value"].agg(lambda v: sorted(set(map(float, v))))
        current = rows.iloc[0]
        current_value = float(current["value"])
        item: dict[str, Any] = {
            **dict(zip(GROUP_KEY, key)), "current_tag": str(current["tag"]), "current_value": current_value,
            "candidate_values": {str(tag): values for tag, values in per_tag.items()},
            "presentation": {str(tag): presentations.get((str(key[1]), str(tag)), {
                "income_statement": False, "labels": [], "lines": [], "explicit_total": False,
            }) for tag in per_tag.index},
        }
        if any(len(values) != 1 for values in per_tag):
            item.update(status="REVENUE_AMBIGUOUS", reason="DUPLICATE_TAG_CONFLICT", selected_tag=None, corrected_value=None)
        elif len({values[0] for values in per_tag}) == 1:
            item.update(status="CURRENT_SUPPORTED", reason="CANDIDATES_VALUE_EQUIVALENT", selected_tag=str(current["tag"]), corrected_value=current_value)
        else:
            explicit = [tag for tag in per_tag.index if item["presentation"][str(tag)]["explicit_total"]]
            on_statement = [tag for tag in per_tag.index if item["presentation"][str(tag)]["income_statement"]]
            if len(explicit) == 1:
                chosen, reason = explicit[0], "UNIQUE_EXPLICIT_TOTAL_IS_LABEL"
            elif len(on_statement) == 1:
                chosen, reason = on_statement[0], "UNIQUE_INCOME_STATEMENT_PRESENTATION"
            else:
                chosen, reason = None, "MULTIPLE_PLAUSIBLE_TOTALS" if on_statement else "NO_INCOME_STATEMENT_PRESENTATION"
            if chosen is None:
                item.update(status="REVENUE_AMBIGUOUS", reason=reason, selected_tag=None, corrected_value=None)
            else:
                corrected_value = float(per_tag.loc[chosen][0])
                status = "CURRENT_SUPPORTED" if corrected_value == current_value else "CORRECTED_CANDIDATE"
                item.update(status=status, reason=reason, selected_tag=str(chosen), corrected_value=corrected_value)
                picked = rows[(rows["tag"] == chosen) & (rows["value"].astype(float) == corrected_value)].index[0]
                selected_rows[key] = int(picked)
        item["corrected_to_frozen_ratio"] = (
            None if item["corrected_value"] is None or current_value == 0 else float(item["corrected_value"] / current_value)
        )
        records.append(item)
    return pd.DataFrame(records), selected_rows


def corrected_fact_view(facts: pd.DataFrame, reconciliation: pd.DataFrame, selected_rows: dict[tuple[Any, ...], int]) -> pd.DataFrame:
    shadow = facts.copy()
    for row in reconciliation.itertuples(index=False):
        key = tuple(getattr(row, column) for column in GROUP_KEY)
        mask = pd.Series(True, index=shadow.index)
        for column, value in zip(GROUP_KEY, key):
            mask &= shadow[column].eq(value)
        mask &= shadow["canonical_fact"].eq("revenue")
        if row.status == "REVENUE_AMBIGUOUS":
            shadow = shadow[~mask]
        elif row.status == "CORRECTED_CANDIDATE":
            shadow.loc[mask, "tag_priority"] = shadow.loc[mask, "tag_priority"].astype(int) + 10
            selected = selected_rows[key]
            if selected in shadow.index:
                shadow.loc[selected, "tag_priority"] = -1
    return shadow.reset_index(drop=True)


def _changed(a: pd.DataFrame, b: pd.DataFrame, columns: list[str], tolerance: float = 1e-12) -> pd.DataFrame:
    av, bv = a[columns].to_numpy(float), b[columns].to_numpy(float)
    return pd.DataFrame(~((np.isclose(av, bv, rtol=0.0, atol=tolerance, equal_nan=True))), columns=columns, index=a.index)


def _distribution(mask: pd.Series, groups: pd.Series) -> dict[str, dict[str, float | int]]:
    out = {}
    affected_values = np.asarray(mask, dtype=bool)
    group_values = np.asarray(groups)
    for group in sorted(pd.Series(group_values).dropna().unique()):
        rows = group_values == group
        affected = int(affected_values[rows].sum())
        out[str(group)] = {"rows": int(rows.sum()), "affected": affected, "share": float(affected / rows.sum())}
    return out


def run(root: Path) -> dict[str, Any]:
    root = Path(root)
    frozen = load_population(root)
    ciks = set(frozen["cik"].dropna().astype(int))
    facts = load_population_facts(root, ciks)
    reconciliation, selected = reconcile_filings(root, facts)
    shadow_facts = corrected_fact_view(facts, reconciliation, selected)

    snapshot_cache = root / "data/research/derived/exp011_revenue_audit_original_snapshots.parquet"
    if snapshot_cache.exists():
        original_snapshots = pd.read_parquet(snapshot_cache)
    else:
        original_snapshots = F.build_snapshots(facts)
        original_snapshots.to_parquet(snapshot_cache, compression="zstd", index=False)
    # Only affected filers can differ.  Reuse the exact original snapshots for
    # every other CIK; this changes no semantics and avoids rebuilding hundreds
    # of unrelated filing histories a second time.
    affected_ciks = set(reconciliation.loc[
        reconciliation["status"].isin(["CORRECTED_CANDIDATE", "REVENUE_AMBIGUOUS"]), "cik"
    ].astype(int))
    corrected_affected = F.build_snapshots(shadow_facts[shadow_facts["cik"].isin(affected_ciks)])
    corrected_snapshots = pd.concat([
        original_snapshots[~original_snapshots["cik"].isin(affected_ciks)], corrected_affected,
    ], ignore_index=True)
    base_columns = ["date", "symbol", "close", "dollar_volume", "in_universe", *R.BASELINE_FEATURES]
    base = frozen[base_columns].copy()
    tables = root / "data/curated/security_master_v3"
    identities = pd.read_parquet(tables / "security_identity_interval.parquet")
    classification = pd.read_parquet(tables / "security_classification_interval.parquet")
    shares = pd.read_parquet(tables / "shares_fact_vintage.parquet")
    splits = C.split_factor_table(pd.read_parquet(root / "data/research/raw/dolthub_stocks_split/part-all.parquet"))
    kwargs = {"identities": identities, "classification": classification, "shares": shares,
              "split_table": splits, "controls_allowed": False}
    reproduced = R.build_panel(base, snapshots=original_snapshots, **kwargs)
    corrected = R.build_panel(base, snapshots=corrected_snapshots, **kwargs)
    rich_columns = list(exp011.RICH_FEATURES)
    reproduction_change = _changed(frozen, reproduced, rich_columns)
    if int(reproduction_change.to_numpy().sum()) != 0:
        raise AssertionError(f"frozen panel reproduction changed {int(reproduction_change.to_numpy().sum())} cells")

    features = exp011.feature_list("rich")
    corrected_features = frozen[features].copy()
    corrected_features[rich_columns] = corrected[rich_columns]
    changed = _changed(frozen, corrected_features, features)
    abs_change = (corrected_features[features] - frozen[features]).abs()
    row_affected = changed.any(axis=1)

    # Snapshot impact excludes rank propagation to other same-date names.
    attach_rows = frozen[["date", "cik"]]
    original_attached = F.attach_snapshot(attach_rows, original_snapshots, F.STALE_SNAPSHOT_DAYS)
    corrected_attached = F.attach_snapshot(attach_rows, corrected_snapshots, F.STALE_SNAPSHOT_DAYS)
    snapshot_columns = [c for c in ("revenue_ttm", "revenue_ttm_1y", "gross_margin_std8")
                        if c in original_attached and c in corrected_attached]
    attached_change = _changed(original_attached, corrected_attached, snapshot_columns).any(axis=1)
    snapshot_affected = pd.Series(False, index=frozen.index)
    snapshot_affected.loc[attached_change.index] = attached_change.to_numpy(dtype=bool)

    folds = [fold.as_dict() for fold in exp009b.recorded_plan(root).folds]
    fold_labels = C.label_periods(frozen["date"], folds)
    years = frozen["date"].dt.year
    regimes = pd.read_parquet(root / "data/curated/security_master_v4/security_identity_interval.parquet")
    regime_map = regimes.dropna(subset=["cik"]).drop_duplicates("cik").set_index("cik")["filer_regime"]
    row_regime = frozen["cik"].map(regime_map).fillna("UNRESOLVED")

    by_feature = {}
    for feature in features:
        mask = changed[feature]
        if not mask.any():
            continue
        values = abs_change.loc[mask, feature].dropna()
        by_feature[feature] = {
            "count": int(mask.sum()), "share": float(mask.mean()),
            "median_absolute_change": None if values.empty else float(values.median()),
            "p95_absolute_change": None if values.empty else float(values.quantile(0.95)),
            "max_absolute_change": None if values.empty else float(values.max()),
            "same_date_ranks_changed": int(mask.sum()),
            "revenue_dependency": REVENUE_DEPENDENCIES.get(feature),
        }

    corrected_rows = reconciliation[reconciliation["status"].eq("CORRECTED_CANDIDATE")]
    ambiguous_rows = reconciliation[reconciliation["status"].eq("REVENUE_AMBIGUOUS")]
    classification = "UNRESOLVED_MAPPING_IMPACT" if len(ambiguous_rows) else "LOCALIZED_SEMANTIC_MAPPING_ISSUE"
    ratios = corrected_rows["corrected_to_frozen_ratio"].dropna().astype(float)
    reason_counts = Counter(reconciliation["reason"])
    return {
        "audit_id": "EXP-011-REVENUE-MAPPING-IMPACT-V1",
        "status": "COMPLETE_OUTCOME_BLIND",
        "classification": classification,
        "scientific_action": "FORMAL_REPLICATION_DECISION_REQUIRED_BEFORE_FINAL_CANDIDATE_FREEZE" if classification == "UNRESOLVED_MAPPING_IMPACT" else "REVIEW_MEASURED_SCOPE",
        "firewall": {"target_columns_loaded": False, "returns_read": False, "models_fit": 0, "portfolio_runs": 0,
                     "holdout_touched": False, "exp011_outputs_modified": False},
        "frozen_population": {"dataset_id": exp011.RICH_DATASET_ID, "rows": int(len(frozen)), "ciks": len(ciks),
                              "date_min": str(frozen["date"].min().date()), "date_max": str(frozen["date"].max().date()),
                              "features": len(features), "feature_hash": exp011.RICH_FEATURE_HASH},
        "reconciliation": {
            "multi_candidate_contexts": int(len(reconciliation)),
            "multi_candidate_filings": int(reconciliation["accession"].nunique()),
            "corrected_disagreement_contexts": int(len(corrected_rows)),
            "corrected_disagreement_filings": int(corrected_rows["accession"].nunique()),
            "affected_ciks": int(reconciliation.loc[reconciliation["status"].isin(["CORRECTED_CANDIDATE", "REVENUE_AMBIGUOUS"]), "cik"].nunique()),
            "ambiguous_contexts": int(len(ambiguous_rows)),
            "ambiguous_filings": int(ambiguous_rows["accession"].nunique()), "reason_counts": dict(sorted(reason_counts.items())),
            "corrected_to_frozen_ratio": {"count": int(len(ratios)), "median": None if ratios.empty else float(ratios.median()),
                                               "p05": None if ratios.empty else float(ratios.quantile(.05)),
                                               "p95": None if ratios.empty else float(ratios.quantile(.95)),
                                               "min": None if ratios.empty else float(ratios.min()),
                                               "max": None if ratios.empty else float(ratios.max())},
            "records": reconciliation.replace({np.nan: None}).to_dict("records"),
        },
        "snapshot_impact": {
            "affected_name_dates": int(snapshot_affected.sum()), "share": float(snapshot_affected.mean()),
            "by_fold": _distribution(snapshot_affected, fold_labels), "by_year": _distribution(snapshot_affected, years),
            "by_regime": _distribution(snapshot_affected, row_regime),
        },
        "feature_impact": {
            "common_rows": int(len(frozen)), "features_examined": len(features),
            "changed_cells": int(changed.to_numpy().sum()), "affected_name_dates_including_rank_propagation": int(row_affected.sum()),
            "affected_features": len(by_feature), "by_feature": by_feature,
            "changed_cells_by_fold": {k: int(changed.loc[fold_labels.eq(k)].to_numpy().sum()) for k in sorted(fold_labels.unique())},
            "changed_cells_by_year": {str(y): int(changed.loc[years.eq(y)].to_numpy().sum()) for y in sorted(years.unique())},
        },
        "dependency_trace": REVENUE_DEPENDENCIES,
        "integrity": {
            "frozen_reproduction_changed_cells": int(reproduction_change.to_numpy().sum()),
            "shadow_feature_hash": _hash_frame(pd.concat([frozen[["date", "symbol"]], corrected_features], axis=1), ["date", "symbol", *features]),
            "reconciliation_hash": _hash_frame(reconciliation, list(reconciliation.columns)),
        },
    }
