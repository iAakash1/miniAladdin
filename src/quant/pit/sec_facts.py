"""As-reported SEC fact store, version 3 (`sec-core-facts-v3`).

Supersedes the v2 curation in `sec_foundation.py`, whose audit found three defects
(`docs/SEC_TAG_MAP_AUDIT.md`): dimensional (segment / equity-component) rows were not excluded, so
one "revenue" or "equity" could be a segment or a component; the unit column was never populated
from the source `uom`, so currencies could mix; and the `as_of` view preferred the *fallback* tag
when one filing carried several tags of a family.

Rules that are load-bearing:

* every filing vintage is retained; nothing is overwritten, ever - selection is a view;
* only consolidated, undimensioned facts (`segments` and `coreg` empty) enter the store, and the
  count of excluded dimensional rows is reported, never hidden;
* a fact is usable from its EDGAR *acceptance* time, expressed in US Eastern wall-clock time (the
  timezone EDGAR stamps), and an acceptance at or after the 16:00 close is usable from the next
  session - nothing is inferred from a fiscal period end;
* a tag is only accepted from the taxonomy family the map names, in the unit the map names;
* missing is missing: no fact is filled, defaulted or zero-substituted.
"""

from __future__ import annotations

import json
import os
import zipfile
from dataclasses import dataclass
from datetime import date as Date, datetime, time as Clock, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import numpy as np
import pandas as pd

from src.quant.pit.calendar import TradingCalendar
from src.quant.pit.sec_foundation import _parse_accepted, sha256_file

TAG_MAP_VERSION = "sec-core-facts-v3"
ACCEPTANCE_TIMEZONE = "America/New_York"  # EDGAR acceptance stamps are US Eastern wall-clock time
MARKET_CLOSE = Clock(16, 0)
PERIODIC_FORMS = frozenset({"10-K", "10-K/A", "10-KT", "10-KT/A", "10-Q", "10-Q/A", "10-QT", "10-QT/A"})


@dataclass(frozen=True)
class FactSpec:
    context: str                      # "instant" or "duration"
    unit: str                         # required source `uom`
    tags: tuple[tuple[str, str], ...]  # (taxonomy family, tag) in strict priority order
    note: str = ""


FACTS: dict[str, FactSpec] = {
    "revenue": FactSpec("duration", "USD", (
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"), ("us-gaap", "Revenues"),
        ("us-gaap", "SalesRevenueNet"), ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"))),
    "cost_of_revenue": FactSpec("duration", "USD", (
        ("us-gaap", "CostOfRevenue"), ("us-gaap", "CostOfGoodsAndServicesSold"), ("us-gaap", "CostOfGoodsSold"))),
    "gross_profit": FactSpec("duration", "USD", (("us-gaap", "GrossProfit"),)),
    "operating_income": FactSpec("duration", "USD", (("us-gaap", "OperatingIncomeLoss"),)),
    "net_income": FactSpec("duration", "USD", (("us-gaap", "NetIncomeLoss"), ("us-gaap", "ProfitLoss")),
                           "ProfitLoss includes non-controlling interest; fallback only"),
    "eps_diluted": FactSpec("duration", "USD/shares", (("us-gaap", "EarningsPerShareDiluted"),)),
    "depreciation_amortization": FactSpec("duration", "USD", (
        ("us-gaap", "DepreciationDepletionAndAmortization"), ("us-gaap", "DepreciationAndAmortization"))),
    "operating_cash_flow": FactSpec("duration", "USD", (
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"))),
    "capital_expenditure": FactSpec("duration", "USD", (
        ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"), ("us-gaap", "PaymentsToAcquireProductiveAssets")),
        "a payment: reported positive"),
    "assets": FactSpec("instant", "USD", (("us-gaap", "Assets"),)),
    "current_assets": FactSpec("instant", "USD", (("us-gaap", "AssetsCurrent"),)),
    "liabilities": FactSpec("instant", "USD", (("us-gaap", "Liabilities"),)),
    "current_liabilities": FactSpec("instant", "USD", (("us-gaap", "LiabilitiesCurrent"),)),
    "equity": FactSpec("instant", "USD", (
        ("us-gaap", "StockholdersEquity"),
        ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")),
        "fallback includes non-controlling interest"),
    "cash": FactSpec("instant", "USD", (
        ("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
        ("us-gaap", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"))),
    "inventory": FactSpec("instant", "USD", (("us-gaap", "InventoryNet"),)),
    "accounts_receivable": FactSpec("instant", "USD", (("us-gaap", "AccountsReceivableNetCurrent"),)),
    "long_term_debt": FactSpec("instant", "USD", (("us-gaap", "LongTermDebtNoncurrent"), ("us-gaap", "LongTermDebt"))),
    "short_term_debt": FactSpec("instant", "USD", (
        ("us-gaap", "DebtCurrent"), ("us-gaap", "ShortTermBorrowings"), ("us-gaap", "LongTermDebtCurrent"))),
    "shares_outstanding": FactSpec("instant", "shares", (
        ("dei", "EntityCommonStockSharesOutstanding"), ("us-gaap", "CommonStockSharesOutstanding")),
        "dei cover-page shares are absent from the bulk data sets after ~2014; see security master"),
    "weighted_shares_basic": FactSpec("duration", "shares", (("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic"),)),
}
TAG_INDEX: dict[str, list[tuple[str, int, str]]] = {}
for _fact, _spec in FACTS.items():
    for _priority, (_family, _tag) in enumerate(_spec.tags):
        TAG_INDEX.setdefault(_tag, []).append((_fact, _priority, _family))

CURATED_COLUMNS = [
    "cik", "accession", "form", "filed", "accepted_at", "available_session", "fy", "fp", "report_period",
    "taxonomy", "canonical_fact", "tag", "tag_priority", "context_type", "qtrs", "unit", "value",
    "period_start", "period_end", "period_start_method", "amendment", "previous_report_amended",
    "source_archive", "source_archive_sha256", "tag_map_version", "sic", "name",
]
FACT_KEY = ["cik", "canonical_fact", "unit", "period_start", "period_end", "context_type"]


# ── availability ─────────────────────────────────────────────────────────────

def available_session(accepted_at: datetime | pd.Timestamp, calendar: TradingCalendar,
                      close: Clock = MARKET_CLOSE) -> Optional[Date]:
    """First session whose close-based decision may use a filing accepted at `accepted_at` (US Eastern).

    Accepted strictly before the close on a session: usable that session.  Accepted at or after the
    close, or on a non-session day: usable from the next session.  `None` beyond the calendar - never
    clamped, never guessed.
    """
    stamp = pd.Timestamp(accepted_at)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert(ACCEPTANCE_TIMEZONE).tz_localize(None)
    day = stamp.date()
    if calendar.contains(day):
        if stamp.time() < close:
            return day
        return calendar.on_or_after(day + timedelta(days=1))
    return calendar.on_or_after(day)


# ── filings registry ─────────────────────────────────────────────────────────

REGISTRY_COLUMNS = ["adsh", "cik", "name", "sic", "form", "period", "fy", "fp", "filed", "accepted_at", "prevrpt",
                    "former", "changed", "countryinc", "stprinc", "ein", "source_archive"]


def _read_member(archive: zipfile.ZipFile, name: str, **kwargs: Any) -> pd.DataFrame:
    actual = next(member for member in archive.namelist() if Path(member).name.lower() == name)
    with archive.open(actual) as handle:
        return pd.read_csv(handle, sep="\t", low_memory=False, **kwargs)


def read_registry(zip_path: Path, *, accepted_cutoff: str | pd.Timestamp = "2025-05-09 23:59:59") -> pd.DataFrame:
    """Every periodic filing in one quarterly archive, whoever filed it."""
    with zipfile.ZipFile(zip_path) as archive:
        sub = _read_member(archive, "sub.txt", dtype=str)
    sub.columns = [c.lower() for c in sub.columns]
    sub["accepted_at"] = _parse_accepted(sub["accepted"])
    sub = sub[sub["form"].isin(PERIODIC_FORMS) & sub["accepted_at"].notna()
              & (sub["accepted_at"] <= pd.Timestamp(accepted_cutoff))].copy()
    for column in ("cik", "sic", "fy", "prevrpt"):
        sub[column] = pd.to_numeric(sub[column], errors="coerce")
    sub["source_archive"] = zip_path.name
    return sub.reindex(columns=REGISTRY_COLUMNS).reset_index(drop=True)


# ── curation ─────────────────────────────────────────────────────────────────

def _period_start(period_end: pd.Series, qtrs: pd.Series) -> list:
    stamps = pd.to_datetime(period_end)
    return [None if (q <= 0 or pd.isna(e)) else (e - pd.DateOffset(months=3 * int(q)) + pd.Timedelta(days=1)).date()
            for e, q in zip(stamps, qtrs)]


def curate_num(num: pd.DataFrame, registry: pd.DataFrame, *, archive_name: str, archive_sha256: str,
               calendar: Optional[TradingCalendar] = None) -> tuple[pd.DataFrame, dict[str, int]]:
    """Curate one chunk of `num` rows against the registry.  Returns rows and exclusion counts."""
    counts = {"considered": len(num)}
    num = num[num["tag"].isin(TAG_INDEX)].copy()
    counts["mapped_tag_rows"] = len(num)
    dimensional = num["segments"].notna() | num["coreg"].notna()
    counts["dimensional_excluded"] = int(dimensional.sum())
    num = num[~dimensional]
    if num.empty:
        return pd.DataFrame(columns=CURATED_COLUMNS), counts

    expanded = []
    for tag, group in num.groupby("tag", sort=False):
        for fact, priority, family in TAG_INDEX[tag]:
            spec = FACTS[fact]
            keep = group[group["version"].astype("string").str.startswith(family + "/", na=False)
                         & (group["uom"] == spec.unit)]
            counts.setdefault("wrong_taxonomy_or_unit", 0)
            counts["wrong_taxonomy_or_unit"] += len(group) - len(keep)
            if keep.empty:
                continue
            keep = keep.assign(canonical_fact=fact, tag_priority=priority, context_type=spec.context,
                               taxonomy=keep["version"])
            expanded.append(keep)
    if not expanded:
        return pd.DataFrame(columns=CURATED_COLUMNS), counts
    rows = pd.concat(expanded, ignore_index=True)
    rows["qtrs"] = pd.to_numeric(rows["qtrs"], errors="coerce").fillna(-1).astype(int)
    ok = ((rows["context_type"] == "instant") & (rows["qtrs"] == 0)) | ((rows["context_type"] == "duration") & (rows["qtrs"] > 0))
    counts["context_mismatch_excluded"] = int((~ok).sum())
    rows = rows[ok]
    rows = rows.merge(registry.rename(columns={"adsh": "adsh"}), on="adsh", how="inner", validate="many_to_one")
    rows["accession"] = rows["adsh"]
    rows["unit"] = rows["uom"]
    rows["value"] = pd.to_numeric(rows["value"], errors="coerce")
    counts["null_value_excluded"] = int(rows["value"].isna().sum())
    rows = rows[rows["value"].notna()]
    rows["period_end"] = pd.to_datetime(rows["ddate"].astype(str), format="%Y%m%d", errors="coerce").dt.date
    rows["period_start"] = _period_start(rows["period_end"], rows["qtrs"])
    rows["period_start_method"] = np.where(rows["qtrs"] > 0, "derived_from_fsds_qtrs", "instant_not_applicable")
    rows["report_period"] = pd.to_datetime(rows["period"].astype(str), format="%Y%m%d", errors="coerce").dt.date
    rows["filed"] = pd.to_datetime(rows["filed"].astype(str), format="%Y%m%d", errors="coerce").dt.date
    rows["amendment"] = rows["form"].str.endswith("/A")
    rows["previous_report_amended"] = rows["prevrpt"].fillna(0).astype(int).astype(bool)
    rows["source_archive"] = archive_name
    rows["source_archive_sha256"] = archive_sha256
    rows["tag_map_version"] = TAG_MAP_VERSION
    rows["available_session"] = (
        [available_session(v, calendar) for v in rows["accepted_at"]] if calendar is not None else None)
    rows["fy"] = rows["fy"].astype("Int64")
    out = rows.reindex(columns=CURATED_COLUMNS)
    counts["curated"] = len(out)
    return out, counts


def curate_archive(zip_path: Path, archive_sha256: str, *, ciks: Optional[set[int]] = None,
                   calendar: Optional[TradingCalendar] = None,
                   accepted_cutoff: str | pd.Timestamp = "2025-05-09 23:59:59",
                   chunk_rows: int = 500_000) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    """One archive -> (filings registry, curated facts, exclusion counts).  Deterministic."""
    registry = read_registry(zip_path, accepted_cutoff=accepted_cutoff)
    selected = registry if ciks is None else registry[registry["cik"].isin(ciks)]
    total: dict[str, int] = {}
    parts = []
    with zipfile.ZipFile(zip_path) as archive:
        member = next(m for m in archive.namelist() if Path(m).name.lower() == "num.txt")
        wanted = set(selected["adsh"])
        with archive.open(member) as handle:
            for chunk in pd.read_csv(handle, sep="\t", low_memory=False, chunksize=chunk_rows, dtype={
                    "adsh": "string", "tag": "string", "version": "string", "uom": "string",
                    "segments": "string", "coreg": "string", "ddate": "string"}):
                chunk = chunk[chunk["adsh"].isin(wanted)]
                rows, counts = curate_num(chunk, selected, archive_name=zip_path.name, archive_sha256=archive_sha256,
                                          calendar=calendar)
                for key, value in counts.items():
                    total[key] = total.get(key, 0) + value
                if len(rows):
                    parts.append(rows)
    facts = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=CURATED_COLUMNS)
    facts = facts.sort_values(["accepted_at", "cik", "canonical_fact", "period_end", "tag_priority", "accession", "qtrs"],
                              kind="stable").reset_index(drop=True)
    return registry, facts, total


# ── the two point-in-time views ──────────────────────────────────────────────

def canonical_per_filing(facts: pd.DataFrame) -> pd.DataFrame:
    """One row per (fact key, accession): the highest-priority tag the filing carried."""
    keys = FACT_KEY + ["accession"]
    ordered = facts.sort_values(keys + ["tag_priority"], kind="stable")
    return ordered.drop_duplicates(keys, keep="first")


def first_reported(facts: pd.DataFrame) -> pd.DataFrame:
    """FIRST_REPORTED: for each fact key, the earliest accepted filing (ties: accession)."""
    ordered = canonical_per_filing(facts).sort_values(["accepted_at", "accession"], kind="stable")
    return ordered.drop_duplicates(FACT_KEY, keep="first").reset_index(drop=True)


def as_of(facts: pd.DataFrame, decision_time: datetime | str | pd.Timestamp) -> pd.DataFrame:
    """AS_OF(decision_time): for each fact key, the latest filing with accepted_at <= decision_time.

    Within that filing the highest-priority tag wins.  Later filings, later amendments and later
    restatements cannot change the result - they are filtered out before any selection.
    """
    eligible = facts[pd.to_datetime(facts["accepted_at"]) <= pd.Timestamp(decision_time)]
    ordered = canonical_per_filing(eligible).sort_values(["accepted_at", "accession"], kind="stable")
    return ordered.drop_duplicates(FACT_KEY, keep="last").reset_index(drop=True)


def as_of_session(facts: pd.DataFrame, session: Date) -> pd.DataFrame:
    """AS_OF for a close-based decision on `session`: filings whose available_session <= session."""
    eligible = facts[pd.to_datetime(facts["available_session"]) <= pd.Timestamp(session)]
    ordered = canonical_per_filing(eligible).sort_values(["accepted_at", "accession"], kind="stable")
    return ordered.drop_duplicates(FACT_KEY, keep="last").reset_index(drop=True)


def tag_disagreements(facts: pd.DataFrame) -> pd.DataFrame:
    """Where two tags of one family in the same filing and period carry different values (not resolved, reported)."""
    keys = FACT_KEY + ["accession"]
    grouped = facts.groupby(keys, dropna=False).agg(tags=("tag", "nunique"), values=("value", "nunique")).reset_index()
    return grouped[(grouped["tags"] > 1) & (grouped["values"] > 1)]


def duplicate_conflicts(facts: pd.DataFrame) -> pd.DataFrame:
    """Same filing, same tag, same period, different values: a source-level conflict, never averaged."""
    keys = FACT_KEY + ["accession", "tag"]
    grouped = facts.groupby(keys, dropna=False)["value"].nunique().reset_index(name="values")
    return grouped[grouped["values"] > 1]


def content_hash(facts: pd.DataFrame) -> str:
    """Order-independent content hash of a curated frame (for byte-identity checks)."""
    import hashlib

    cols = [c for c in CURATED_COLUMNS if c != "available_session"]
    frame = facts.reindex(columns=cols).astype(str).sort_values(cols, kind="stable")
    return hashlib.sha256(pd.util.hash_pandas_object(frame, index=False).to_numpy().tobytes()).hexdigest()


# ── build ────────────────────────────────────────────────────────────────────

def build_store(raw_dir: Path, download_manifest: Path, out_dir: Path, *, ciks: Optional[set[int]],
                calendar: Optional[TradingCalendar], accepted_cutoff: str = "2025-05-09 23:59:59",
                quarters: Optional[Sequence[str]] = None, progress: bool = True) -> dict[str, Any]:
    raw_dir, out_dir = Path(raw_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    hashes = {r["filename"]: r["sha256"] for r in json.loads(Path(download_manifest).read_text())["archives"]}
    registry_parts, summaries, totals = [], [], {}
    for index, path in enumerate(sorted(raw_dir.glob("????q?.zip")), 1):
        if quarters and path.stem not in quarters:
            continue
        registry, facts, counts = curate_archive(path, hashes[path.name], ciks=ciks, calendar=calendar, accepted_cutoff=accepted_cutoff)
        registry_parts.append(registry)
        target = out_dir / f"facts-{path.stem}.parquet"
        tmp = target.with_suffix(".parquet.tmp")
        facts.to_parquet(tmp, compression="zstd", index=False)
        os.replace(tmp, target)
        for key, value in counts.items():
            totals[key] = totals.get(key, 0) + value
        summaries.append({"quarter": path.stem, "rows": len(facts), "ciks": int(facts["cik"].nunique()),
                          "filings": int(facts["accession"].nunique()), "output_sha256": sha256_file(target),
                          "tag_disagreements": int(len(tag_disagreements(facts))) if len(facts) else 0,
                          "duplicate_conflicts": int(len(duplicate_conflicts(facts))) if len(facts) else 0})
        if progress:
            print(f"CURATE v3 {index}/58 {path.stem}: {len(facts):,} facts, {facts['cik'].nunique():,} CIKs", flush=True)
    registry_all = pd.concat(registry_parts, ignore_index=True).sort_values(["accepted_at", "adsh"], kind="stable")
    registry_all.to_parquet(out_dir / "filings.parquet", compression="zstd", index=False)
    report = {"tag_map_version": TAG_MAP_VERSION, "acceptance_timezone": ACCEPTANCE_TIMEZONE,
              "market_close": MARKET_CLOSE.isoformat(), "accepted_cutoff": accepted_cutoff,
              "registry_filings": int(len(registry_all)), "registry_ciks": int(registry_all["cik"].nunique()),
              "exclusion_counts": totals, "quarters": summaries,
              "candidate_ciks": None if ciks is None else len(ciks)}
    return report


def coverage_report(out_dir: Path) -> dict[str, Any]:
    """Coverage, fallback and conflict rates measured from the curated store itself."""
    paths = sorted(Path(out_dir).glob("facts-*.parquet"))
    if not paths:
        return {"status": "NO_CURATED_FACTS"}
    cols = ["cik", "accession", "accepted_at", "canonical_fact", "tag", "tag_priority", "qtrs", "unit", "value",
            "period_start", "period_end", "context_type", "form"]
    frames = [pd.read_parquet(p, columns=cols) for p in paths]
    facts = pd.concat(frames, ignore_index=True)
    facts["year"] = pd.to_datetime(facts["accepted_at"]).dt.year
    canonical = canonical_per_filing(facts)
    by_fact = {}
    disagreements = tag_disagreements(facts)
    dis_by_fact = disagreements.groupby("canonical_fact").size()
    for fact, group in facts.groupby("canonical_fact"):
        per_filing = canonical[canonical["canonical_fact"] == fact]
        by_fact[fact] = {
            "rows": int(len(group)), "filing_period_facts": int(len(per_filing)), "ciks": int(group["cik"].nunique()),
            "primary_tag": FACTS[fact].tags[0][1], "fallback_tags": [t for _, t in FACTS[fact].tags[1:]],
            "unit": FACTS[fact].unit, "context": FACTS[fact].context,
            "fallback_rate": float((per_filing["tag_priority"] > 0).mean()),
            "tag_disagreement_rate": float(dis_by_fact.get(fact, 0) / max(len(per_filing), 1)),
            "tags_used": {str(k): int(v) for k, v in group["tag"].value_counts().items()},
        }
    return {
        "status": "BUILT", "tag_map_version": TAG_MAP_VERSION, "rows": int(len(facts)), "filings": int(facts["accession"].nunique()),
        "ciks": int(facts["cik"].nunique()), "accepted_min": str(facts["accepted_at"].min()), "accepted_max": str(facts["accepted_at"].max()),
        "rows_by_year": {str(k): int(v) for k, v in facts.groupby("year").size().items()},
        "forms": {str(k): int(v) for k, v in facts["form"].value_counts().items()},
        "duplicate_conflict_rows": int(len(duplicate_conflicts(facts))),
        "tag_disagreement_rows": int(len(disagreements)),
        "unit_values": {str(k): int(v) for k, v in facts["unit"].value_counts().items()},
        "by_fact": by_fact,
    }
