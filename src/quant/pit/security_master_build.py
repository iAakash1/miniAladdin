"""Build the v3 security master from the v3 SEC store, dated price windows and the SEC's own APIs.

Nothing dated after the research cutoff (2025-05-09) is read from the price data, so a name that stops
trading inside the sealed holdout period is, to research, still trading.
"""

from __future__ import annotations

import glob
import json
import os
from datetime import date as Date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.quant.pit import pit_coverage as C
from src.quant.pit import security_master as M
from src.quant.pit.calendar import TradingCalendar
from src.quant.pit.sec_facts import available_session
from src.quant.pit.sec_foundation import atomic_json

CUTOFF = Date(2025, 5, 9)


def _write(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    frame.to_parquet(tmp, compression="zstd", index=False)
    os.replace(tmp, path)


def research_universe_symbols(universe_file: Path, cutoff: Date = CUTOFF) -> list[str]:
    payload = json.loads(Path(universe_file).read_text())
    return sorted({s for snap in payload["snapshots"] if Date.fromisoformat(snap["as_of"]) <= cutoff for s in snap["symbols"]})


def load_ohlcv(root: Path, cutoff: Date = CUTOFF) -> pd.DataFrame:
    parts = []
    for path in sorted(glob.glob(str(root / "data/research/raw/dolthub_stocks_ohlcv/part-*.parquet"))):
        frame = pd.read_parquet(path, columns=["date", "symbol", "close"])
        frame["date"] = pd.to_datetime(frame["date"])
        parts.append(frame[frame["date"] <= pd.Timestamp(cutoff)])
    return pd.concat(parts, ignore_index=True)


def build(root: Path, *, network: bool = True) -> dict[str, Any]:
    root = Path(root)
    facts_dir = root / "data/curated/sec_v3"
    out_dir = root / "data/curated/security_master_v3"
    raw_api = root / "data/raw/sec_api"
    french_dir = root / "data/raw/french_sic"
    registry = pd.read_parquet(facts_dir / "filings.parquet")
    registry["cik"] = registry["cik"].astype("int64")
    ohlcv = load_ohlcv(root)
    symbols = research_universe_symbols(root / "data/research/universe/liquid.json")
    ohlcv = ohlcv[ohlcv["symbol"].isin(symbols)]
    windows = M.price_windows(ohlcv)
    vendor = pd.read_parquet(root / "data/research/raw/dolthub_stocks_symbol/part-all.parquet", columns=["symbol", "security_name", "listing_exchange"])
    payload = json.loads((root / "data/raw/security_master/company_tickers_exchange.json").read_text())
    current = pd.DataFrame(payload["data"], columns=[str(f).lower() for f in payload["fields"]])
    current["ticker"] = current["ticker"].astype(str).str.upper()
    snapshot_at = datetime.fromtimestamp((root / "data/raw/security_master/company_tickers_exchange.json").stat().st_mtime, tz=timezone.utc)

    histories: dict[int, list[dict[str, Any]]] = {}
    evidence: dict[int, list[dict[str, Any]]] = {}
    fetched: set[int] = set()
    resolution = M.resolve_universe(symbols, current, vendor, registry, windows, evidence_end=CUTOFF)
    for _ in range(3):
        wanted = set(resolution["cik"].dropna().astype(int)) - fetched
        if not wanted or not network:
            break
        for index, cik in enumerate(sorted(wanted), 1):
            document = M.submissions(cik, raw_api)
            fetched.add(cik)
            if document and "_status" not in document:
                histories[cik] = M.name_history(document)
                evidence[cik] = M.exit_evidence(document)
            if index % 100 == 0:
                print(f"submissions {index}/{len(wanted)}", flush=True)
        resolution = M.resolve_universe(symbols, current, vendor, registry, windows, histories=histories, evidence_end=CUTOFF)

    identities = M.identity_intervals(resolution, retrieved_at=snapshot_at, last_data_date=CUTOFF)
    M.check_no_overlap(identities)
    identities = identities.assign(cik=identities["cik"].astype("int64"))

    hashes = M.download_french(french_dir) if network else {}
    maps, hashes = M.load_french_maps(french_dir)
    classification = M.classification_intervals(registry, identities, maps, version=f"{M.SECURITY_MASTER_VERSION}+french-sic-{'-'.join(h[:8] for h in hashes.values())}")

    name_rows = [{"cik": cik, **row} for cik, rows in histories.items() for row in rows]
    names = pd.DataFrame(name_rows)
    names = names.merge(identities[["security_id", "cik"]].drop_duplicates(), on="cik", how="inner") if len(names) else names

    last_seen = {t: w.last for t, w in windows.items()}
    exits = M.exit_events(identities[identities["status"].isin(["A_CONFIRMED", "B_CONSISTENT", "C_PARTIAL"])], evidence, last_seen)

    calendar = TradingCalendar.from_dates(sorted(set(ohlcv["date"].dt.date)) + [d.date() for d in pd.bdate_range("2025-05-10", "2025-06-30")])
    shares = build_shares(root, identities, registry, facts_dir, raw_api, calendar, network=network)

    for name, frame in (("security_identity_interval", identities), ("security_classification_interval", classification),
                        ("security_name_interval", names), ("security_exit_event", exits), ("shares_fact_vintage", shares),
                        ("universe_resolution", resolution)):
        _write(frame, out_dir / f"{name}.parquet")
    return {"resolution": resolution, "identities": identities, "classification": classification, "names": names,
            "exits": exits, "shares": shares, "ohlcv": ohlcv, "french_hashes": hashes, "submissions_fetched": len(fetched)}


def build_shares(root: Path, identities: pd.DataFrame, registry: pd.DataFrame, facts_dir: Path, raw_api: Path,
                 calendar: TradingCalendar, *, network: bool) -> pd.DataFrame:
    trusted = identities[identities["status"].isin(C.TRUSTED_GRADES)][["security_id", "cik"]].drop_duplicates()
    by_accession = registry.drop_duplicates("adsh").set_index("adsh")[["accepted_at", "form", "cik"]]
    parts = []
    for cik in sorted(trusted["cik"].unique()):
        concept = M.dei_shares_concept(int(cik), raw_api) if network else None
        if concept and "_status" not in concept:
            rows = M.dei_share_rows(concept, by_accession)
            if len(rows):
                parts.append(rows[rows["cik"] == cik])
    dei = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    balance = []
    for path in sorted(glob.glob(str(facts_dir / "facts-*.parquet"))):
        frame = pd.read_parquet(path, columns=["cik", "accession", "form", "accepted_at", "canonical_fact", "tag", "unit", "value",
                                               "period_end", "amendment"])
        frame = frame[(frame["canonical_fact"] == "shares_outstanding") & frame["cik"].isin(trusted["cik"])]
        balance.append(frame)
    balance_frame = pd.concat(balance, ignore_index=True)
    balance_frame = balance_frame.assign(basis="BALANCE_SHEET", multi_class_summed=False)
    proxy = []
    for path in sorted(glob.glob(str(facts_dir / "facts-*.parquet"))):
        frame = pd.read_parquet(path, columns=["cik", "accession", "form", "accepted_at", "canonical_fact", "tag", "unit", "value",
                                               "period_end", "amendment", "qtrs"])
        frame = frame[(frame["canonical_fact"] == "weighted_shares_basic") & frame["qtrs"].isin([1, 4]) & frame["cik"].isin(trusted["cik"])]
        proxy.append(frame.drop(columns="qtrs"))
    proxy_frame = pd.concat(proxy, ignore_index=True).assign(basis="WEIGHTED_AVG_PROXY", multi_class_summed=False)
    if len(dei):
        dei = dei.assign(period_end=pd.to_datetime(dei["period_end"]).dt.date, amendment=dei["form"].astype(str).str.endswith("/A"))
    combined = pd.concat([d for d in (dei, balance_frame, proxy_frame) if len(d)], ignore_index=True)
    combined["cik"] = combined["cik"].astype("int64")
    combined = combined.merge(trusted, on="cik", how="inner")
    combined["accepted_at"] = pd.to_datetime(combined["accepted_at"])
    combined["available_session"] = [available_session(v, calendar) for v in combined["accepted_at"]]
    combined = combined.rename(columns={"amendment": "is_amendment"})
    combined = combined.dropna(subset=["value"])
    combined = combined[combined["value"] > 0]
    combined = combined.drop_duplicates(["security_id", "accession", "period_end", "basis", "value"])
    return combined[["security_id", "cik", "period_end", "accepted_at", "available_session", "accession", "form", "tag", "unit",
                     "value", "is_amendment", "basis", "multi_class_summed"]].sort_values(["security_id", "accepted_at"]).reset_index(drop=True)


def measure(root: Path, built: dict[str, Any], folds: list[dict[str, Any]]) -> dict[str, Any]:
    """Coverage on the frozen research frame's in-universe rows (date, symbol), using the same joins the panel uses."""
    frame = pd.read_parquet(Path(root) / "data/research/derived/exp009b_frame.parquet", columns=["date", "symbol", "in_universe"])
    frame = frame[frame["in_universe"]].drop(columns="in_universe").reset_index(drop=True)   # the population the models use
    frame["date"] = pd.to_datetime(frame["date"])
    splits = pd.read_parquet(Path(root) / "data/research/raw/dolthub_stocks_split/part-all.parquet")
    table = C.split_factor_table(splits)
    panel = C.attach_identity(frame, built["identities"])
    panel = C.attach_classification(panel, built["classification"])
    panel = C.attach_shares(panel, built["shares"], table)
    close = built["ohlcv"][["date", "symbol", "close"]]
    panel = panel.merge(close, on=["date", "symbol"], how="left")
    panel["market_cap"] = panel["shares_outstanding"] * panel["close"]
    tables = C.coverage_tables(panel, folds)
    status = C.security_master_status(tables)
    resolution = built["resolution"]
    unresolved = resolution[resolution["grade"] == "UNRESOLVED"]
    exits, ids = built["exits"], built["identities"]
    return {
        "version": M.SECURITY_MASTER_VERSION, "cutoff": str(CUTOFF), "universe_symbols": int(resolution["ticker"].nunique()),
        "evidence": M.evidence_summary(resolution), "unresolved_tickers": int(unresolved["ticker"].nunique()),
        "unresolved_sample": sorted(unresolved["ticker"].unique())[:60],
        "ticker_reuse_candidates": int((resolution.groupby("ticker")["window_from"].nunique() > 1).sum()),
        "identity_intervals": int(len(ids)), "classification_intervals": int(len(built["classification"])),
        "name_intervals": int(len(built["names"])), "shares_vintages": int(len(built["shares"])),
        "shares_by_basis": {k: int(v) for k, v in built["shares"]["basis"].value_counts().items()},
        "exit_events": int(len(exits)), "exit_quality": {k: int(v) for k, v in exits["quality"].value_counts().items()},
        "closed_identities": int(ids["effective_to"].notna().sum()),
        "coverage": tables, **status, "french_sic_sha256": built["french_hashes"],
    }
