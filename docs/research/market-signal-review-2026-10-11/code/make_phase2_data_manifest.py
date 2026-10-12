#!/usr/bin/env python3
"""Phase II dataset manifest: every dataset used or created in Phase II, with provenance, size, checksum, coverage, licence and status.

Status values: EXISTING_VERIFIED (built before Phase II; hash re-checked here), NEWLY_ACQUIRED (downloaded or read from a local clone in Phase II), NEWLY_DERIVED (computed in Phase II from the others),
PLANNED, BLOCKED. Nothing here redistributes data: the manifest records hashes and counts only.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/make_phase2_data_manifest.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[4]
OUT = REPO / "docs/research/market-signal-review-2026-10-11/phase2_data_manifest.json"
SEC_TERMS = "US government public data; SEC fair access (at most 10 requests a second, declared User-Agent)"
DOLT_TERMS = "community open data on DoltHub; licence review is an open owner action; nothing derived from it is redistributed"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_hash(root: Path, pattern: str = "**/*") -> dict:
    files = sorted(p for p in root.glob(pattern) if p.is_file())
    h = hashlib.sha256()
    total = 0
    for p in files:
        h.update(str(p.relative_to(root)).encode())
        h.update(sha256_file(p).encode())
        total += p.stat().st_size
    return {"files": len(files), "bytes": total, "sha256": h.hexdigest(), "method": "sha256 over relative path + sha256 of every file, sorted"}


def parquet_rows(path: Path) -> int:
    import pyarrow.parquet as pq
    return int(pq.ParquetFile(path).metadata.num_rows)


def entry(id_, path, kind, status, provider, source, licence, redistribution, pit, tracked, used_by, caveats, *, tree=False, rows=None, extra=None):
    p = REPO / path
    out = {"id": id_, "path": path, "kind": kind, "status": status, "provider": provider, "source": source, "licence": licence, "redistribution": redistribution, "pit_status": pit,
           "tracked_in_git": tracked, "used_by": used_by, "caveats": caveats}
    if not p.exists():
        out.update({"present": False})
        return out
    out["present"] = True
    if tree or p.is_dir():
        out["tree"] = tree_hash(p)
        if (p / "manifest.json").exists():
            partitions = json.loads((p / "manifest.json").read_text()).get("partitions", [])
            if partitions:
                out["rows"] = int(sum(x["rows"] for x in partitions))
                out["partitions"] = len(partitions)
    else:
        out.update({"bytes": p.stat().st_size, "sha256": sha256_file(p)})
        if p.suffix == ".parquet":
            out["rows"] = parquet_rows(p)
    if rows is not None:
        out["rows"] = rows
    if extra:
        out.update(extra)
    return out


def main() -> int:
    m = lambda name: json.loads((REPO / "data/manifests" / name).read_text())
    ingest, universe, baseline = m("mid_sample_ingest.json"), m("mid_sample_universe.json"), m("mid_sample_baseline.json")
    master, panel, edgar = m("mid_security_master_coverage.json"), m("rich_pit_panel_mid_manifest.json"), m("edgar_filings_v1.json")
    items = [
        entry("P2-01", "data/research_mid/universe/mid.json", "universe membership", "NEWLY_DERIVED", "this project, from DoltHub prices", "scripts/quant/build_independent_sample.py universe", DOLT_TERMS,
              "membership lists only", "point in time (each month's whole-market cross-section, delisted names included)", True, "EXP-014", "not index membership; ranks 251-1,000 by 3-month median dollar volume", extra={"snapshots": universe["snapshots"], "unique_members": universe["unique_members"], "overlap_with_frozen_universe_ever": universe["overlap_with_frozen_universe_ever"]}),
        entry("P2-02", "data/research_mid/raw/dolthub_stocks_ohlcv", "daily prices", "NEWLY_ACQUIRED", "DoltHub post-no-preference/stocks (local clone)", f"clone commit {ingest['clone_commits']['stocks']}", DOLT_TERMS,
              "raw not committed", "prices are not revised; unadjusted; capped 2025-06-30", False, "EXP-014 baseline frame and labels", "no adjusted close; split table starts 2014-03-28; delistings before 2017-10-26 only partly recorded", tree=True),
        entry("P2-03", "data/research_mid/raw/dolthub_stocks_dividend", "dividends", "NEWLY_ACQUIRED", "DoltHub stocks", "same clone", DOLT_TERMS, "raw not committed", "dated ex-dates", False, "labels", "", tree=True),
        entry("P2-04", "data/research_mid/raw/dolthub_stocks_split", "splits", "NEWLY_ACQUIRED", "DoltHub stocks", "same clone", DOLT_TERMS, "raw not committed", "dated ex-dates; none before 2014-03-28", False, "labels", "", tree=True),
        entry("P2-05", "data/research_mid/raw/dolthub_rates_us_treasury", "treasury curve", "NEWLY_ACQUIRED", "DoltHub rates", f"clone commit {ingest['clone_commits']['rates']}", DOLT_TERMS, "raw not committed", "one-session lag in features", False, "baseline features", "", tree=True),
        entry("P2-06", "data/research_mid/derived/mid_baseline_frame.parquet", "26-feature baseline frame and labels", "NEWLY_DERIVED", "this project", "scripts/quant/build_independent_sample.py baseline", DOLT_TERMS, "not redistributed", "point in time by the same builder as the frozen frame", False,
              "EXP-014", "features absent (not zeroed) where optional datasets are missing; those columns are not used", extra={"symbols": baseline["symbols"], "dates": baseline["dates"], "in_universe_rows": baseline["in_universe_rows"], "date_min": baseline["date_min"], "date_max": baseline["date_max"]}),
        entry("P2-07", "data/research_mid/derived/exp014_daily_panel.parquet", "daily forward returns and dollar volume for economics", "NEWLY_DERIVED", "this project", "src/quant/study/exp014.py mid_daily_panel", DOLT_TERMS, "not redistributed", "capped 2025-05-09", False, "EXP-014 economics", ""),
        entry("P2-08", "data/curated/security_master_mid", "identity, classification, shares, exits", "NEWLY_DERIVED", "SEC submissions and XBRL company concepts, DoltHub names", "scripts/quant/build_mid_security_master.py", SEC_TERMS, "derived from public data; not committed",
              "intervals; grades by name history and exit evidence", False, "EXP-014 panel", "ticker is not an identity; 337 tickers unresolved; share counts from cover pages", tree=True, extra={"resolution_grades": master["resolution_grades"], "trusted_securities": master["trusted_securities"]}),
        entry("P2-09", "data/raw/sec_api/submissions", "EDGAR submissions documents (main)", "NEWLY_ACQUIRED", "SEC EDGAR data.sec.gov", "request log data/manifests/edgar_requests_*.jsonl", SEC_TERMS, "public records; not committed for size",
              "current-state download (retrieved 2026-10-12), not a historical snapshot", False, "EXP-014 registry, identity", "acceptance stamps unreliable for about a quarter of matched 10-K/10-Q filings (clock audit)", tree=True),
        entry("P2-10", "data/raw/sec_api/submissions_pages", "EDGAR submissions older pages", "NEWLY_ACQUIRED", "SEC EDGAR data.sec.gov", "request log data/manifests/edgar_requests_submissions.jsonl", SEC_TERMS, "public records; not committed", "current-state download", False, "EXP-014 registry", "", tree=True),
        entry("P2-11", "data/curated/edgar_filings_v1/filings.parquet", "normalised filing registry (periodic reports, amendments, 8-K items, NT notices, exits)", "NEWLY_DERIVED", "SEC EDGAR", "scripts/quant/acquire_edgar_submissions.py", SEC_TERMS,
              "derived counts only", "event_date = max(filing date, stamp date); FSDS stamps used for availability where they exist", False, "EXP-014 secondary analyses", "filings accepted after 2025-06-30 dropped", extra={"companies": edgar["validation"]["companies"], "clock_audit_shares": edgar["validation"]["clock_audit"]["shares"]}),
        entry("P2-12", "data/research/derived/amendment_classification_v1.parquet", "content classification of every FSDS amendment", "NEWLY_DERIVED", "SEC Financial Statement Data Sets", "docs/research/.../code/classify_amendments.py", SEC_TERMS, "derived from public data",
              "usable from each amendment's own acceptance session", False, "EXP-014 treatment", "55% of amendments have a comparable previous version"),
        entry("P2-13", "data/research_mid/derived/rich_pit_panel_mid.parquet", "rich point-in-time panel (76 features) for the independent sample", "NEWLY_DERIVED", "this project", "scripts/quant/build_mid_rich_panel.py", DOLT_TERMS, "not redistributed", "same construction as the frozen panel", False, "EXP-014",
              "size and industry-relative controls withheld", extra={"content_hash": panel["content_hash"], "identity_gate": panel["identity_gate"]["security_master_pit"], "trusted_share": panel["identity"]["share_trusted"]}),
        entry("P2-14", "data/curated/sec_v3/filings.parquet", "FSDS filing registry", "EXISTING_VERIFIED", "SEC Financial Statement Data Sets", "58 quarterly archives 2011Q1-2025Q2", SEC_TERMS, "public domain", "acceptance stamps validated against the 17:30 rule (99.2-99.5% agreement)", False,
              "EXP-012 to EXP-014", ""),
        entry("P2-15", "data/research/derived/rich_pit_panel.parquet", "rich point-in-time panel, discovery sample", "EXISTING_VERIFIED", "this project", "src/quant/pit/rich_panel_build.py", DOLT_TERMS, "not redistributed", "point in time", False, "EXP-012, EXP-013, EXP-014 time-separate sample", ""),
    ]
    OUT.write_text(json.dumps({"generated": "2026-10-12", "phase": "II", "datasets": items,
                               "blocked_or_planned": [{"id": "P2-90", "item": "ALFRED vintages for the live scorer's macro gate", "status": "BLOCKED", "reason": "no FRED/ALFRED key; the owner's decision"},
                                                       {"id": "P2-91", "item": "provider snapshots for the live scorer (fundamentals, analysts, news)", "status": "PLANNED", "reason": "needs provider-terms review and a year of capture; archive library implemented, no capture job"},
                                                       {"id": "P2-92", "item": "full text of Frieder and Shanthikumar (2008) and other SSRN works", "status": "BLOCKED", "reason": "SSRN bot verification; not circumvented"}]},
                              indent=1, default=str) + "\n")
    print(f"wrote {OUT} with {len(items)} entries; present: {sum(1 for i in items if i['present'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
