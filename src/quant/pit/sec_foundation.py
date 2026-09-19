"""Point-in-time SEC fundamentals and CIK-centred security-master foundation.

The SEC quarterly Financial Statement Data Sets are the canonical rebuild input.
Every filing vintage is retained; selection into ``first_reported`` or ``as_of``
is a view operation, never a destructive coalesce.  Current SEC ticker data is
accepted only as current evidence and never back-dated.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date as Date, datetime, time as Clock, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

import numpy as np
import pandas as pd

from src.quant.pit.calendar import TradingCalendar

SEC_BASE = "https://www.sec.gov/files/dera/data/financial-statement-data-sets"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
TAG_MAP_VERSION = "sec-core-facts-v2"
FF_INDUSTRY_VERSION = "french-12-sic-2024-07"
DEFAULT_USER_AGENT = "miniAladdin-research aakashjawle101@gmail.com"
REQUIRED_MEMBERS = {"sub.txt", "num.txt", "tag.txt", "pre.txt"}

# Alternatives are ordered.  Context type is part of the mapping so instant and
# duration facts can never be silently mixed.
TAG_MAP: dict[str, dict[str, Any]] = {
    "revenue": {"context": "duration", "tags": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"]},
    "gross_profit": {"context": "duration", "tags": ["GrossProfit"]},
    "operating_income": {"context": "duration", "tags": ["OperatingIncomeLoss"]},
    "net_income": {"context": "duration", "tags": ["NetIncomeLoss", "ProfitLoss"]},
    "assets": {"context": "instant", "tags": ["Assets"]},
    "current_assets": {"context": "instant", "tags": ["AssetsCurrent"]},
    "liabilities": {"context": "instant", "tags": ["Liabilities"]},
    "current_liabilities": {"context": "instant", "tags": ["LiabilitiesCurrent"]},
    "equity": {"context": "instant", "tags": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]},
    "cash": {"context": "instant", "tags": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]},
    "operating_cash_flow": {"context": "duration", "tags": ["NetCashProvidedByUsedInOperatingActivities"]},
    "capital_expenditure": {"context": "duration", "tags": ["PaymentsToAcquirePropertyPlantAndEquipment"]},
    "shares_outstanding": {"context": "instant", "tags": ["EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding"]},
}
TAG_LOOKUP = {
    tag: (fact, priority, spec["context"])
    for fact, spec in TAG_MAP.items()
    for priority, tag in enumerate(spec["tags"])
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    os.replace(temporary, path)


def archive_specs(start_year: int = 2011, end_year: int = 2025, end_quarter: int = 2) -> list[dict[str, Any]]:
    return [
        {"year": year, "quarter": quarter, "filename": f"{year}q{quarter}.zip",
         "url": f"{SEC_BASE}/{year}q{quarter}.zip"}
        for year in range(start_year, end_year + 1)
        for quarter in range(1, 5)
        if (year, quarter) <= (end_year, end_quarter)
    ]


def _request(url: str, *, method: str = "GET", user_agent: str = DEFAULT_USER_AGENT,
             timeout: int = 60) -> urllib.response.addinfourl:
    request = urllib.request.Request(url, method=method, headers={
        "User-Agent": user_agent, "Accept-Encoding": "identity",
        "Host": "www.sec.gov",
    })
    return urllib.request.urlopen(request, timeout=timeout)


def estimate_download(*, user_agent: str = DEFAULT_USER_AGENT) -> dict[str, Any]:
    specs = archive_specs()
    sizes: list[int] = []
    unavailable: list[str] = []
    for spec in specs:
        try:
            with _request(spec["url"], method="HEAD", user_agent=user_agent) as response:
                sizes.append(int(response.headers.get("Content-Length", 0)))
        except Exception:
            unavailable.append(spec["filename"])
        time.sleep(0.11)
    measured = sum(sizes)
    average = (measured / len(sizes)) if sizes else 45 * 1024**2
    raw = int(measured + average * len(unavailable))
    return {
        "archives": len(specs), "head_sizes_available": len(sizes),
        "unavailable_heads": unavailable, "expected_raw_bytes": raw,
        "expected_raw_gib": round(raw / 1024**3, 2),
        "expected_extracted_gib": round(raw * 4.0 / 1024**3, 2),
        "expected_curated_gib": round(max(raw * 0.3, 300 * 1024**2) / 1024**3, 2),
        "expected_runtime": "1-6 hours for first full download/build; resumable by quarter",
        "peak_ram": "bounded quarter/chunk processing; target 4-10 GiB, hard operational target <18 GiB",
        "window": "2011Q1-2025Q2; curated accepted_at cutoff 2025-05-09",
    }


def verify_zip(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = {Path(name).name.lower() for name in archive.namelist()}
        missing = REQUIRED_MEMBERS - names
        if missing:
            raise ValueError(f"{path.name} is missing {sorted(missing)}")
        corrupt = archive.testzip()
        if corrupt:
            raise ValueError(f"{path.name} has corrupt member {corrupt}")


def _download_one(spec: Mapping[str, Any], destination: Path, *, user_agent: str,
                  attempts: int = 4) -> dict[str, Any]:
    final = destination / str(spec["filename"])
    temporary = final.with_suffix(".zip.part")
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with _request(str(spec["url"]), user_agent=user_agent, timeout=120) as response, temporary.open("wb") as out:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    out.write(block)
                headers = dict(response.headers.items())
            verify_zip(temporary)
            os.replace(temporary, final)
            return {
                **dict(spec), "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "bytes": final.stat().st_size, "sha256": sha256_file(final),
                "http": {key: headers.get(key) for key in ("ETag", "Last-Modified", "Content-Length") if headers.get(key)},
                "members": sorted(REQUIRED_MEMBERS),
            }
        except Exception as error:
            last_error = error
            temporary.unlink(missing_ok=True)
            if attempt + 1 < attempts:
                time.sleep(min(8.0, 0.75 * (2**attempt)))
    raise RuntimeError(f"failed to download {spec['url']} after {attempts} attempts: {last_error}")


def download_sec(raw_dir: Path, manifest_path: Path, *, user_agent: str = DEFAULT_USER_AGENT,
                 force: bool = False) -> dict[str, Any]:
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    old = json.loads(Path(manifest_path).read_text()) if Path(manifest_path).exists() else {"archives": []}
    recorded = {row["filename"]: row for row in old.get("archives", [])}
    rows = []
    for index, spec in enumerate(archive_specs(), 1):
        final = raw_dir / spec["filename"]
        previous = recorded.get(spec["filename"])
        if not force and final.exists() and previous and final.stat().st_size == previous.get("bytes") and sha256_file(final) == previous.get("sha256"):
            row = previous
            state = "verified"
        else:
            row = _download_one(spec, raw_dir, user_agent=user_agent)
            state = "downloaded"
        rows.append(row)
        atomic_json(Path(manifest_path), {
            "source": "SEC Financial Statement Data Sets", "schema": "sub/num/tag/pre",
            "fair_access_max_requests_per_second": 10, "archives": rows,
        })
        print(f"SEC {index}/{len(archive_specs())} {spec['filename']} {state} {row['bytes']/1024**2:.1f} MiB", flush=True)
        time.sleep(0.11)

    ticker_path = raw_dir.parent / "security_master" / "company_tickers_exchange.json"
    ticker_path.parent.mkdir(parents=True, exist_ok=True)
    if force or not ticker_path.exists():
        temporary = ticker_path.with_suffix(".json.part")
        with _request(SEC_TICKERS_URL, user_agent=user_agent) as response:
            temporary.write_bytes(response.read())
        json.loads(temporary.read_text())
        os.replace(temporary, ticker_path)
    ticker_record = {
        "url": SEC_TICKERS_URL, "filename": ticker_path.name,
        "retrieved_at": datetime.now(timezone.utc).isoformat(), "bytes": ticker_path.stat().st_size,
        "sha256": sha256_file(ticker_path),
        "historical_use": "current bootstrap only; never back-dated",
    }
    manifest = json.loads(Path(manifest_path).read_text())
    manifest["company_tickers_snapshot"] = ticker_record
    manifest["total_bytes"] = sum(row["bytes"] for row in rows) + ticker_record["bytes"]
    atomic_json(Path(manifest_path), manifest)
    return manifest


def _parse_accepted(values: pd.Series) -> pd.Series:
    text = values.astype("string").str.replace(r"\.0$", "", regex=True).str.strip()
    # SEC archives changed from compact YYYYMMDDHHMMSS to a formatted timestamp.
    # Parsing both is part of the source contract; accepted_at may never be
    # manufactured from filed or period end when one representation changes.
    formatted = pd.to_datetime(text, errors="coerce", format="mixed")
    missing = formatted.isna()
    if missing.any():
        formatted.loc[missing] = pd.to_datetime(
            text.loc[missing].str.replace(r"\D", "", regex=True).str[:14],
            format="%Y%m%d%H%M%S", errors="coerce",
        )
    return formatted


def available_session(accepted_at: datetime | pd.Timestamp, calendar: TradingCalendar,
                      close: Clock = Clock(16, 0)) -> Date | None:
    """First session on which a filing is usable at a close-to-close decision."""
    stamp = pd.Timestamp(accepted_at)
    day = stamp.date()
    if calendar.contains(day) and stamp.time() <= close:
        return day
    anchor = day + timedelta(days=1) if stamp.time() > close else day
    return calendar.on_or_after(anchor)


def _period_start(end: pd.Timestamp, quarters: int) -> Date | None:
    if quarters <= 0 or pd.isna(end):
        return None
    # FSDS supplies qtrs, not the instance's exact start date.  This derived
    # field is explicitly labelled in provenance and never used to overwrite a
    # source context.
    return (end - pd.DateOffset(months=3 * quarters) + pd.Timedelta(days=1)).date()


def curate_sec_rows(sub: pd.DataFrame, num: pd.DataFrame, *, archive_hash: str,
                    calendar: TradingCalendar | None = None,
                    accepted_cutoff: str | datetime = "2025-05-09 23:59:59") -> pd.DataFrame:
    sub = sub.copy()
    sub.columns = [str(column).lower() for column in sub.columns]
    num = num.copy()
    num.columns = [str(column).lower() for column in num.columns]
    sub["accepted_at"] = _parse_accepted(sub["accepted"])
    cutoff = pd.Timestamp(accepted_cutoff)
    sub = sub[sub["accepted_at"].notna() & (sub["accepted_at"] <= cutoff)]
    wanted = num[num["tag"].isin(TAG_LOOKUP)].copy()
    wanted = wanted.merge(sub[[column for column in (
        "adsh", "cik", "form", "filed", "accepted_at", "fy", "fp", "sic", "name", "instance"
    ) if column in sub]], on="adsh", how="inner", validate="many_to_one")
    if wanted.empty:
        return pd.DataFrame(columns=CURATED_COLUMNS)
    mapping = wanted["tag"].map(TAG_LOOKUP)
    wanted["canonical_fact"] = mapping.map(lambda item: item[0])
    wanted["tag_priority"] = mapping.map(lambda item: item[1])
    wanted["context_type"] = mapping.map(lambda item: item[2])
    wanted["qtrs"] = pd.to_numeric(wanted.get("qtrs"), errors="coerce").fillna(0).astype(int)
    wanted = wanted[((wanted["context_type"] == "instant") & (wanted["qtrs"] == 0)) |
                    ((wanted["context_type"] == "duration") & (wanted["qtrs"] > 0))]
    wanted["period_end"] = pd.to_datetime(wanted["ddate"].astype(str), format="%Y%m%d", errors="coerce").dt.date
    end_stamps = pd.to_datetime(wanted["period_end"])
    wanted["period_start"] = [_period_start(end, quarters) for end, quarters in zip(end_stamps, wanted["qtrs"])]
    wanted["period_start_method"] = np.where(wanted["qtrs"] > 0, "derived_from_fsds_qtrs", "instant_not_applicable")
    wanted["taxonomy"] = wanted.get("version", pd.Series("us-gaap", index=wanted.index)).astype("string")
    wanted["accession"] = wanted["adsh"]
    wanted["amendment"] = wanted["form"].astype("string").str.endswith("/A")
    wanted["source_archive_hash"] = archive_hash
    wanted["tag_map_version"] = TAG_MAP_VERSION
    wanted["value"] = pd.to_numeric(wanted["value"], errors="coerce")
    wanted["frame"] = wanted.get("frame", pd.Series(pd.NA, index=wanted.index))
    if calendar is not None:
        wanted["available_session"] = [available_session(value, calendar) for value in wanted["accepted_at"]]
    else:
        wanted["available_session"] = pd.NaT
    return wanted.reindex(columns=CURATED_COLUMNS).sort_values(
        ["accepted_at", "cik", "canonical_fact", "period_end", "tag_priority", "accession"],
        kind="stable",
    ).reset_index(drop=True)


CURATED_COLUMNS = [
    "cik", "accession", "form", "filed", "accepted_at", "available_session", "fy", "fp",
    "taxonomy", "canonical_fact", "tag", "tag_priority", "context_type", "qtrs", "unit", "value",
    "period_start", "period_end", "period_start_method", "frame", "amendment", "source_archive_hash",
    "tag_map_version", "sic", "name",
]


def first_reported(facts: pd.DataFrame) -> pd.DataFrame:
    keys = ["cik", "canonical_fact", "unit", "period_start", "period_end", "context_type"]
    return facts.sort_values(["accepted_at", "tag_priority", "accession"], kind="stable").drop_duplicates(keys, keep="first")


def as_of(facts: pd.DataFrame, decision_time: datetime | str) -> pd.DataFrame:
    eligible = facts[pd.to_datetime(facts["accepted_at"]) <= pd.Timestamp(decision_time)]
    keys = ["cik", "canonical_fact", "unit", "period_start", "period_end", "context_type"]
    return eligible.sort_values(["accepted_at", "tag_priority", "accession"], kind="stable").drop_duplicates(keys, keep="last")


def conflict_report(facts: pd.DataFrame) -> pd.DataFrame:
    keys = ["cik", "canonical_fact", "unit", "period_start", "period_end", "accepted_at"]
    grouped = facts.groupby(keys, dropna=False).agg(rows=("value", "size"), distinct_values=("value", "nunique")).reset_index()
    return grouped[grouped["distinct_values"] > 1]


def _read_member(archive: zipfile.ZipFile, name: str, **kwargs: Any) -> pd.DataFrame:
    actual = next(member for member in archive.namelist() if Path(member).name.lower() == name)
    with archive.open(actual) as handle:
        return pd.read_csv(handle, sep="\t", low_memory=False, **kwargs)


def build_fundamentals(raw_dir: Path, curated_dir: Path, manifest_path: Path, *,
                       calendar_dates: Iterable[Date], universe_ciks: set[int] | None = None,
                       accepted_cutoff: str = "2025-05-09 23:59:59") -> dict[str, Any]:
    raw_dir, curated_dir = Path(raw_dir), Path(curated_dir)
    curated_dir.mkdir(parents=True, exist_ok=True)
    download_manifest = json.loads(Path(manifest_path).read_text())
    hash_by_file = {row["filename"]: row["sha256"] for row in download_manifest["archives"]}
    calendar = TradingCalendar.from_dates(calendar_dates)
    summaries = []
    for index, path in enumerate(sorted(raw_dir.glob("????q?.zip")), 1):
        output = curated_dir / f"facts-{path.stem}.parquet"
        with zipfile.ZipFile(path) as archive:
            sub = _read_member(archive, "sub.txt", dtype={"adsh": "string", "cik": "Int64", "accepted": "string", "form": "string"})
            if universe_ciks:
                sub = sub[sub["cik"].isin(universe_ciks)]
            adsh = set(sub["adsh"].dropna())
            parts = []
            actual = next(member for member in archive.namelist() if Path(member).name.lower() == "num.txt")
            with archive.open(actual) as handle:
                for chunk in pd.read_csv(handle, sep="\t", low_memory=False, chunksize=400_000,
                                         dtype={"adsh": "string", "tag": "string", "version": "string", "uom": "string", "frame": "string"}):
                    chunk = chunk[chunk["adsh"].isin(adsh) & chunk["tag"].isin(TAG_LOOKUP)]
                    if not chunk.empty:
                        parts.append(curate_sec_rows(sub, chunk, archive_hash=hash_by_file[path.name], calendar=calendar,
                                                     accepted_cutoff=accepted_cutoff))
            facts = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=CURATED_COLUMNS)
        temporary = output.with_suffix(".parquet.tmp")
        facts.to_parquet(temporary, compression="zstd", index=False)
        os.replace(temporary, output)
        conflicts = conflict_report(facts)
        summaries.append({"quarter": path.stem, "rows": len(facts), "ciks": int(facts["cik"].nunique()),
                          "conflicts": len(conflicts), "output_sha256": sha256_file(output)})
        print(f"CURATE {index} {path.stem}: {len(facts):,} facts / {facts['cik'].nunique():,} CIKs", flush=True)
    report = coverage_report(curated_dir)
    report["quarter_shards"] = summaries
    return report


def coverage_report(curated_dir: Path) -> dict[str, Any]:
    paths = sorted(Path(curated_dir).glob("facts-*.parquet"))
    if not paths:
        return {"status": "NO_CURATED_FACTS", "rows": 0}
    frames = [pd.read_parquet(path, columns=["cik", "canonical_fact", "tag", "tag_priority", "accepted_at", "value", "unit", "period_start", "period_end"]) for path in paths]
    facts = pd.concat(frames, ignore_index=True)
    facts["year"] = pd.to_datetime(facts["accepted_at"]).dt.year
    conflicts = conflict_report(facts)
    return {
        "status": "BUILT", "rows": int(len(facts)), "companies": int(facts["cik"].nunique()),
        "accepted_min": str(facts["accepted_at"].min()), "accepted_max": str(facts["accepted_at"].max()),
        "coverage_by_year": {str(k): int(v) for k, v in facts.groupby("year").size().items()},
        "coverage_by_fact": {str(k): int(v) for k, v in facts.groupby("canonical_fact").size().items()},
        "companies_by_fact": {str(k): int(v) for k, v in facts.groupby("canonical_fact")["cik"].nunique().items()},
        "fallback_tag_rate": float((facts["tag_priority"] > 0).mean()),
        "missing_value_rate": float(facts["value"].isna().mean()), "conflict_count": int(len(conflicts)),
        "tag_map_version": TAG_MAP_VERSION,
    }


def ff12_from_sic(sic: int | float | None) -> str | None:
    if sic is None or pd.isna(sic):
        return None
    value = int(sic)
    groups = {
        "NoDur": [(100, 999), (2000, 2399), (2700, 2749), (2770, 2799), (3100, 3199), (3940, 3989)],
        "Durbl": [(2500, 2519), (2590, 2599), (3630, 3659), (3710, 3711), (3714, 3714), (3716, 3716), (3750, 3751), (3792, 3792), (3900, 3939), (3990, 3999)],
        "Manuf": [(2520, 2589), (2600, 2699), (2750, 2769), (3000, 3099), (3200, 3569), (3580, 3629), (3700, 3709), (3712, 3713), (3715, 3715), (3717, 3749), (3752, 3791), (3793, 3799), (3830, 3839), (3860, 3899)],
        "Enrgy": [(1200, 1399), (2900, 2999)], "Chems": [(2800, 2829), (2840, 2899)],
        "BusEq": [(3570, 3579), (3660, 3692), (3694, 3699), (3810, 3829), (7370, 7379)],
        "Telcm": [(4800, 4899)], "Utils": [(4900, 4949)],
        "Shops": [(5000, 5999), (7200, 7299), (7600, 7699)],
        "Hlth": [(2830, 2839), (3693, 3693), (3840, 3859), (8000, 8099)],
        "Money": [(6000, 6999)],
    }
    for label, ranges in groups.items():
        if any(start <= value <= end for start, end in ranges):
            return label
    return "Other"


def validate_identity_intervals(intervals: pd.DataFrame) -> None:
    for security_id, group in intervals.sort_values("effective_from").groupby("security_id"):
        previous_end: pd.Timestamp | None = None
        previous_was_open = False
        for position, row in enumerate(group.itertuples(index=False)):
            start, end = pd.Timestamp(row.effective_from), pd.Timestamp(row.effective_to) if pd.notna(row.effective_to) else None
            if position and previous_was_open:
                raise ValueError(f"overlap for security {security_id}")
            if previous_end is not None and start <= previous_end:
                raise ValueError(f"overlap for security {security_id}")
            previous_end = end
            previous_was_open = end is None


def build_security_master(ticker_snapshot: Path, universe_symbols: Sequence[str], facts_dir: Path,
                          output_dir: Path, *, local_symbol_snapshot: Path | None = None) -> dict[str, Any]:
    payload = json.loads(Path(ticker_snapshot).read_text())
    current = pd.DataFrame(payload["data"], columns=[str(field).lower() for field in payload["fields"]])
    current["ticker"] = current["ticker"].astype(str).str.upper()
    current = current[current["ticker"].isin({str(symbol).upper() for symbol in universe_symbols})].copy()
    retrieved = datetime.fromtimestamp(Path(ticker_snapshot).stat().st_mtime, tz=timezone.utc)
    current["security_id"] = ["sec-" + hashlib.sha256(f"{int(cik)}:{ticker}".encode()).hexdigest()[:20]
                              for cik, ticker in zip(current["cik"], current["ticker"])]
    current["effective_from"] = retrieved.date()
    current["effective_to"] = pd.NaT
    current["source"] = "sec_company_tickers_current_snapshot"
    current["accession"] = pd.NA
    current["retrieved_at"] = retrieved
    identities = current[["security_id", "cik", "ticker", "exchange", "name", "effective_from", "effective_to", "source", "accession", "retrieved_at"]]
    validate_identity_intervals(identities)

    fact_paths = sorted(Path(facts_dir).glob("facts-*.parquet"))
    metadata = [pd.read_parquet(path, columns=["cik", "sic", "accepted_at", "accession"]).dropna(subset=["sic"]) for path in fact_paths]
    classifications = pd.concat(metadata, ignore_index=True) if metadata else pd.DataFrame(columns=["cik", "sic", "accepted_at", "accession"])
    classifications = classifications.sort_values(["cik", "accepted_at", "accession"]).drop_duplicates(["cik", "accepted_at", "sic"])
    # One SIC state per acceptance instant; a later different SIC closes the
    # former interval. Repeated filings with the same SIC create no new state.
    classifications = classifications.drop_duplicates(["cik", "accepted_at"], keep="last")
    classifications = classifications[
        classifications.groupby("cik")["sic"].shift().ne(classifications["sic"])
    ].copy()
    classifications = classifications.merge(identities[["cik", "security_id"]], on="cik", how="inner")
    classifications = classifications.sort_values(["security_id", "accepted_at"])
    classifications["effective_from"] = pd.to_datetime(classifications["accepted_at"])
    classifications["effective_to"] = (
        classifications.groupby("security_id")["effective_from"].shift(-1) - pd.Timedelta(microseconds=1)
    )
    classifications["ff_industry"] = classifications["sic"].map(ff12_from_sic)
    classifications["source_accession"] = classifications["accession"]
    classifications["mapping_version"] = FF_INDUSTRY_VERSION
    classifications = classifications[["security_id", "sic", "ff_industry", "effective_from", "effective_to", "source_accession", "mapping_version"]]

    share_columns = ["cik", "canonical_fact", "period_end", "accepted_at", "accession", "form", "tag", "unit", "value", "amendment"]
    shares_parts = [pd.read_parquet(path, columns=share_columns) for path in fact_paths]
    shares = pd.concat(shares_parts, ignore_index=True) if shares_parts else pd.DataFrame(columns=CURATED_COLUMNS)
    shares = shares[shares["canonical_fact"] == "shares_outstanding"].merge(identities[["cik", "security_id"]], on="cik", how="inner")
    shares = shares.rename(columns={"accession": "accession"})
    shares = shares[["security_id", "period_end", "accepted_at", "accession", "form", "tag", "unit", "value", "amendment"]].rename(columns={"amendment": "is_amendment"})

    symbols = pd.DataFrame({"ticker": sorted(set(map(str.upper, universe_symbols)))})
    resolution = symbols.merge(identities[["ticker", "security_id", "cik"]], on="ticker", how="left")
    duplicates = resolution.groupby("ticker")["security_id"].nunique()
    ambiguous = set(duplicates[duplicates > 1].index)
    resolution["resolution_status"] = np.where(resolution["security_id"].isna(), "UNRESOLVED_NO_SEC_CURRENT_MATCH",
                                                 np.where(resolution["ticker"].isin(ambiguous), "UNRESOLVED_AMBIGUOUS", "RESOLVED_CURRENT_ONLY"))

    exits = pd.DataFrame(columns=["security_id", "event_date", "form", "reason", "last_trade_date", "return_treatment", "source_accession"])
    if local_symbol_snapshot is not None and Path(local_symbol_snapshot).exists():
        local = pd.read_parquet(local_symbol_snapshot, columns=["symbol", "date"])
        local = local.rename(columns={"symbol": "ticker", "date": "event_date"})
        local["ticker"] = local["ticker"].astype(str).str.upper()
        exits = local.merge(identities[["ticker", "security_id"]], on="ticker", how="inner")
        exits["form"] = pd.NA
        exits["reason"] = "APPROXIMATED_LOCAL_LAST_SEEN"
        exits["last_trade_date"] = exits["event_date"]
        exits["return_treatment"] = "UNKNOWN_NO_CRSP_DELISTING_RETURN"
        exits["source_accession"] = pd.NA
        exits = exits[["security_id", "event_date", "form", "reason", "last_trade_date", "return_treatment", "source_accession"]]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in (("security_identity_interval", identities), ("security_classification_interval", classifications),
                        ("shares_fact_vintage", shares), ("security_exit_event", exits),
                        ("universe_resolution", resolution)):
        temporary = output_dir / f"{name}.parquet.tmp"
        frame.to_parquet(temporary, compression="zstd", index=False)
        os.replace(temporary, output_dir / f"{name}.parquet")
    resolved = resolution[resolution["resolution_status"] == "RESOLVED_CURRENT_ONLY"]
    return {
        "identity_evidence": "current SEC snapshot only; no historical dates inferred",
        "universe_members": len(symbols), "resolved_current_only": int(resolved["ticker"].nunique()),
        "unresolved": int((resolution["resolution_status"] != "RESOLVED_CURRENT_ONLY").sum()),
        "identity_intervals": len(identities), "classification_rows": len(classifications),
        "sic_coverage_of_resolved": float(classifications["security_id"].nunique() / max(resolved["security_id"].nunique(), 1)),
        "shares_rows": len(shares), "shares_security_coverage": int(shares["security_id"].nunique()),
        "exit_events": len(exits), "exit_event_quality": "APPROXIMATED from local last_seen; returns UNKNOWN",
        "neutralization_allowed": False,
        "neutralization_blocker": "historical identity intervals remain incomplete; current ticker snapshot is not back-dated",
        "ff_mapping_version": FF_INDUSTRY_VERSION,
    }
