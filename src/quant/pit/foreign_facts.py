"""Foreign-filer (20-F / 40-F) as-reported facts, version `ifrs-core-facts-v1`.

Foreign private issuers file annual reports on 20-F or 40-F.  The SEC data sets carry their XBRL facts under either the
IFRS taxonomy (`ifrs/…`) or US-GAAP (`us-gaap/…`); this module keeps the two apart and never treats their tags as
interchangeable.  Rules that are load-bearing:

* one taxonomy family per filing - the family that supplies most of its mapped facts; tags from the other family in the
  same filing are ignored, so a filing is never assembled from a mixture;
* monetary facts are in the filing's reporting currency, the most frequent currency among its mapped monetary facts;
  facts in any other currency are dropped and counted - values in different currencies are never combined;
* consolidated, undimensioned facts only (as in `sec_facts`); every filing vintage is kept;
* availability is EDGAR acceptance time in US Eastern with the after-close next-session rule (`sec_facts.available_session`);
* nothing here defines shares, market capitalisation or any price-dependent quantity: the ADS-to-ordinary ratio and the
  FX rate are not available point-in-time, so those are undefined for foreign filers (gate document, definition D2).

Concepts are limited to those the existing characteristics need.  Every mapping carries its caveat.
"""

from __future__ import annotations

import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.quant.pit import sec_facts as S
from src.quant.pit.calendar import TradingCalendar
from src.quant.pit.sec_foundation import _parse_accepted, sha256_file

IFRS_MAP_VERSION = "ifrs-core-facts-v1"
FOREIGN_ANNUAL_FORMS = frozenset({"20-F", "20-F/A", "40-F", "40-F/A"})
AUDITED_EVENT_FORMS = frozenset({"6-K", "6-K/A"})     # counted, never periodic evidence
CURRENCY = "currency"
_CURRENCY_CODE = r"^[A-Z]{3}$"


@dataclass(frozen=True)
class ForeignFact:
    context: str                        # instant | duration
    tags: tuple[tuple[str, str], ...]   # (taxonomy family, tag) in strict priority order
    caveat: str = ""


# The us-gaap entries reuse the v3 tag lists (currency rather than USD); the ifrs entries are new and conservative.
IFRS_FACTS: dict[str, tuple[tuple[str, str], ...]] = {
    "revenue": (("ifrs", "Revenue"), ("ifrs", "RevenueFromContractsWithCustomers")),
    "cost_of_revenue": (("ifrs", "CostOfSales"),),
    "gross_profit": (("ifrs", "GrossProfit"),),
    "operating_income": (("ifrs", "ProfitLossFromOperatingActivities"),),
    "net_income": (("ifrs", "ProfitLossAttributableToOwnersOfParent"), ("ifrs", "ProfitLoss")),
    "operating_cash_flow": (("ifrs", "CashFlowsFromUsedInOperatingActivities"),),
    "capital_expenditure": (("ifrs", "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"),),
    "assets": (("ifrs", "Assets"),),
    "current_assets": (("ifrs", "CurrentAssets"),),
    "liabilities": (("ifrs", "Liabilities"),),
    "current_liabilities": (("ifrs", "CurrentLiabilities"),),
    "equity": (("ifrs", "EquityAttributableToOwnersOfParent"), ("ifrs", "Equity")),
    "cash": (("ifrs", "CashAndCashEquivalents"),),
}
CAVEATS = {
    ("revenue", "ifrs"): "IFRS `Revenue` is the entity's own total-revenue line; banks/insurers use other lines and are unmapped",
    ("operating_income", "ifrs"): "IFRS defines no standard operating-profit line; `ProfitLossFromOperatingActivities` follows the issuer's own definition and is not comparable with US-GAAP OperatingIncomeLoss",
    ("net_income", "ifrs"): "parent-attributable profit first (like NetIncomeLoss); `ProfitLoss` includes non-controlling interests and is a fallback only",
    ("equity", "ifrs"): "parent equity first (like StockholdersEquity); `Equity` includes non-controlling interests and is a fallback only",
    ("operating_cash_flow", "ifrs"): "`CashFlowsFromUsedInOperations` (before interest and tax) is a different quantity and is deliberately NOT a fallback",
    ("capital_expenditure", "ifrs"): "a payment; the sign is as reported and the share of negative values is measured in the coverage audit",
    ("gross_profit", "ifrs"): "many IFRS issuers present expenses by nature and report no gross profit; the ratio falls back to revenue minus cost of sales only when both exist",
}

# The us-gaap side reuses the v3 map for the same canonical facts (only these concepts).
US_GAAP_FACTS = {fact: tuple(t for t in S.FACTS[fact].tags if t[0] == "us-gaap") for fact in IFRS_FACTS}
CONTEXT = {fact: S.FACTS[fact].context for fact in IFRS_FACTS}

FOREIGN_TAG_INDEX: dict[tuple[str, str], list[tuple[str, int]]] = {}
for _fact in IFRS_FACTS:
    for _family, _tags in (("ifrs", IFRS_FACTS[_fact]), ("us-gaap", US_GAAP_FACTS[_fact])):
        for _priority, (_fam, _tag) in enumerate(_tags):
            FOREIGN_TAG_INDEX.setdefault((_fam, _tag), []).append((_fact, _priority))

FOREIGN_COLUMNS = S.CURATED_COLUMNS + ["currency", "taxonomy_family", "map_version"]


def read_foreign_registry(zip_path: Path, *, accepted_cutoff: str | pd.Timestamp = "2025-05-09 23:59:59") -> pd.DataFrame:
    """Foreign annual filings plus 6-K/6-K/A (kept only so their count can be audited)."""
    with zipfile.ZipFile(zip_path) as archive:
        sub = S._read_member(archive, "sub.txt", dtype=str)
    sub.columns = [c.lower() for c in sub.columns]
    sub["accepted_at"] = _parse_accepted(sub["accepted"])
    keep = sub["form"].isin(FOREIGN_ANNUAL_FORMS | AUDITED_EVENT_FORMS) & sub["accepted_at"].notna() & (sub["accepted_at"] <= pd.Timestamp(accepted_cutoff))
    sub = sub[keep].copy()
    for column in ("cik", "sic", "fy", "prevrpt"):
        sub[column] = pd.to_numeric(sub[column], errors="coerce")
    sub["source_archive"] = zip_path.name
    return sub.reindex(columns=S.REGISTRY_COLUMNS).reset_index(drop=True)


def filing_families(rows: pd.DataFrame) -> pd.Series:
    """Per accession: the taxonomy family supplying most of its mapped facts (ties go to ifrs, the filing's own taxonomy)."""
    counts = rows.groupby(["adsh", "family"]).size().unstack(fill_value=0)
    for family in ("ifrs", "us-gaap"):
        if family not in counts:
            counts[family] = 0
    return pd.Series(np.where(counts["ifrs"] >= counts["us-gaap"], "ifrs", "us-gaap"), index=counts.index)


def reporting_currencies(rows: pd.DataFrame) -> pd.Series:
    """Per accession: the most frequent currency among its mapped monetary rows (deterministic tie-break: code order)."""
    monetary = rows[rows["uom"].astype("string").str.match(_CURRENCY_CODE, na=False)]
    counts = monetary.groupby(["adsh", "uom"]).size().reset_index(name="n").sort_values(["adsh", "n", "uom"], ascending=[True, False, True])
    return counts.drop_duplicates("adsh").set_index("adsh")["uom"]


def curate_foreign_num(num: pd.DataFrame, registry: pd.DataFrame, *, archive_name: str, archive_sha256: str,
                       calendar: Optional[TradingCalendar] = None) -> tuple[pd.DataFrame, dict[str, int]]:
    counts = {"considered": len(num)}
    num = num[num["adsh"].isin(set(registry["adsh"]))].copy()
    counts["annual_filing_rows"] = len(num)
    num["family"] = num["version"].astype("string").str.split("/").str[0]
    key = list(zip(num["family"], num["tag"]))
    num = num[[k in FOREIGN_TAG_INDEX for k in key]]
    counts["mapped_tag_rows"] = len(num)
    dimensional = num["segments"].notna() | num["coreg"].notna()
    counts["dimensional_excluded"] = int(dimensional.sum())
    num = num[~dimensional]
    if num.empty:
        return pd.DataFrame(columns=FOREIGN_COLUMNS), counts
    family = filing_families(num)
    num = num[num["family"] == num["adsh"].map(family)]
    counts["other_family_excluded"] = counts["mapped_tag_rows"] - counts["dimensional_excluded"] - len(num)
    currency = reporting_currencies(num)
    num["currency"] = num["adsh"].map(currency)
    expanded = []
    for (fam, tag), group in num.groupby(["family", "tag"], sort=False):
        for fact, priority in FOREIGN_TAG_INDEX[(fam, tag)]:
            expanded.append(group.assign(canonical_fact=fact, tag_priority=priority, context_type=CONTEXT[fact]))
    rows = pd.concat(expanded, ignore_index=True)
    monetary = rows["canonical_fact"] != "shares_outstanding"
    wrong_currency = monetary & (rows["uom"] != rows["currency"])
    counts["other_currency_excluded"] = int(wrong_currency.sum())
    rows = rows[~wrong_currency]
    rows["qtrs"] = pd.to_numeric(rows["qtrs"], errors="coerce").fillna(-1).astype(int)
    ok = ((rows["context_type"] == "instant") & (rows["qtrs"] == 0)) | ((rows["context_type"] == "duration") & (rows["qtrs"] > 0))
    counts["context_mismatch_excluded"] = int((~ok).sum())
    rows = rows[ok].merge(registry, on="adsh", how="inner", validate="many_to_one")
    rows["accession"] = rows["adsh"]
    rows["unit"] = rows["uom"]
    rows["taxonomy"] = rows["version"]
    rows["taxonomy_family"] = rows["family"]
    rows["value"] = pd.to_numeric(rows["value"], errors="coerce")
    counts["null_value_excluded"] = int(rows["value"].isna().sum())
    rows = rows[rows["value"].notna()]
    rows["period_end"] = pd.to_datetime(rows["ddate"].astype(str), format="%Y%m%d", errors="coerce").dt.date
    rows["period_start"] = S._period_start(rows["period_end"], rows["qtrs"])
    rows["period_start_method"] = np.where(rows["qtrs"] > 0, "derived_from_fsds_qtrs", "instant_not_applicable")
    rows["report_period"] = pd.to_datetime(rows["period"].astype(str), format="%Y%m%d", errors="coerce").dt.date
    rows["filed"] = pd.to_datetime(rows["filed"].astype(str), format="%Y%m%d", errors="coerce").dt.date
    rows["amendment"] = rows["form"].str.endswith("/A")
    rows["previous_report_amended"] = rows["prevrpt"].fillna(0).astype(int).astype(bool)
    rows["source_archive"] = archive_name
    rows["source_archive_sha256"] = archive_sha256
    rows["tag_map_version"] = IFRS_MAP_VERSION
    rows["map_version"] = IFRS_MAP_VERSION
    rows["available_session"] = [S.available_session(v, calendar) for v in rows["accepted_at"]] if calendar is not None else None
    rows["fy"] = rows["fy"].astype("Int64")
    out = rows.reindex(columns=FOREIGN_COLUMNS)
    counts["curated"] = len(out)
    return out, counts


def curate_foreign_archive(zip_path: Path, archive_sha256: str, *, calendar: Optional[TradingCalendar] = None,
                           accepted_cutoff: str | pd.Timestamp = "2025-05-09 23:59:59", chunk_rows: int = 600_000
                           ) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    """One archive -> (foreign registry incl. 6-K, curated annual facts, exclusion counts).  Deterministic."""
    registry = read_foreign_registry(zip_path, accepted_cutoff=accepted_cutoff)
    annual = registry[registry["form"].isin(FOREIGN_ANNUAL_FORMS)]
    total: dict[str, int] = {}
    parts = []
    with zipfile.ZipFile(zip_path) as archive:
        member = next(m for m in archive.namelist() if Path(m).name.lower() == "num.txt")
        wanted = set(annual["adsh"])
        with archive.open(member) as handle:
            for chunk in pd.read_csv(handle, sep="\t", low_memory=False, chunksize=chunk_rows, dtype={
                    "adsh": "string", "tag": "string", "version": "string", "uom": "string", "segments": "string", "coreg": "string", "ddate": "string"}):
                chunk = chunk[chunk["adsh"].isin(wanted)]
                if chunk.empty:
                    continue
                rows, counts = curate_foreign_num(chunk, annual, archive_name=zip_path.name, archive_sha256=archive_sha256, calendar=calendar)
                for key, value in counts.items():
                    total[key] = total.get(key, 0) + value
                if len(rows):
                    parts.append(rows)
    facts = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=FOREIGN_COLUMNS)
    facts = facts.sort_values(["accepted_at", "cik", "canonical_fact", "period_end", "tag_priority", "accession", "qtrs"], kind="stable").reset_index(drop=True)
    return registry, facts, total


def mapping_table() -> pd.DataFrame:
    """The versioned map as data: canonical concept, taxonomy, tag, unit requirement, context, priority, fallback, caveat."""
    rows = []
    for fact in IFRS_FACTS:
        for family, tags in (("ifrs", IFRS_FACTS[fact]), ("us-gaap", US_GAAP_FACTS[fact])):
            for priority, (fam, tag) in enumerate(tags):
                rows.append({"canonical_fact": fact, "taxonomy": fam, "tag": tag, "unit_requirement": "reporting currency of the filing",
                             "context": CONTEXT[fact], "priority": priority, "is_fallback": priority > 0,
                             "semantic_caveat": CAVEATS.get((fact, fam), ""), "map_version": IFRS_MAP_VERSION})
    return pd.DataFrame(rows)


def build_foreign_store(raw_dir: Path, download_manifest, out_dir: Path, *, calendar: Optional[TradingCalendar],
                        accepted_cutoff: str = "2025-05-09 23:59:59", progress: bool = True) -> dict[str, Any]:
    import json

    raw_dir, out_dir = Path(raw_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    hashes = {r["filename"]: r["sha256"] for r in json.loads(Path(download_manifest).read_text())["archives"]}
    registries, summaries, totals = [], [], {}
    for index, path in enumerate(sorted(raw_dir.glob("????q?.zip")), 1):
        registry, facts, counts = curate_foreign_archive(path, hashes[path.name], calendar=calendar, accepted_cutoff=accepted_cutoff)
        registries.append(registry)
        target = out_dir / f"facts-{path.stem}.parquet"
        temporary = target.with_suffix(".parquet.tmp")
        facts.to_parquet(temporary, compression="zstd", index=False)
        os.replace(temporary, target)
        for key, value in counts.items():
            totals[key] = totals.get(key, 0) + value
        summaries.append({"quarter": path.stem, "rows": len(facts), "ciks": int(facts["cik"].nunique()) if len(facts) else 0,
                          "filings": int(facts["accession"].nunique()) if len(facts) else 0, "output_sha256": sha256_file(target)})
        if progress:
            print(f"FOREIGN {index}/58 {path.stem}: {len(facts):,} facts", flush=True)
    registry_all = pd.concat(registries, ignore_index=True).sort_values(["accepted_at", "adsh"], kind="stable")
    registry_all.to_parquet(out_dir / "filings_foreign.parquet", compression="zstd", index=False)
    forms = registry_all["form"].value_counts().to_dict()
    return {"map_version": IFRS_MAP_VERSION, "accepted_cutoff": accepted_cutoff, "registry_filings": int(len(registry_all)),
            "registry_ciks": int(registry_all["cik"].nunique()), "forms": {k: int(v) for k, v in forms.items()},
            "exclusion_counts": totals, "quarters": summaries}
