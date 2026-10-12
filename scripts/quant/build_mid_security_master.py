"""Security master for the independent firm sample (ranks 251 to 1,000): ticker to CIK identity intervals, industry classification, share counts, exit evidence.

Re-runs, for the new universe, exactly the construction `src/quant/pit/security_master_build.py` used for the frozen 250-name universe, with three differences, all deliberate:

* the symbols come from `data/research_mid/universe/mid.json` and the prices from `data/research_mid/` (never later than the research cutoff 2025-05-09); vendor names come from the frozen store's symbol table, restricted to snapshots on or before the cutoff;
* outputs go to `data/curated/security_master_mid/`; the frozen `security_master_v3` is not touched;
* SEC documents are fetched through `EdgarClient` (declared contact read from `EDGAR_USER_AGENT`, paced at 6 requests per second, one manifest line per request), into the same on-disk cache the frozen
  build used (`data/raw/sec_api`), so a document already fetched for the frozen universe is not fetched again.

Identity is the crux for survivorship: a name that later delisted must resolve to the right company in the months it was liquid. The resolver grades every link (confirmed by name history and exit
evidence, consistent, partial, unresolved); the panel uses only the grades the frozen panel trusted.

    export EDGAR_USER_AGENT="<name> <contact>"        # required; never written anywhere
    python -m scripts.quant.build_mid_security_master
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import sys
import time
from datetime import date as Date, datetime, timezone
from pathlib import Path

import pandas as pd

from src.quant.pit import pit_coverage as C
from src.quant.pit import security_master as M
from src.quant.pit.calendar import TradingCalendar
from src.quant.pit.edgar_client import EdgarClient
from src.quant.pit.security_master_build import _write, build_shares
from src.quant.pit.sec_foundation import atomic_json
from src.quant.pit.universe import UniverseHistory

CUTOFF = Date(2025, 5, 9)
ROOT = Path(".")
MID = ROOT / "data/research_mid"
OUT = ROOT / "data/curated/security_master_mid"
RAW_API = ROOT / "data/raw/sec_api"
logger = logging.getLogger("build_mid_security_master")


def load_mid_ohlcv(cutoff: Date = CUTOFF) -> pd.DataFrame:
    parts = []
    for path in sorted(glob.glob(str(MID / "raw/dolthub_stocks_ohlcv/part-*.parquet"))):
        frame = pd.read_parquet(path, columns=["date", "symbol", "close"])
        frame["date"] = pd.to_datetime(frame["date"])
        parts.append(frame[frame["date"] <= pd.Timestamp(cutoff)])
    return pd.concat(parts, ignore_index=True)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s  %(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-network", action="store_true", help="use only documents already cached (identity grades will be lower)")
    parser.add_argument("--rps", type=float, default=6.0)
    args = parser.parse_args()
    began = time.perf_counter()
    facts_dir = ROOT / "data/curated/sec_v3"
    registry = pd.read_parquet(facts_dir / "filings.parquet")
    registry["cik"] = registry["cik"].astype("int64")
    universe = UniverseHistory.load(MID / "universe", name="mid")
    symbols = sorted({s for snap in universe.snapshots if snap.as_of <= CUTOFF for s in snap.symbols})
    ohlcv = load_mid_ohlcv()
    ohlcv = ohlcv[ohlcv["symbol"].isin(symbols)]
    windows = M.price_windows(ohlcv)
    # vendor names: the frozen store's copy of the symbol table, snapshots on or before the cutoff only (the table runs to 2026-08, inside the sealed holdout window), latest snapshot per symbol
    vendor = pd.read_parquet(ROOT / "data/research/raw/dolthub_stocks_symbol/part-all.parquet", columns=["symbol", "security_name", "listing_exchange", "date"])
    vendor = vendor[pd.to_datetime(vendor["date"]) <= pd.Timestamp(CUTOFF)].sort_values("date", kind="mergesort")[["symbol", "security_name", "listing_exchange"]]
    snapshot_path = ROOT / "data/raw/security_master/company_tickers_exchange.json"
    payload = json.loads(snapshot_path.read_text())
    current = pd.DataFrame(payload["data"], columns=[str(f).lower() for f in payload["fields"]])
    current["ticker"] = current["ticker"].astype(str).str.upper()
    snapshot_at = datetime.fromtimestamp(snapshot_path.stat().st_mtime, tz=timezone.utc)

    client = None if args.no_network else EdgarClient(requests_per_second=args.rps, manifest=ROOT / "data/manifests/edgar_requests_mid_security_master.jsonl")
    opener = client.opener() if client else None
    histories: dict[int, list] = {}
    evidence: dict[int, list] = {}
    fetched: set[int] = set()
    resolution = M.resolve_universe(symbols, current, vendor, registry, windows, evidence_end=CUTOFF)
    for round_ in range(3):
        wanted = set(resolution["cik"].dropna().astype(int)) - fetched
        logger.info("round %d: %d CIKs to look up", round_ + 1, len(wanted))
        if not wanted or args.no_network:
            break
        for index, cik in enumerate(sorted(wanted), 1):
            document = M.submissions(cik, RAW_API, opener=opener, pause=0.0)
            fetched.add(cik)
            if document and "_status" not in document:
                histories[cik] = M.name_history(document)
                evidence[cik] = M.exit_evidence(document)
            if index % 200 == 0:
                logger.info("submissions %d/%d (%d requests so far)", index, len(wanted), client.requests if client else 0)
        resolution = M.resolve_universe(symbols, current, vendor, registry, windows, histories=histories, evidence_end=CUTOFF)
    identities = M.identity_intervals(resolution, retrieved_at=snapshot_at, last_data_date=CUTOFF)
    M.check_no_overlap(identities)
    identities = identities.assign(cik=identities["cik"].astype("int64"))
    maps, hashes = M.load_french_maps(ROOT / "data/raw/french_sic")
    classification = M.classification_intervals(registry, identities, maps, version=f"{M.SECURITY_MASTER_VERSION}+french-sic-{'-'.join(h[:8] for h in hashes.values())}")
    names = pd.DataFrame([{"cik": cik, **row} for cik, rows in histories.items() for row in rows])
    if len(names):
        names = names.merge(identities[["security_id", "cik"]].drop_duplicates(), on="cik", how="inner")
    last_seen = {t: w.last for t, w in windows.items()}
    exits = M.exit_events(identities[identities["status"].isin(["A_CONFIRMED", "B_CONSISTENT", "C_PARTIAL"])], evidence, last_seen)
    calendar = TradingCalendar.from_dates(sorted(set(ohlcv["date"].dt.date)) + [d.date() for d in pd.bdate_range("2025-05-10", "2025-06-30")])
    # dei share counts are fetched through the same client (progress logged here; build_shares then reads the filled cache)
    trusted = identities[identities["status"].isin(C.TRUSTED_GRADES)][["security_id", "cik"]].drop_duplicates()
    if not args.no_network:
        for index, cik in enumerate(sorted(trusted["cik"].unique()), 1):
            M.dei_shares_concept(int(cik), RAW_API, opener=opener, pause=0.0)
            if index % 200 == 0:
                logger.info("dei shares %d/%d (%d requests so far)", index, trusted["cik"].nunique(), client.requests if client else 0)
    if opener is not None:                       # any document still missing from the cache is fetched through the client, never with the library's built-in agent
        original = M.dei_shares_concept
        M.dei_shares_concept = lambda cik, raw_dir, **kw: original(cik, raw_dir, opener=opener, pause=0.0)
    shares = build_shares(ROOT, identities, registry, facts_dir, RAW_API, calendar, network=not args.no_network)
    for name, frame in (("security_identity_interval", identities), ("security_classification_interval", classification), ("security_name_interval", names),
                        ("security_exit_event", exits), ("shares_fact_vintage", shares), ("universe_resolution", resolution)):
        _write(frame, OUT / f"{name}.parquet")
    grades = resolution["grade"].value_counts().to_dict()
    report = {"symbols": len(symbols), "resolution_grades": {k: int(v) for k, v in grades.items()}, "identity_intervals": int(len(identities)),
              "trusted_securities": int(trusted["security_id"].nunique()), "unresolved_tickers": int((resolution["grade"] == "UNRESOLVED").sum()),
              "classification_intervals": int(len(classification)), "shares_vintages": int(len(shares)), "exit_events": int(len(exits)),
              "submissions_documents_looked_up": len(fetched), "sec_requests_this_run": client.requests if client else 0,
              "french_sic_sha256": hashes, "cutoff": str(CUTOFF), "seconds": round(time.perf_counter() - began, 1),
              "note": "no request header is recorded anywhere; see data/manifests/edgar_requests_mid_security_master.jsonl for URLs, statuses and body hashes"}
    atomic_json(ROOT / "data/manifests/mid_security_master_coverage.json", report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
