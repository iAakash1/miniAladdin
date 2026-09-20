"""Manual audit of rich PIT v2: deterministic identifier-only selection, then a source -> curated -> snapshot -> panel trace per filing.

    .venv/bin/python -m scripts.quant.audit_pit_v2

Writes data/manifests/manual_audit_v2.json.  Reads no return, label statistic or model output.
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.quant.build_pit_data import MANIFESTS, RAW_SEC, ROOT, trading_dates
from src.quant.features import pit_fundamentals as F
from src.quant.pit import audit_v2 as A
from src.quant.pit import security_master_v4 as V4
from src.quant.pit.foreign_facts import FOREIGN_ANNUAL_FORMS
from src.quant.pit.rich_panel_build import FACT_COLUMNS
from src.quant.pit.rich_panel_v2_build import FOREIGN_FACT_COLUMNS
from src.quant.pit.sec_foundation import atomic_json

ANNUAL_FORMS = frozenset({"10-K", "10-K/A", "10-KT", "10-KT/A"}) | FOREIGN_ANNUAL_FORMS
PANEL_COLUMNS = ["date", "symbol", "v2_cik", "v2_identity_grade", "v2_filer_regime", "roa_xs", "fc_roa_xs"]


def _facts(pattern: str, columns: list[str], filing_ids: set[str]) -> pd.DataFrame:
    parts = []
    for path in sorted(glob.glob(str(ROOT / pattern))):
        frame = pd.read_parquet(path, columns=columns)
        parts.append(frame[frame["accession"].isin(filing_ids)])
    return pd.concat(parts, ignore_index=True)


def candidates(registry: pd.DataFrame, panel_ciks: set[int]) -> pd.DataFrame:
    tables = ROOT / "data/curated/security_master_v4"
    identities = pd.read_parquet(tables / "security_identity_interval.parquet")
    exits = pd.read_parquet(tables / "security_exit_event.parquet")
    links = pd.read_parquet(tables / "security_succession_link.parquet")
    shares = pd.read_parquet(tables / "shares_fact_vintage.parquet")
    resolution = pd.read_parquet(tables / "universe_resolution.parquet")

    annual = registry[registry["form"].isin(ANNUAL_FORMS) & registry["cik"].isin(panel_ciks)
                      & (pd.to_datetime(registry["accepted_at"]) <= pd.Timestamp("2025-05-09 23:59:59"))].copy()
    # only filings that produced curated facts can be traced end to end
    foreign_meta = _facts("data/curated/sec_v4_foreign/facts-*.parquet", ["accession", "currency", "taxonomy_family"], set(annual["adsh"])).drop_duplicates("accession")
    domestic_ids = set(_facts("data/curated/sec_v3/facts-*.parquet", ["accession"], set(annual["adsh"]))["accession"])
    annual = annual[annual["adsh"].isin(domestic_ids | set(foreign_meta["accession"]))].merge(
        foreign_meta.rename(columns={"accession": "adsh"}), on="adsh", how="left")

    regimes = identities.drop_duplicates("cik").set_index("cik")["filer_regime"]
    reused = resolution.groupby("ticker")["cik"].nunique()
    reuse_ciks = set(resolution[resolution["ticker"].isin(reused[reused > 1].index)]["cik"].dropna().astype("int64"))
    succession_ciks = set(links["predecessor_cik"].astype("int64")) | set(links["successor_cik"].astype("int64")) | reuse_ciks
    exiting = set(exits[exits["classification"].isin(["EXACT", "APPROXIMATED"])]["cik"].astype("int64"))
    multi = set(shares[shares["multi_class_summed"].fillna(False).astype(bool)]["cik"].astype("int64"))
    proxy = set(shares[shares["basis"] == "WEIGHTED_AVG_PROXY"]["cik"].astype("int64"))
    grade = identities.groupby("cik")["status"].agg(lambda s: set(s))
    b_or_c = {c for c, s in grade.items() if s & {"B_LIKELY", "C_PARTIAL"} or any(str(x).startswith(("B", "C")) for x in s)}
    annual["regime"] = annual["cik"].map(regimes)
    is_foreign_form = annual["form"].isin(FOREIGN_ANNUAL_FORMS)
    rules = {
        "AMENDED_ANNUAL_FILING": annual["form"].str.endswith("/A"),
        "SUCCESSION_OR_TICKER_REUSE": annual["cik"].isin(succession_ciks),
        "EXITING_SECURITY": annual["cik"].isin(exiting),
        "MIXED_FILER_REGIME": annual["regime"].eq("MIXED"),
        "NON_USD_REPORTING_CURRENCY": is_foreign_form & annual["currency"].notna() & annual["currency"].ne("USD"),
        "IFRS_20F": annual["form"].isin(["20-F", "20-F/A"]) & annual["taxonomy_family"].eq("ifrs"),
        "US_GAAP_20F": annual["form"].isin(["20-F", "20-F/A"]) & annual["taxonomy_family"].eq("us-gaap"),
        "FORM_40F": annual["form"].isin(["40-F", "40-F/A"]),
        "MULTI_CLASS_SHARES": annual["cik"].isin(multi),
        "SHARES_PROXY_TIER": annual["cik"].isin(proxy),
        "IDENTITY_GRADE_B_OR_C": annual["cik"].isin(b_or_c),
        "FORMER_NAME": annual["former"].notna(),
        "DOMESTIC_10K_GRADE_A": annual["form"].eq("10-K") & annual["regime"].eq("DOMESTIC_10K") & annual["cik"].map(grade).map(lambda s: isinstance(s, set) and s == {"A_CONFIRMED"}),
    }
    rows = [annual.loc[mask, ["cik", "adsh"]].rename(columns={"adsh": "accession"}).assign(stratum=stratum) for stratum, mask in rules.items()]
    return pd.concat(rows, ignore_index=True), annual


def trace(selected: pd.DataFrame, annual: pd.DataFrame) -> list[dict]:
    panel = pd.read_parquet(ROOT / "data/research/derived/rich_pit_v2_panel.parquet", columns=PANEL_COLUMNS)
    panel["date"] = pd.to_datetime(panel["date"])
    sessions = list(trading_dates())
    ciks = set(selected["cik"])
    dom_all = pd.concat([f[f["cik"].isin(ciks)] for f in (pd.read_parquet(p, columns=FACT_COLUMNS + ["tag"]) for p in sorted(glob.glob(str(ROOT / "data/curated/sec_v3/facts-*.parquet"))))], ignore_index=True)
    for_all = pd.concat([f[f["cik"].isin(ciks) & (f["fp"] == "FY")] for f in (pd.read_parquet(p, columns=FOREIGN_FACT_COLUMNS + ["tag", "currency"]) for p in sorted(glob.glob(str(ROOT / "data/curated/sec_v4_foreign/facts-*.parquet"))))], ignore_index=True)

    info = annual.set_index("adsh")
    records, wanted_by_archive = [], {}
    for item in selected.itertuples(index=False):
        row = info.loc[item.accession]
        curated = pd.concat([for_all[for_all["accession"] == item.accession], dom_all[dom_all["accession"] == item.accession]], ignore_index=True)
        currency = None
        period_end = None
        if len(curated):
            period_end = pd.Timestamp(curated["report_period"].iloc[0]).strftime("%Y%m%d")
            if "currency" in curated and curated["currency"].notna().any():
                currency = curated["currency"].dropna().mode().iloc[0]
        else:
            period_end = None if pd.isna(row["period"]) else str(int(row["period"]))
        wanted_by_archive.setdefault(row["source_archive"], {})[item.accession] = (period_end, currency)
        records.append({"stratum": item.stratum, "cik": item.cik, "accession": item.accession, "selection_key": item.selection_key, "name": row["name"],
                        "form": row["form"], "accepted_at": str(row["accepted_at"]), "source_archive": row["source_archive"], "period_end": period_end,
                        "regime": row["regime"], "reporting_currency": currency, "taxonomy_family": None if pd.isna(row.get("taxonomy_family")) else row.get("taxonomy_family"),
                        "curated_facts": int(len(curated)), "_curated": curated})

    raw = {}
    for archive, wanted in wanted_by_archive.items():
        raw.update(A.raw_values(RAW_SEC / archive, {a: v for a, v in wanted.items() if v[0]}))
    for rec in records:
        curated = rec.pop("_curated")
        stored = pd.Timestamp(curated["available_session"].iloc[0]).date() if len(curated) else None
        derived = A.available_session_independent(pd.Timestamp(rec["accepted_at"]), sessions)
        rec.update({"available_session_stored": None if stored is None else str(stored), "available_session_recomputed": None if derived is None else str(derived),
                    "availability_ok": None if stored is None else bool(stored == derived)})
        annual_curated = curated[(curated["qtrs"].isin([0, 4])) & (pd.to_datetime(curated["period_end"]) == pd.to_datetime(curated["report_period"]))] if len(curated) else curated
        family_tags = {}
        for concept in A.RAW_TAGS:
            subset = annual_curated[annual_curated["canonical_fact"] == concept]
            if "qtrs" in subset and len(subset):
                subset = subset[subset["qtrs"] == int(A.FLOW_QTRS[concept])]
            best = subset.sort_values("tag_priority").iloc[0] if len(subset) else None
            rec[f"{concept}_raw"] = raw.get(rec["accession"], {}).get(concept)
            rec[f"{concept}_curated"] = None if best is None else float(best["value"])
            rec[f"{concept}_curated_tag"] = None if best is None else best["tag"]
            rec[f"{concept}_raw_vs_curated"] = A.close(rec[f"{concept}_raw"], rec[f"{concept}_curated"])
        source = for_all if rec["form"] in FOREIGN_ANNUAL_FORMS else dom_all
        snapshots = F.build_snapshots(source[source["cik"] == rec["cik"]])
        snap = snapshots[snapshots["accession"] == rec["accession"]]
        if len(snap):
            s = snap.iloc[[0]]
            rec.update({"assets_snapshot": float(s["assets"].iloc[0]), "net_income_snapshot": float(s["net_income_ttm"].iloc[0]), "revenue_snapshot": float(s["revenue_ttm"].iloc[0])})
            chars = F.snapshot_characteristics(s)
            rec["roa_snapshot"] = None if pd.isna(chars["roa"].iloc[0]) else float(chars["roa"].iloc[0])
        else:
            rec.update({"assets_snapshot": None, "net_income_snapshot": None, "revenue_snapshot": None, "roa_snapshot": None})
        for concept, snapshot_key in (("assets", "assets_snapshot"), ("net_income", "net_income_snapshot"), ("revenue", "revenue_snapshot")):
            rec[f"{concept}_curated_vs_snapshot"] = A.close(rec[f"{concept}_curated"], rec[snapshot_key])
        raw_roa = None if not rec["assets_raw"] or rec["net_income_raw"] is None else rec["net_income_raw"] / rec["assets_raw"]
        rec["roa_from_raw"] = raw_roa
        rec["roa_recomputed_vs_snapshot"] = A.close(raw_roa, rec["roa_snapshot"])
        after = panel[(panel["v2_cik"] == rec["cik"]) & (panel["date"] >= pd.Timestamp(rec["available_session_stored"] or rec["accepted_at"]))].head(1)
        if len(after):
            r = after.iloc[0]
            rec.update({"panel_first_date": str(r["date"].date()), "panel_symbol": r["symbol"], "panel_identity_grade": r["v2_identity_grade"],
                        "panel_regime": r["v2_filer_regime"], "panel_roa_xs": None if pd.isna(r["roa_xs"]) else float(r["roa_xs"]),
                        "panel_fc_roa_xs": None if pd.isna(r["fc_roa_xs"]) else float(r["fc_roa_xs"])})
        else:
            rec.update({"panel_first_date": None, "panel_symbol": None, "panel_identity_grade": None, "panel_regime": None, "panel_roa_xs": None, "panel_fc_roa_xs": None})
        rec["verdict"] = A.verdict(rec)
    return records


def main() -> int:
    registry = V4.augmented_registry(ROOT)
    panel_ciks = set(pd.read_parquet(ROOT / "data/research/derived/rich_pit_v2_panel.parquet", columns=["v2_cik"])["v2_cik"].dropna().astype("int64"))
    pool, annual = candidates(registry, panel_ciks)
    selected = A.select(pool)
    records = trace(selected, annual)
    summary = {"version": A.AUDIT_VERSION, "per_stratum": A.PER_STRATUM, "strata": list(A.STRATA), "candidates_per_stratum": pool.groupby("stratum").size().to_dict(),
               "issuer_periods_audited": len(records), "verdicts": pd.Series([r["verdict"] for r in records]).value_counts().to_dict(),
               "selection_uses": "identifiers only", "records": records}
    atomic_json(MANIFESTS / "manual_audit_v2.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "records"}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
