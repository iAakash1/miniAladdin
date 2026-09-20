"""Manual audit of issuer-periods for rich PIT v2.

Selection is frozen before any trace is read and depends on nothing but identifiers: within each stratum candidates are ordered by
SHA-256("exp012-manual-audit-v1:" + cik + ":" + accession) and the first three not already chosen are audited.  No return, label,
feature value or model output participates in the choice.

Each selected filing is traced source -> curated -> snapshot -> panel with code that does not import the curation functions: the raw
values are read straight from the SEC archive's `num.txt` with their own (deliberately plain) tag lists, the availability session is
re-derived from the acceptance timestamp, and the recomputed ratios are compared with what the pipeline stored.
"""

from __future__ import annotations

import hashlib
import zipfile
from datetime import date as Date, time as Clock, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

AUDIT_VERSION = "exp012-manual-audit-v1"
PER_STRATUM = 3
MARKET_CLOSE = Clock(16, 0)
RELATIVE_TOLERANCE = 1e-9

# Frozen order: hard cases first, so an issuer-period that qualifies for several strata is audited under the hardest one.
STRATA = (
    "AMENDED_ANNUAL_FILING", "SUCCESSION_OR_TICKER_REUSE", "EXITING_SECURITY", "MIXED_FILER_REGIME", "NON_USD_REPORTING_CURRENCY",
    "IFRS_20F", "US_GAAP_20F", "FORM_40F", "MULTI_CLASS_SHARES", "SHARES_PROXY_TIER", "IDENTITY_GRADE_B_OR_C", "FORMER_NAME", "DOMESTIC_10K_GRADE_A",
)
RAW_TAGS = {
    "assets": ("Assets",),
    "net_income": ("NetIncomeLoss", "ProfitLoss", "ProfitLossAttributableToOwnersOfParent"),
    "revenue": ("Revenues", "Revenue", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "RevenueFromContractsWithCustomers"),
}
FLOW_QTRS = {"assets": "0", "net_income": "4", "revenue": "4"}


def selection_key(cik: int, accession: str) -> str:
    return hashlib.sha256(f"{AUDIT_VERSION}:{int(cik)}:{accession}".encode()).hexdigest()


def select(candidates: pd.DataFrame, per_stratum: int = PER_STRATUM, strata: Sequence[str] = STRATA) -> pd.DataFrame:
    """`candidates`: rows (stratum, cik, accession).  Deterministic, identifier-only; an item is audited once, under its first stratum in STRATA order."""
    ranked = candidates.assign(sel_key=[selection_key(c, a) for c, a in zip(candidates["cik"], candidates["accession"])]).sort_values(["sel_key"], kind="mergesort")
    chosen, seen = [], set()
    for stratum in strata:
        pool = ranked[ranked["stratum"] == stratum]
        taken = 0
        for row in pool.itertuples(index=False):
            if (row.cik, row.accession) in seen:
                continue
            chosen.append({"stratum": stratum, "cik": int(row.cik), "accession": row.accession, "selection_key": row.sel_key})
            seen.add((row.cik, row.accession))
            taken += 1
            if taken == per_stratum:
                break
    return pd.DataFrame(chosen, columns=["stratum", "cik", "accession", "selection_key"])


def available_session_independent(accepted_at: pd.Timestamp, sessions: Sequence[Date]) -> Optional[Date]:
    """Accepted strictly before 16:00 on a session -> that session; otherwise the next session.  (US Eastern wall clock, as in the filing.)"""
    stamp = pd.Timestamp(accepted_at)
    day = stamp.date()
    index = pd.DatetimeIndex(pd.to_datetime(list(sessions)))
    pos = index.searchsorted(pd.Timestamp(day))
    if pos < len(index) and index[pos].date() == day and stamp.time() < MARKET_CLOSE:
        return index[pos].date()
    later = index.searchsorted(pd.Timestamp(day) + pd.Timedelta(days=1))
    return index[later].date() if later < len(index) else None


def raw_values(zip_path: Path, wanted: Mapping[str, tuple[str, Optional[str]]], chunk_rows: int = 600_000) -> dict[str, dict[str, Optional[float]]]:
    """{accession: {concept: value}} straight from num.txt.  `wanted[accession] = (period_end 'YYYYMMDD', currency or None -> USD)`."""
    out: dict[str, dict[str, Optional[float]]] = {a: {k: None for k in RAW_TAGS} for a in wanted}
    tag_found: dict[str, dict[str, Optional[str]]] = {a: {k: None for k in RAW_TAGS} for a in wanted}
    with zipfile.ZipFile(zip_path) as archive:
        member = next(m for m in archive.namelist() if Path(m).name.lower() == "num.txt")
        with archive.open(member) as handle:
            for chunk in pd.read_csv(handle, sep="\t", low_memory=False, chunksize=chunk_rows, dtype=str,
                                     usecols=["adsh", "tag", "version", "ddate", "qtrs", "uom", "segments", "coreg", "value"]):
                chunk = chunk[chunk["adsh"].isin(wanted) & chunk["segments"].isna() & chunk["coreg"].isna()]
                for adsh, group in chunk.groupby("adsh"):
                    period_end, currency = wanted[adsh]
                    group = group[(group["ddate"] == period_end) & (group["uom"] == (currency or "USD"))]
                    for concept, tags in RAW_TAGS.items():
                        subset = group[group["qtrs"] == FLOW_QTRS[concept]]
                        for rank, tag in enumerate(tags):
                            hit = subset[subset["tag"] == tag]
                            if len(hit) and (tag_found[adsh][concept] is None or rank < tags.index(tag_found[adsh][concept])):
                                out[adsh][concept] = float(hit["value"].astype(float).iloc[0])
                                tag_found[adsh][concept] = tag
                                break
    return out


def close(a: Optional[float], b: Optional[float]) -> Optional[bool]:
    """None when either side is absent (nothing to compare), else relative equality."""
    if a is None or b is None or (isinstance(a, float) and np.isnan(a)) or (isinstance(b, float) and np.isnan(b)):
        return None
    return bool(abs(a - b) <= RELATIVE_TOLERANCE * max(1.0, abs(a), abs(b)))


def verdict(record: Mapping[str, Any]) -> str:
    """PASS: every comparable value agrees and timing is right.  NEEDS_REVIEW: a disagreement or a missing comparison that a person must read."""
    checks = [record.get("availability_ok")]
    for concept in RAW_TAGS:
        checks += [record.get(f"{concept}_raw_vs_curated"), record.get(f"{concept}_curated_vs_snapshot")]
    checks.append(record.get("roa_recomputed_vs_snapshot"))
    if any(c is False for c in checks):
        return "FAIL"
    if record.get("curated_facts") == 0:
        return "NEEDS_REVIEW"
    return "PASS"
