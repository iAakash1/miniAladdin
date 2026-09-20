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

# Frozen order (docs/DATA_COMPLETION_GATE_2026.md section 7, operationalised in Amendment A1.2): an issuer-period that qualifies for several
# strata is audited once, under the first one listed.
FROZEN_STRATA = ("AMENDMENT", "AFTER_CLOSE_ACCEPTANCE", "TICKER_REUSE_OR_SUCCESSION", "FOREIGN_FILER", "MULTIPLE_SHARE_CLASSES", "DELISTED_NAME",
                 "MISSING_FACT", "RESTATEMENT", "SPLIT", "UNCONSTRAINED")
# The first run's hard-case list: reported separately, beside the frozen audit.
SUPPLEMENTARY_STRATA = (
    "AMENDED_ANNUAL_FILING", "SUCCESSION_OR_TICKER_REUSE", "EXITING_SECURITY", "MIXED_FILER_REGIME", "NON_USD_REPORTING_CURRENCY",
    "IFRS_20F", "US_GAAP_20F", "FORM_40F", "MULTI_CLASS_SHARES", "SHARES_PROXY_TIER", "IDENTITY_GRADE_B_OR_C", "FORMER_NAME", "DOMESTIC_10K_GRADE_A",
)
STRATA = FROZEN_STRATA
# Independent *definitions* used only for DEFINITION_NOTE (total profit including non-controlling interest, total revenue); never for pass/fail.
ALTERNATE_TAGS = {
    "assets": ("Assets",),
    "net_income": ("ProfitLoss", "NetIncomeLoss"),
    "revenue": ("Revenues", "Revenue"),
}
RAW_TAGS = ALTERNATE_TAGS
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


def raw_values(zip_path: Path, wanted: Mapping[str, Mapping[str, Any]], chunk_rows: int = 600_000) -> dict[str, dict[str, Any]]:
    """Straight from num.txt.  `wanted[accession] = {"period_end": 'YYYYMMDD', "currency": str|None, "tags": {concept: curated tag}, "share_tag": str|None}`.

    Returns per accession: `same_tag` {concept: value of the tag the curated row cites}, `alternate` {concept: (tag, value)} under the alternate
    definitions, and `shares` [(segments, value)] rows of the stored share tag (any segment - so per-class rows are visible)."""
    out: dict[str, dict[str, Any]] = {a: {"same_tag": {k: None for k in FLOW_QTRS}, "alternate": {k: None for k in FLOW_QTRS}, "mapped_present": {k: [] for k in FLOW_QTRS}, "shares": []} for a in wanted}
    with zipfile.ZipFile(zip_path) as archive:
        member = next(m for m in archive.namelist() if Path(m).name.lower() == "num.txt")
        with archive.open(member) as handle:
            for chunk in pd.read_csv(handle, sep="\t", low_memory=False, chunksize=chunk_rows, dtype=str,
                                     usecols=["adsh", "tag", "version", "ddate", "qtrs", "uom", "segments", "coreg", "value"]):
                chunk = chunk[chunk["adsh"].isin(wanted)]
                for adsh, group in chunk.groupby("adsh"):
                    spec = wanted[adsh]
                    share_tag = spec.get("share_tag")
                    if share_tag:
                        for row in group[(group["tag"] == share_tag) & group["coreg"].isna()].itertuples(index=False):
                            out[adsh]["shares"].append((None if pd.isna(row.segments) else str(row.segments), float(row.value)))
                    if not spec.get("period_end"):
                        continue
                    plain = group[group["segments"].isna() & group["coreg"].isna() & (group["ddate"] == spec["period_end"]) & (group["uom"] == (spec.get("currency") or "USD"))]
                    for concept in FLOW_QTRS:
                        subset = plain[plain["qtrs"] == FLOW_QTRS[concept]]
                        cited = spec["tags"].get(concept)
                        if cited is not None:
                            hit = subset[subset["tag"] == cited]
                            if len(hit):
                                out[adsh]["same_tag"][concept] = float(hit["value"].astype(float).iloc[0])
                        for tag in spec.get("mapped", {}).get(concept, ()):
                            if len(subset[subset["tag"] == tag]):
                                out[adsh]["mapped_present"][concept].append(tag)
                        for tag in ALTERNATE_TAGS[concept]:
                            hit = subset[subset["tag"] == tag]
                            if len(hit):
                                out[adsh]["alternate"][concept] = (tag, float(hit["value"].astype(float).iloc[0]))
                                break
    return out


def close(a: Optional[float], b: Optional[float]) -> Optional[bool]:
    """None when either side is absent (nothing to compare), else relative equality."""
    if a is None or b is None or (isinstance(a, float) and np.isnan(a)) or (isinstance(b, float) and np.isnan(b)):
        return None
    return bool(abs(a - b) <= RELATIVE_TOLERANCE * max(1.0, abs(a), abs(b)))


def verdict(record: Mapping[str, Any]) -> str:
    """Amendment A1.3.  FAIL: any comparable value disagrees.  NEEDS_REVIEW: no curated fact to trace.  PASS otherwise.
    DEFINITION_NOTE (alternate tag differs by more than 1%) and share-count observations are reported, never turned into a pass or a fail."""
    checks = [record.get("availability_ok")]
    for concept in FLOW_QTRS:
        checks += [record.get(f"{concept}_same_tag_vs_curated"), record.get(f"{concept}_curated_vs_snapshot")]
    checks += [record.get("roa_recomputed_vs_snapshot"), record.get("shares_stored_vs_raw")]
    checks += [None if record.get(f"{c}_dropped_fact") is None else not record[f"{c}_dropped_fact"] for c in FLOW_QTRS]      # a mapped tag present in the source but absent from curated is a failure
    if any(c is False for c in checks):
        return "FAIL"
    if record.get("curated_facts") == 0:
        return "NEEDS_REVIEW"
    return "PASS"


def definition_note(curated: Optional[float], alternate: Optional[tuple]) -> Optional[str]:
    """A note (never a failure) when a different definition available in the same filing differs from the curated value by more than 1%."""
    if curated is None or alternate is None:
        return None
    tag, value = alternate
    if abs(curated - value) <= 0.01 * max(1.0, abs(curated), abs(value)):
        return None
    return f"{tag}={value:.6g} vs curated {curated:.6g}"


def shares_reconcile(stored: Optional[float], raw_rows: Sequence[tuple]) -> Optional[bool]:
    """Stored share value equals the raw un-dimensioned value, or the sum of the per-class rows; None when there is nothing to compare."""
    if stored is None or not raw_rows:
        return None
    plain = [v for s, v in raw_rows if s is None]
    classes = [v for s, v in raw_rows if s is not None]
    if plain and close(stored, plain[0]):
        return True
    return bool(classes and close(stored, float(sum(classes))))
