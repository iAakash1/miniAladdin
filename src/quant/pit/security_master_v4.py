"""Security master v4: identity evidence extended to foreign annual reports, exit events in the full schema, share-tier audit.

Built beside `security_master_v3` (never over it).  The grade definitions are unchanged (`security_master.grade_link`); what changes is the
evidence: the filings registry now also contains 20-F/40-F annual reports (gate definition D1), so a foreign issuer's ticker->CIK link can be
tested the way a domestic one is.  Foreign filers get no share count or market capitalisation (definition D2).
"""

from __future__ import annotations

import glob
import json
import os
from datetime import date as Date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

import numpy as np
import pandas as pd

from src.quant.pit import pit_coverage as C
from src.quant.pit import pit_coverage_v4 as C4
from src.quant.pit import security_master as M
from src.quant.pit.calendar import TradingCalendar
from src.quant.pit.security_master_build import CUTOFF, _write, build_shares, load_ohlcv, research_universe_symbols
from src.quant.pit.foreign_facts import FOREIGN_ANNUAL_FORMS

DOMESTIC_FORMS = frozenset({"10-K", "10-K/A", "10-KT", "10-KT/A", "10-Q", "10-Q/A", "10-QT", "10-QT/A"})
SECURITY_MASTER_V4 = "security-master-v4"

EVENT_TYPES = {
    "EXCHANGE_DELISTING_FORM_25": "DELISTING_FORM_25", "DEREGISTRATION_FORM_15": "DEREGISTRATION_FORM_15",
    "FOREIGN_DEREGISTRATION": "DEREGISTRATION_FORM_15F", "8K_DELISTING_NOTICE": "DELISTING_NOTICE_8K",
    "8K_ACQUISITION_COMPLETED": "MERGER_OR_ACQUISITION_8K", "8K_BANKRUPTCY": "BANKRUPTCY_8K",
}
CONFIDENCE = {"DELISTING_FORM_25": "HIGH", "DEREGISTRATION_FORM_15": "MEDIUM", "DEREGISTRATION_FORM_15F": "MEDIUM",
              "DELISTING_NOTICE_8K": "MEDIUM", "MERGER_OR_ACQUISITION_8K": "MEDIUM", "BANKRUPTCY_8K": "MEDIUM",
              "LAST_PRICE_DATE_ONLY": "LOW", "PRICE_GAP_WINDOW_END": "LOW"}
EXIT_COLUMNS = ["security_id", "cik", "ticker", "event_type", "effective_date", "evidence_date", "source", "confidence",
                "classification", "source_accession", "return_treatment"]


def augmented_registry(root: Path) -> pd.DataFrame:
    """v3 domestic filings plus foreign annual reports.  6-K rows are excluded: they are not periodic evidence."""
    root = Path(root)
    domestic = pd.read_parquet(root / "data/curated/sec_v3/filings.parquet")
    foreign = pd.read_parquet(root / "data/curated/sec_v4_foreign/filings_foreign.parquet")
    foreign = foreign[foreign["form"].isin(FOREIGN_ANNUAL_FORMS)]
    out = pd.concat([domestic, foreign], ignore_index=True).sort_values(["accepted_at", "adsh"], kind="stable")
    out["cik"] = out["cik"].astype("int64")
    return out.reset_index(drop=True)


def filer_regimes(registry: pd.DataFrame) -> pd.Series:
    """cik -> DOMESTIC_10K | FOREIGN_20F_40F | MIXED, from the forms the CIK actually filed."""
    forms = registry.groupby("cik")["form"].agg(lambda s: set(s))
    def regime(fs: set) -> str:
        d, f = bool(fs & DOMESTIC_FORMS), bool(fs & FOREIGN_ANNUAL_FORMS)
        return "MIXED" if d and f else ("FOREIGN_20F_40F" if f else "DOMESTIC_10K")
    return forms.map(regime)


def exit_events_v4(identities: pd.DataFrame, evidence_by_cik: Mapping[int, list[dict[str, Any]]], windows: Mapping[str, Any],
                   succession_ciks: set[int]) -> pd.DataFrame:
    """One record per identity whose window closes before the research cutoff, in the full schema.

    EXACT only with a Form 25 within 45 days of the last trade.  Other dated evidence within 45 days is APPROXIMATED; a window that ends only
    because prices have a long gap, with no exit filing near it, is UNKNOWN (an exit, a ticker reuse and a data gap look identical).
    No delisting return is invented.
    """
    rows = []
    closed = identities[identities["effective_to"].notna()]
    for row in closed.itertuples(index=False):
        last_trade = pd.Timestamp(row.effective_to)
        window = windows.get(row.ticker)
        gap_end = bool(window is not None and len(window.segments) > 1 and last_trade.date() < window.last)
        near = [e for e in evidence_by_cik.get(int(row.cik), []) if abs((pd.Timestamp(e["event_date"]) - last_trade).days) <= 45]
        form25 = [e for e in near if e["kind"] == "EXCHANGE_DELISTING_FORM_25"]
        best = (form25 or near or [None])[0]
        if best is not None:
            event_type = EVENT_TYPES[best["kind"]]
            classification = "EXACT" if form25 else "APPROXIMATED"
            evidence_date, source, accession = pd.Timestamp(best["event_date"]), f"SEC_SUBMISSIONS:{best['form']}", best["accession"]
        elif gap_end:
            event_type, classification, evidence_date, source, accession = "PRICE_GAP_WINDOW_END", "UNKNOWN", last_trade, "PRICE_WINDOW_GAP", pd.NA
        elif int(row.cik) in succession_ciks:
            event_type, classification, evidence_date, source, accession = "LAST_PRICE_DATE_ONLY", "APPROXIMATED", last_trade, "SUCCESSOR_LINK+PRICE_WINDOW", pd.NA
        else:
            event_type, classification, evidence_date, source, accession = "LAST_PRICE_DATE_ONLY", "APPROXIMATED", last_trade, "PRICE_WINDOW", pd.NA
        rows.append({"security_id": row.security_id, "cik": row.cik, "ticker": row.ticker, "event_type": event_type,
                     "effective_date": last_trade, "evidence_date": evidence_date, "source": source, "confidence": CONFIDENCE[event_type],
                     "classification": classification, "source_accession": accession,
                     "return_treatment": "UNKNOWN_NO_DELISTING_RETURN_INVENTED"})
    return pd.DataFrame(rows, columns=EXIT_COLUMNS)


def succession_links(resolution: pd.DataFrame, identities: pd.DataFrame) -> pd.DataFrame:
    """Explicit predecessor -> successor links (same ticker, exact issuer-name continuity)."""
    link = resolution[resolution["method"] == "SUCCESSOR_NAME_CONTINUITY"]
    rows = []
    for row in link.itertuples(index=False):
        later = identities[(identities["ticker"] == row.ticker) & (identities["cik"] != row.cik)].sort_values("effective_from")
        for successor in later.itertuples(index=False):
            if pd.Timestamp(successor.effective_from) >= pd.Timestamp(row.window_to):
                predecessor = identities[(identities["ticker"] == row.ticker) & (identities["cik"] == row.cik)].iloc[0]
                rows.append({"ticker": row.ticker, "predecessor_security_id": predecessor["security_id"], "predecessor_cik": int(row.cik),
                             "successor_security_id": successor.security_id, "successor_cik": int(successor.cik),
                             "predecessor_window_to": row.window_to, "successor_window_from": successor.effective_from,
                             "method": row.method, "reason": row.reason})
                break
    return pd.DataFrame(rows)


def ticker_reuse_review(resolution: pd.DataFrame) -> dict[str, Any]:
    """Every ticker that has more than one price window or a link that is not a plain single-issuer link, with its graded windows."""
    out = {}
    counts = resolution.groupby("ticker")["window_from"].nunique()
    flagged = set(counts[counts > 1].index) | set(resolution.loc[resolution["method"] == "SUCCESSOR_NAME_CONTINUITY", "ticker"]) | \
        set(resolution.loc[resolution["grade"] == "X_CONTRADICTED", "ticker"])
    for ticker in sorted(flagged):
        group = resolution[resolution["ticker"] == ticker].sort_values("window_from")
        out[ticker] = [{"cik": None if pd.isna(r.cik) else int(r.cik), "grade": r.grade, "method": r.method, "window": [str(r.window_from), str(r.window_to)], "reason": r.reason}
                       for r in group.itertuples(index=False)]
    return out


def build(root: Path, *, network: bool = True) -> dict[str, Any]:
    root = Path(root)
    out_dir = root / "data/curated/security_master_v4"
    raw_api = root / "data/raw/sec_api"
    registry = augmented_registry(root)
    regimes = filer_regimes(registry)
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
        for cik in sorted(wanted):
            document = M.submissions(cik, raw_api)
            fetched.add(cik)
            if document and "_status" not in document:
                histories[cik] = M.name_history(document)
                evidence[cik] = M.exit_evidence(document)
        resolution = M.resolve_universe(symbols, current, vendor, registry, windows, histories=histories, evidence_end=CUTOFF)
    # cached submissions for CIKs that did not need a fetch this time
    for cik in set(resolution["cik"].dropna().astype(int)) - set(histories):
        document = M.submissions(cik, raw_api) if network or (raw_api / "submissions" / f"CIK{cik:010d}.json").exists() else None
        if document and "_status" not in document:
            histories[cik] = M.name_history(document)
            evidence[cik] = M.exit_evidence(document)

    identities = M.identity_intervals(resolution, retrieved_at=snapshot_at, last_data_date=CUTOFF)
    M.check_no_overlap(identities)
    identities = identities.assign(cik=identities["cik"].astype("int64"))
    identities["filer_regime"] = identities["cik"].map(regimes)

    maps, hashes = M.load_french_maps(root / "data/raw/french_sic")
    classification = M.classification_intervals(registry, identities, maps, version=f"{SECURITY_MASTER_V4}+french-sic-{'-'.join(h[:8] for h in hashes.values())}")
    names = pd.DataFrame([{"cik": cik, **row} for cik, rows in histories.items() for row in rows])
    names = names.merge(identities[["security_id", "cik"]].drop_duplicates(), on="cik", how="inner") if len(names) else names

    links = succession_links(resolution, identities)
    successors = set(links["predecessor_cik"]) if len(links) else set()
    exits = exit_events_v4(identities[identities["status"].isin(["A_CONFIRMED", "B_CONSISTENT", "C_PARTIAL"])], evidence, windows, successors)

    calendar = TradingCalendar.from_dates(sorted(set(ohlcv["date"].dt.date)) + [d.date() for d in pd.bdate_range("2025-05-10", "2025-06-30")])
    domestic_identities = identities[identities["filer_regime"] != "FOREIGN_20F_40F"]
    shares = build_shares(root, domestic_identities, pd.read_parquet(root / "data/curated/sec_v3/filings.parquet"),
                          root / "data/curated/sec_v3", raw_api, calendar, network=network)

    for name, frame in (("security_identity_interval", identities), ("security_classification_interval", classification),
                        ("security_name_interval", names), ("security_exit_event", exits), ("shares_fact_vintage", shares),
                        ("security_succession_link", links), ("universe_resolution", resolution)):
        _write(frame, out_dir / f"{name}.parquet")
    return {"resolution": resolution, "identities": identities, "classification": classification, "names": names, "exits": exits,
            "shares": shares, "links": links, "ohlcv": ohlcv, "french_hashes": hashes, "regimes": regimes, "windows": windows,
            "registry": registry, "submissions_fetched": len(fetched)}


def multi_listed_ciks(identities: pd.DataFrame) -> set[int]:
    """CIKs with two or more trusted securities (Amendment A1, D5).  Identity table only; no name parsing."""
    trusted = identities[identities["status"].isin(C.TRUSTED_GRADES)]
    per_cik = trusted.groupby("cik")["security_id"].nunique()
    return {int(c) for c in per_cik[per_cik > 1].index}


def tier_table(panel: pd.DataFrame, key: str) -> dict[str, Any]:
    """Share tiers never merged: cover-page (exact), balance-sheet (fallback), weighted-average proxy, and missing, among domestic identified name-dates."""
    out = {}
    for label, group in panel.groupby(key):
        n = len(group)
        basis = group["shares_basis"]
        out[str(label)] = {"name_dates": int(n),
                           "exact_cover_page": float((basis == "DEI_COVER").sum() / n), "fallback_balance_sheet": float((basis == "BALANCE_SHEET").sum() / n),
                           "proxy_weighted_average": float((basis == "WEIGHTED_AVG_PROXY").sum() / n), "missing": float(basis.isna().sum() / n),
                           "multi_class_summed": float(group["multi_class_summed"].fillna(False).astype(bool).sum() / n)}
    return out


def load_built(root: Path) -> dict[str, Any]:
    """Re-read the written v4 tables (so coverage can be re-measured without rebuilding)."""
    root = Path(root)
    tables = root / "data/curated/security_master_v4"
    identities = pd.read_parquet(tables / "security_identity_interval.parquet")
    registry = augmented_registry(root)
    ohlcv = load_ohlcv(root)
    symbols = set(research_universe_symbols(root / "data/research/universe/liquid.json"))
    _, hashes = M.load_french_maps(root / "data/raw/french_sic")
    return {"resolution": pd.read_parquet(tables / "universe_resolution.parquet"), "identities": identities,
            "classification": pd.read_parquet(tables / "security_classification_interval.parquet"),
            "names": pd.read_parquet(tables / "security_name_interval.parquet"), "exits": pd.read_parquet(tables / "security_exit_event.parquet"),
            "shares": pd.read_parquet(tables / "shares_fact_vintage.parquet"), "links": pd.read_parquet(tables / "security_succession_link.parquet"),
            "ohlcv": ohlcv[ohlcv["symbol"].isin(symbols)], "french_hashes": hashes, "regimes": filer_regimes(registry), "registry": registry}


def measure(root: Path, built: Mapping[str, Any], folds: list[dict[str, Any]]) -> dict[str, Any]:
    """Coverage on the frozen in-universe rows; the frozen `security_master_status` applied unchanged (with the D3 size population)."""
    root = Path(root)
    frame = pd.read_parquet(root / "data/research/derived/exp009b_frame.parquet", columns=["date", "symbol", "in_universe"])
    frame = frame[frame["in_universe"]].drop(columns="in_universe").reset_index(drop=True)
    frame["date"] = pd.to_datetime(frame["date"])
    splits = pd.read_parquet(root / "data/research/raw/dolthub_stocks_split/part-all.parquet")
    panel = C.attach_identity(frame, built["identities"])
    panel = C4.attach_classification_pit(panel, built["classification"], built["registry"])     # corrected staleness rule (no future filing)
    panel = C.attach_shares(panel, built["shares"], C.split_factor_table(splits))
    panel = panel.merge(built["ohlcv"][["date", "symbol", "close"]], on=["date", "symbol"], how="left")
    regime = panel["cik"].map(built["regimes"])
    multi_listed = multi_listed_ciks(built["identities"])
    panel = C4.apply_foreign_policy(panel, built["regimes"], multi_listed)
    tables = C.coverage_tables(panel, folds)
    domestic = panel[~panel["foreign"]].copy()
    tables_domestic = C.coverage_tables(domestic.assign(security_id=domestic["security_id"]), folds)
    gated = {"by_year": tables["by_year"],
             "by_period": {k: {**v, "market_cap_of_identified_all": v["market_cap_of_identified"],
                               "market_cap_of_identified": tables_domestic["by_period"][k]["market_cap_of_identified"]} for k, v in tables["by_period"].items()}}
    status = C.security_master_status(gated)
    panel["period"] = C.label_periods(panel["date"], folds)
    panel["year"] = panel["date"].dt.year
    identified = panel[panel["security_id"].notna() & ~panel["foreign"]]
    per_security = identified.groupby("security_id")["shares_basis"].agg(lambda s: (s == "DEI_COVER").mean())
    resolution, exits = built["resolution"], built["exits"]
    foreign_identified = panel[panel["security_id"].notna() & panel["foreign"]]
    return {
        "version": SECURITY_MASTER_V4, "cutoff": str(CUTOFF), "universe_symbols": int(resolution["ticker"].nunique()),
        "evidence": M.evidence_summary(resolution), "unresolved_tickers": int(resolution.loc[resolution["grade"] == "UNRESOLVED", "ticker"].nunique()),
        "unresolved_list": sorted(resolution.loc[resolution["grade"] == "UNRESOLVED", "ticker"].unique()),
        "identity_intervals": int(len(built["identities"])), "classification_intervals": int(len(built["classification"])),
        "name_intervals": int(len(built["names"])), "succession_links": int(len(built["links"])), "shares_vintages": int(len(built["shares"])),
        "shares_by_basis": {k: int(v) for k, v in built["shares"]["basis"].value_counts().items()},
        "exit_events": int(len(exits)), "exit_classification": {k: int(v) for k, v in exits["classification"].value_counts().items()},
        "exit_event_types": {k: int(v) for k, v in exits["event_type"].value_counts().items()},
        "filer_regime_of_identities": {k: int(v) for k, v in built["identities"]["filer_regime"].value_counts().items()},
        "multi_listed_ciks": len(multi_listed), "multi_listed_securities": int(built["identities"][built["identities"]["cik"].isin(multi_listed) & built["identities"]["status"].isin(C.TRUSTED_GRADES)]["security_id"].nunique()),
        "foreign_identified_name_dates": int(len(foreign_identified)), "foreign_identified_securities": int(foreign_identified["security_id"].nunique()),
        "coverage": gated, "coverage_all_rows": tables, "share_tiers_by_year": tier_table(identified, "year"), "share_tiers_by_period": tier_table(identified, "period"),
        "share_tier_security_distribution": {"securities": int(per_security.size), "with_at_least_90pct_exact": int((per_security >= 0.9).sum()),
                                             "with_zero_exact": int((per_security == 0).sum())},
        "ticker_reuse_review": ticker_reuse_review(resolution), **status, "french_sic_sha256": built["french_hashes"],
        "size_gate_population": "identified domestic name-dates (definition D3); the all-identified figure is kept beside it",
    }
