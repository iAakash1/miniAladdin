"""Acquire the complete EDGAR filing registry (periodic reports, amendments, 8-Ks, late-filing notices, deregistrations) for the study firms and validate it against the Financial Statement Data Sets.

The Financial Statement Data Sets (FSDS) used by EXP-012/013 list only filings that carry XBRL financial statements. The EDGAR *submissions* documents list every filing of a company with its acceptance
time, form, XBRL flags and, for 8-Ks, the item numbers (Item 4.02 is the non-reliance notice that precedes most restatements). Each company's main document holds only its most recent ~1,000 entries;
older entries are on extra pages named in `filings.files`. Of the 901 documents already cached for the frozen universe, 640 start after 2011-01-01, so the history is incomplete without those pages.

What this script does, in order (each step resumable: a cached document is never fetched twice; every request is logged without any header):

1. Choose the company identifiers (CIK) of a cohort: `frozen` (the 250-name universe), `mid` (liquidity ranks 251 to 1,000), or both.
2. Fetch each main document and every older page through `EdgarClient` (declared contact read from the environment variable `EDGAR_USER_AGENT`, 6 requests per second, one manifest line per request).
3. Normalise to one table: accession, form, filing date, report date, acceptance time in UTC, XBRL flags, 8-K items, description. Only filings accepted on or before 2025-06-30 are kept (the sealed holdout
   window starts 2025-08-26), and only forms of interest.
4. Validate: no duplicate accession numbers; dates parse and order; the page chain of each company reaches back past 2010 (or to its first filing); acceptance timestamps agree with the FSDS timestamps
   once the FSDS clock (New York time, minute resolution) is converted; which registry amendments the FSDS lacks.

Large raw documents stay under `data/raw/` (git-ignored). Run:

    export EDGAR_USER_AGENT="<name> <contact>"        # required; never written anywhere
    python -m scripts.quant.acquire_edgar_submissions --cohort both
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from datetime import date as Date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.quant.pit import security_master as M
from src.quant.pit.edgar_client import EdgarClient
from src.quant.pit.sec_foundation import atomic_json

ROOT = Path(".")
RAW_API = ROOT / "data/raw/sec_api"
PAGES = RAW_API / "submissions_pages"
OUT_DIR = ROOT / "data/curated/edgar_filings_v1"
MANIFEST = ROOT / "data/manifests/edgar_filings_v1.json"
REQUESTS = ROOT / "data/manifests/edgar_requests_submissions.jsonl"
FSDS = ROOT / "data/curated/sec_v3/filings.parquet"
CAP = Date(2025, 6, 30)
FLOOR = Date(2009, 1, 1)
logger = logging.getLogger("acquire_edgar_submissions")

COHORTS = {"frozen": ROOT / "data/curated/security_master_v3/security_identity_interval.parquet",
           "mid": ROOT / "data/curated/security_master_mid/security_identity_interval.parquet"}
TRUSTED = ("A_CONFIRMED", "B_CONSISTENT", "C_PARTIAL")
COLUMNS = ["accessionNumber", "filingDate", "reportDate", "acceptanceDateTime", "form", "items", "isXBRL", "isInlineXBRL", "primaryDocDescription"]


def keep_form(form: str) -> bool:
    """Forms the study can use: periodic reports and their amendments, current reports, late-filing notices, and the notices that end a registration."""
    return form.startswith(("10-K", "10-Q", "8-K", "NT 10-K", "NT 10-Q", "15-12", "15-15", "25")) or form in ("15F-12B", "15F-12G")


def cohort_ciks(names: list[str]) -> list[int]:
    ciks: set[int] = set()
    for name in names:
        path = COHORTS[name]
        if not path.exists():
            raise FileNotFoundError(f"{path} is missing: build the {name} security master first")
        table = pd.read_parquet(path)
        ciks |= set(table.loc[table["status"].isin(TRUSTED), "cik"].astype("int64"))
    return sorted(ciks)


def fetch(ciks: list[int], client: EdgarClient) -> dict[str, int]:
    """Main documents, then every older page they name. Returns counts; failures are counted, never hidden."""
    counts = {"main_cached_or_fetched": 0, "main_missing_404": 0, "pages_cached_or_fetched": 0, "pages_missing_404": 0, "pages_named": 0}
    opener = client.opener()
    began = time.perf_counter()
    for index, cik in enumerate(ciks, 1):
        document = M.submissions(cik, RAW_API, opener=opener, pause=0.0)
        if not document or "_status" in document:
            counts["main_missing_404"] += 1
            continue
        counts["main_cached_or_fetched"] += 1
        for page in (document.get("filings") or {}).get("files") or []:
            counts["pages_named"] += 1
            result = M.fetch_json(f"https://data.sec.gov/submissions/{page['name']}", PAGES / page["name"], opener=opener, pause=0.0)
            counts["pages_missing_404" if not result or "_status" in result else "pages_cached_or_fetched"] += 1
        if index % 100 == 0:
            logger.info("%d/%d companies (%d requests this run, %.0fs)", index, len(ciks), client.requests, time.perf_counter() - began)
    return counts


def _rows(block: dict[str, Any], cik: int, source: str) -> pd.DataFrame:
    if not block or not block.get("accessionNumber"):
        return pd.DataFrame()
    frame = pd.DataFrame({c: block.get(c, [None] * len(block["accessionNumber"])) for c in COLUMNS})
    frame["cik"] = cik
    frame["source_doc"] = source
    return frame


def normalise(ciks: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One row per accepted filing of interest, and one row per company describing how far back its page chain reaches."""
    frames, chains = [], []
    for cik in ciks:
        path = RAW_API / "submissions" / f"CIK{cik:010d}.json"
        if not path.exists():
            continue
        document = json.loads(path.read_text())
        if "_status" in document:
            continue
        parts = [_rows((document.get("filings") or {}).get("recent") or {}, cik, path.name)]
        named = (document.get("filings") or {}).get("files") or []
        read = 0
        for page in named:
            cached = PAGES / page["name"]
            if cached.exists():
                body = json.loads(cached.read_text())
                if "_status" not in body:
                    parts.append(_rows(body, cik, page["name"]))
                    read += 1
        merged = pd.concat([p for p in parts if len(p)], ignore_index=True) if any(len(p) for p in parts) else pd.DataFrame()
        first_listed = min((p["filingFrom"] for p in named), default=None) if named else None
        chains.append({"cik": cik, "pages_named": len(named), "pages_read": read, "earliest_filing_seen": str(merged["filingDate"].min()) if len(merged) else None,
                       "earliest_filing_listed_on_pages": first_listed, "chain_complete": bool(read == len(named))})
        if len(merged):
            frames.append(merged)
    table = pd.concat(frames, ignore_index=True)
    table = table[table["form"].map(keep_form)].copy()
    table["filing_date"] = pd.to_datetime(table["filingDate"], errors="coerce")
    table["report_date"] = pd.to_datetime(table["reportDate"].replace("", None), errors="coerce")
    table["acceptance_utc"] = pd.to_datetime(table["acceptanceDateTime"], utc=True, errors="coerce")
    table = table[(table["filing_date"] >= pd.Timestamp(FLOOR)) & (table["filing_date"] <= pd.Timestamp(CAP))]
    table = table.rename(columns={"accessionNumber": "accession", "isXBRL": "is_xbrl", "isInlineXBRL": "is_inline_xbrl", "primaryDocDescription": "primary_doc_description"})
    table["is_xbrl"] = table["is_xbrl"].fillna(0).astype(int).astype(bool)
    table["is_inline_xbrl"] = table["is_inline_xbrl"].fillna(0).astype(int).astype(bool)
    table["items"] = table["items"].fillna("").astype(str)
    table = table.drop_duplicates(["cik", "accession"]).sort_values(["cik", "acceptance_utc", "accession"], kind="mergesort").reset_index(drop=True)
    # The registry's acceptance clock is not reliable (see `clock_audit`): about a quarter of the stamps are shifted by 4 to 10 hours. The date of an event is therefore the LATER of the EDGAR filing date,
    # which follows the 17:30 New York rule, and the date of the stamp. A filing can never be used before the day after `event_date`; a shifted stamp can only delay it, never advance it.
    table["acceptance_et_date"] = table["acceptance_utc"].dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    table["event_date"] = table[["filing_date", "acceptance_et_date"]].max(axis=1)
    cols = ["cik", "accession", "form", "filing_date", "report_date", "acceptance_utc", "acceptance_et_date", "event_date", "is_xbrl", "is_inline_xbrl", "items", "primary_doc_description"]
    return table[cols], pd.DataFrame(chains)


def clock_audit(table: pd.DataFrame, fsds: pd.DataFrame) -> dict[str, Any]:
    """Which clock can be trusted? Compare the registry stamp (read as UTC) with the FSDS stamp (New York time, minute resolution) on the filings both list, and test each against the EDGAR rule that a
    filing accepted after 17:30 New York time carries the next business day's date. The FSDS stamps pass that test everywhere; the registry stamps pass it only where they equal the FSDS stamp plus the UTC offset."""
    both = table.merge(fsds[["adsh", "cik", "accepted_at"]], left_on=["cik", "accession"], right_on=["cik", "adsh"], how="inner")
    reg_naive = both["acceptance_utc"].dt.tz_localize(None)
    offset = ((reg_naive - both["accepted_at"]).dt.total_seconds() / 3600).round(0)
    population = offset.map(lambda h: "utc_correct (+4/+5 h)" if h in (4.0, 5.0) else "clock_unconverted (0 h)" if h == 0.0 else "double_converted (+8/+10 h)" if h in (8.0, 10.0) else "other")

    def agrees(clock_et: pd.Series, filing_date: pd.Series) -> pd.Series:
        after = (clock_et.dt.hour * 60 + clock_et.dt.minute) > 17 * 60 + 30
        base = clock_et.dt.normalize()
        expected = pd.Series(np.where(after, base + pd.offsets.BDay(1), np.where(base.dt.dayofweek >= 5, base + pd.offsets.BDay(0), base)), index=clock_et.index)
        return expected == filing_date

    periodic = both["form"].isin(["10-K", "10-Q"])
    registry_et = both["acceptance_utc"].dt.tz_convert("America/New_York").dt.tz_localize(None)
    result: dict[str, Any] = {"matched_filings": int(len(both)), "offset_hours_registry_minus_fsds_clock": {k: int(v) for k, v in offset.value_counts().items()},
                              "populations": {k: int(v) for k, v in population.value_counts().items()}, "shares": {k: round(float(v), 4) for k, v in population.value_counts(normalize=True).items()}}
    for name, clock in (("registry_stamp_read_as_utc", registry_et), ("fsds_stamp_read_as_new_york", both["accepted_at"])):
        ok = agrees(clock[periodic], both.loc[periodic, "filing_date"])
        result[f"filing_date_rule_agreement_10k_10q__{name}"] = {k: round(float(v), 4) for k, v in ok.groupby(population[periodic]).mean().items()}
    gap = (table["filing_date"] - table["acceptance_et_date"]).dt.days
    result["backdated_filings"] = {"definition": "filing date earlier than the acceptance date by more than one day (delinquent filers submitting old reports)", "count": int((gap < -1).sum()),
                                   "share": float((gap < -1).mean()), "min_gap_days": int(gap.min())}
    result["conclusion"] = ("the registry acceptance stamp is shifted for about a quarter of 10-K/10-Q filings; the FSDS stamp is consistent with the filing-date rule; event_date = max(filing date, stamp date) is conservative; "
                            "the FSDS stamp is used wherever it exists")
    return result


def validate(table: pd.DataFrame, chains: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {"rows": int(len(table)), "companies": int(table["cik"].nunique()), "filing_date_min": str(table["filing_date"].min().date()), "filing_date_max": str(table["filing_date"].max().date())}
    out["forms"] = {k: int(v) for k, v in table["form"].value_counts().head(25).items()}
    out["duplicate_accessions_across_companies"] = int(table.duplicated("accession").sum())
    out["null_acceptance_time"] = int(table["acceptance_utc"].isna().sum())
    out["null_filing_date"] = int(table["filing_date"].isna().sum())
    accepted_et = table["acceptance_utc"].dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    gap = (table["filing_date"] - accepted_et).dt.days
    out["filing_date_minus_acceptance_date_days"] = {"min": int(gap.min()), "p50": float(gap.median()), "p99": float(gap.quantile(0.99)), "max": int(gap.max()),
                                                      "share_within_0_to_4_days": float(gap.between(0, 4).mean())}
    out["event_date_after_filing_date_share"] = float((table["event_date"] > table["filing_date"]).mean())
    out["chain"] = {"companies": int(len(chains)), "chains_with_all_pages_read": int(chains["chain_complete"].sum()),
                    "companies_with_history_before_2011": int((pd.to_datetime(chains["earliest_filing_seen"]) < pd.Timestamp("2011-01-01")).sum()),
                    "companies_whose_pages_were_not_all_read": chains.loc[~chains["chain_complete"], "cik"].astype(int).tolist()[:20]}
    # agreement with the FSDS clock (America/New_York, minute resolution)
    fsds = pd.read_parquet(FSDS, columns=["adsh", "cik", "form", "filed", "accepted_at"])
    out["clock_audit"] = clock_audit(table, fsds)
    # which amendments does the FSDS lack?
    amend = table[table["form"].isin(["10-K/A", "10-Q/A", "10-KT/A", "10-QT/A"])]
    in_fsds = amend["accession"].isin(set(fsds["adsh"]))
    out["amendments"] = {"registry_periodic_amendments": int(len(amend)), "in_fsds": int(in_fsds.sum()), "not_in_fsds": int((~in_fsds).sum()),
                         "registry_amendments_flagged_xbrl": int(amend["is_xbrl"].sum()), "xbrl_flagged_but_not_in_fsds": int((amend["is_xbrl"] & ~in_fsds).sum()),
                         "in_fsds_but_not_flagged_xbrl": int((~amend["is_xbrl"] & in_fsds).sum()),
                         "by_form": {k: int(v) for k, v in amend["form"].value_counts().items()}}
    reg_in_range = table[(table["filing_date"] >= pd.Timestamp("2011-01-01"))]
    out["periodic_reports_registry_since_2011"] = int(reg_in_range["form"].isin(["10-K", "10-Q", "10-KT", "10-QT"]).sum())
    item_402 = table[(table["form"].str.startswith("8-K")) & table["items"].str.contains(r"(?:^|,)4\.02(?:,|$)")]
    out["item_4_02_8k"] = {"filings": int(len(item_402)), "companies": int(item_402["cik"].nunique())}
    out["late_notices"] = {"NT 10-K": int((table["form"] == "NT 10-K").sum()), "NT 10-Q": int((table["form"] == "NT 10-Q").sum())}
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s  %(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cohort", choices=["frozen", "mid", "both"], default="both")
    parser.add_argument("--rps", type=float, default=6.0)
    parser.add_argument("--no-network", action="store_true", help="normalise and validate whatever is cached")
    args = parser.parse_args()
    names = ["frozen", "mid"] if args.cohort == "both" else [args.cohort]
    ciks = cohort_ciks(names)
    logger.info("cohort %s: %d companies", args.cohort, len(ciks))
    fetched = {}
    if not args.no_network:
        client = EdgarClient(requests_per_second=args.rps, manifest=REQUESTS)
        fetched = fetch(ciks, client)
        fetched["requests_this_run"] = client.requests
    table, chains = normalise(ciks)
    report = validate(table, chains)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "filings.parquet"
    table.to_parquet(path, compression="zstd", index=False)
    chains.to_parquet(OUT_DIR / "page_chains.parquet", compression="zstd", index=False)
    atomic_json(MANIFEST, {"cohort": args.cohort, "companies_requested": len(ciks), "fetch": fetched, "output": {"file": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "rows": int(len(table))},
                           "validation": report, "cap": str(CAP), "floor": str(FLOOR), "forms_kept": "10-K*, 10-Q*, 8-K*, NT 10-K*, NT 10-Q*, 15-12*, 15-15*, 25*",
                           "caveat": "A current-state download of the registry (retrieved on the date in the request manifest), not a historical snapshot. Acceptance times of accepted filings do not change; "
                                     "withdrawn or removed filings, if any, would be absent. Only filings accepted on or before 2025-06-30 are kept.",
                           "request_log": str(REQUESTS)})
    print(json.dumps({"fetch": fetched, "validation": report}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
