"""Manual audit of rich PIT v2: deterministic identifier-only selection, then a source -> curated -> snapshot -> panel trace per filing.

    .venv/bin/python -m scripts.quant.audit_pit_v2

Two audits share one trace: the FROZEN audit (strata of DATA_COMPLETION_GATE_2026 section 7, operationalised in Amendment A1.2) and a
SUPPLEMENTARY hard-case audit (foreign/IFRS/proxy-share/etc. strata).  Writes data/manifests/manual_audit_v2.json.
Reads no return, label statistic or model output.
"""

from __future__ import annotations

import glob
import json
import sys

import numpy as np
import pandas as pd

from scripts.quant.build_pit_data import MANIFESTS, RAW_SEC, ROOT, trading_dates
from src.quant.features import pit_fundamentals as F
from src.quant.pit import audit_v2 as A
from src.quant.pit import security_master_v4 as V4
from src.quant.pit import foreign_facts as X
from src.quant.pit import sec_facts as S
from src.quant.pit.foreign_facts import FOREIGN_ANNUAL_FORMS
from src.quant.pit.rich_panel_build import FACT_COLUMNS
from src.quant.pit.rich_panel_v2_build import FOREIGN_FACT_COLUMNS
from src.quant.pit.sec_foundation import atomic_json

ANNUAL_FORMS = frozenset({"10-K", "10-K/A", "10-KT", "10-KT/A"}) | FOREIGN_ANNUAL_FORMS
PANEL_COLUMNS = ["date", "symbol", "v2_cik", "v2_identity_grade", "v2_filer_regime", "roa_xs", "fc_roa_xs"]
CONCEPT_QTRS = {"assets": 0, "net_income": 4, "revenue": 4}
CUTOFF = pd.Timestamp("2025-05-09 23:59:59")
RESTATEMENT_TOLERANCE = 0.005


def _read(pattern: str, columns: list[str], keep) -> pd.DataFrame:
    parts = []
    for path in sorted(glob.glob(str(ROOT / pattern))):
        frame = pd.read_parquet(path, columns=columns)
        parts.append(frame[keep(frame)])
    return pd.concat(parts, ignore_index=True)


def annual_facts(ciks: set[int]) -> pd.DataFrame:
    """The three audited concepts at annual scale, one row per (accession, concept, period_end): best tag priority; domestic and foreign together."""
    columns = ["cik", "accession", "accepted_at", "canonical_fact", "tag", "tag_priority", "qtrs", "value", "period_end", "report_period", "available_session"]
    keep = lambda f: f["cik"].isin(ciks) & f["canonical_fact"].isin(CONCEPT_QTRS)
    frames = [_read("data/curated/sec_v3/facts-*.parquet", columns, keep), _read("data/curated/sec_v4_foreign/facts-*.parquet", columns, keep)]
    facts = pd.concat(frames, ignore_index=True)
    facts = facts[facts["qtrs"] == facts["canonical_fact"].map(CONCEPT_QTRS)]
    facts = facts.sort_values(["accession", "canonical_fact", "period_end", "tag_priority"], kind="mergesort")
    return facts.drop_duplicates(["accession", "canonical_fact", "period_end"], keep="first").reset_index(drop=True)


def restating_accessions(facts: pd.DataFrame) -> set[str]:
    """Annual filings that carry a prior-period value differing by more than 0.5% from the same period as first reported by the same CIK (A1.2)."""
    facts = facts.assign(accepted_at=pd.to_datetime(facts["accepted_at"]), period_end=pd.to_datetime(facts["period_end"]), report_period=pd.to_datetime(facts["report_period"]))
    current = facts[facts["period_end"] == facts["report_period"]][["cik", "canonical_fact", "period_end", "accepted_at", "value"]].rename(columns={"accepted_at": "first_accepted", "value": "first_value"})
    prior = facts[facts["period_end"] < facts["report_period"] - pd.Timedelta(days=300)]
    joined = prior.merge(current, on=["cik", "canonical_fact", "period_end"], how="inner")
    joined = joined[joined["first_accepted"] < joined["accepted_at"]]
    changed = (joined["value"] - joined["first_value"]).abs() > RESTATEMENT_TOLERANCE * joined["first_value"].abs().clip(lower=1.0)
    return set(joined.loc[changed, "accession"])


def api_share_rows(cik: int, accession: str) -> list[tuple]:
    """Cover-page shares as the SEC companyconcept response stored them (un-dimensioned facts only; a 404 means the filer has none)."""
    path = ROOT / f"data/raw/sec_api/dei_shares/CIK{int(cik):010d}.json"
    if not path.exists():
        return []
    entries = json.loads(path.read_text()).get("units", {}).get("shares", [])
    return [(None, float(e["val"])) for e in entries if e.get("accn") == accession]


def population(registry: pd.DataFrame, panel_ciks: set[int]) -> tuple[pd.DataFrame, dict]:
    tables = ROOT / "data/curated/security_master_v4"
    identities = pd.read_parquet(tables / "security_identity_interval.parquet")
    exits = pd.read_parquet(tables / "security_exit_event.parquet")
    links = pd.read_parquet(tables / "security_succession_link.parquet")
    shares = pd.read_parquet(tables / "shares_fact_vintage.parquet")
    resolution = pd.read_parquet(tables / "universe_resolution.parquet")
    splits = pd.read_parquet(ROOT / "data/research/raw/dolthub_stocks_split/part-all.parquet")

    annual = registry[registry["form"].isin(ANNUAL_FORMS) & registry["cik"].isin(panel_ciks) & (pd.to_datetime(registry["accepted_at"]) <= CUTOFF)].copy()
    annual["accepted_at"] = pd.to_datetime(annual["accepted_at"])
    foreign_meta = _read("data/curated/sec_v4_foreign/facts-*.parquet", ["accession", "currency", "taxonomy_family"], lambda f: f["accession"].isin(set(annual["adsh"]))).drop_duplicates("accession")
    annual = annual.merge(foreign_meta.rename(columns={"accession": "adsh"}), on="adsh", how="left")
    facts = annual_facts(panel_ciks)
    at_period = facts[pd.to_datetime(facts["period_end"]) == pd.to_datetime(facts["report_period"])]
    present = at_period.groupby("accession")["canonical_fact"].agg(lambda s: set(s))
    annual["concepts_present"] = annual["adsh"].map(present).map(lambda s: s if isinstance(s, set) else set())

    regimes = identities.drop_duplicates("cik").set_index("cik")["filer_regime"]
    multi_listed = V4.multi_listed_ciks(identities)
    reused = resolution.groupby("ticker")["cik"].nunique()
    reuse_ciks = set(resolution[resolution["ticker"].isin(reused[reused > 1].index)]["cik"].dropna().astype("int64"))
    succession_ciks = set(links["predecessor_cik"].astype("int64")) | set(links["successor_cik"].astype("int64")) | reuse_ciks
    exiting_any = set(exits["cik"].astype("int64"))
    exiting = set(exits[exits["classification"].isin(["EXACT", "APPROXIMATED"])]["cik"].astype("int64"))
    multi_class_data = set(shares[shares["multi_class_summed"].fillna(False).astype(bool)]["cik"].astype("int64"))
    proxy = set(shares[shares["basis"] == "WEIGHTED_AVG_PROXY"]["cik"].astype("int64"))
    grade = identities.groupby("cik")["status"].agg(lambda s: set(s))
    b_or_c = {c for c, s in grade.items() if any(str(x).startswith(("B", "C")) for x in s)}
    annual["regime"] = annual["cik"].map(regimes)
    annual["multi_listed"] = annual["cik"].isin(multi_listed)

    sessions = pd.DatetimeIndex(pd.to_datetime(list(trading_dates())))
    day = annual["accepted_at"].dt.normalize()
    after_close = ~(day.isin(sessions) & (annual["accepted_at"].dt.time < A.MARKET_CLOSE))

    ticker_to_cik = identities[identities["status"].isin(["A_CONFIRMED", "B_CONSISTENT"])][["ticker", "cik"]].drop_duplicates()
    split_dates = splits.assign(date=pd.to_datetime(splits["date"])).merge(ticker_to_cik, left_on="symbol", right_on="ticker")[["cik", "date"]]
    with_split = annual[["adsh", "cik", "accepted_at"]].merge(split_dates, on="cik")
    with_split = with_split[(with_split["date"] <= with_split["accepted_at"]) & (with_split["date"] >= with_split["accepted_at"] - pd.Timedelta(days=365))]
    restated = restating_accessions(facts)
    foreign_form = annual["form"].isin(FOREIGN_ANNUAL_FORMS)
    missing = annual["concepts_present"].map(lambda s: not set(CONCEPT_QTRS) <= s)

    frozen = {
        "AMENDMENT": annual["form"].str.endswith("/A"),
        "AFTER_CLOSE_ACCEPTANCE": after_close,
        "TICKER_REUSE_OR_SUCCESSION": annual["cik"].isin(succession_ciks),
        "FOREIGN_FILER": foreign_form,
        "MULTIPLE_SHARE_CLASSES": annual["cik"].isin(multi_listed),
        "DELISTED_NAME": annual["cik"].isin(exiting_any),
        "MISSING_FACT": missing,
        "RESTATEMENT": annual["adsh"].isin(restated),
        "SPLIT": annual["adsh"].isin(set(with_split["adsh"])),
        "UNCONSTRAINED": pd.Series(True, index=annual.index),
    }
    supplementary = {
        "AMENDED_ANNUAL_FILING": annual["form"].str.endswith("/A"),
        "SUCCESSION_OR_TICKER_REUSE": annual["cik"].isin(succession_ciks),
        "EXITING_SECURITY": annual["cik"].isin(exiting),
        "MIXED_FILER_REGIME": annual["regime"].eq("MIXED"),
        "NON_USD_REPORTING_CURRENCY": foreign_form & annual["currency"].notna() & annual["currency"].ne("USD"),
        "IFRS_20F": annual["form"].isin(["20-F", "20-F/A"]) & annual["taxonomy_family"].eq("ifrs"),
        "US_GAAP_20F": annual["form"].isin(["20-F", "20-F/A"]) & annual["taxonomy_family"].eq("us-gaap"),
        "FORM_40F": annual["form"].isin(["40-F", "40-F/A"]),
        "MULTI_CLASS_SHARES": annual["cik"].isin(multi_class_data),
        "SHARES_PROXY_TIER": annual["cik"].isin(proxy),
        "IDENTITY_GRADE_B_OR_C": annual["cik"].isin(b_or_c),
        "FORMER_NAME": annual["former"].notna(),
        "DOMESTIC_10K_GRADE_A": annual["form"].eq("10-K") & annual["regime"].eq("DOMESTIC_10K") & annual["cik"].map(grade).map(lambda s: isinstance(s, set) and s == {"A_CONFIRMED"}),
    }

    def pool(rules: dict) -> pd.DataFrame:
        return pd.concat([annual.loc[mask, ["cik", "adsh"]].rename(columns={"adsh": "accession"}).assign(stratum=stratum) for stratum, mask in rules.items()], ignore_index=True)

    return annual, {"frozen": pool(frozen), "supplementary": pool(supplementary), "context": {"shares": shares}}


def trace(selected: pd.DataFrame, annual: pd.DataFrame, context: dict) -> list[dict]:
    panel = pd.read_parquet(ROOT / "data/research/derived/rich_pit_v2_panel.parquet", columns=PANEL_COLUMNS)
    panel["date"] = pd.to_datetime(panel["date"])
    sessions = list(trading_dates())
    ciks = set(selected["cik"])
    dom_all = _read("data/curated/sec_v3/facts-*.parquet", FACT_COLUMNS + ["tag"], lambda f: f["cik"].isin(ciks))
    for_all = _read("data/curated/sec_v4_foreign/facts-*.parquet", FOREIGN_FACT_COLUMNS + ["tag", "currency"], lambda f: f["cik"].isin(ciks) & (f["fp"] == "FY"))
    shares = context["shares"]

    info = annual.set_index("adsh")
    records, wanted_by_archive = [], {}
    for item in selected.itertuples(index=False):
        row = info.loc[item.accession]
        curated = pd.concat([for_all[for_all["accession"] == item.accession], dom_all[dom_all["accession"] == item.accession]], ignore_index=True)
        currency, period_end, cited = None, None, {}
        if len(curated):
            period_end = pd.Timestamp(curated["report_period"].iloc[0]).strftime("%Y%m%d")
            if "currency" in curated and curated["currency"].notna().any():
                currency = curated["currency"].dropna().mode().iloc[0]
            at = curated[pd.to_datetime(curated["period_end"]) == pd.to_datetime(curated["report_period"])]
            for concept, qtrs in A.FLOW_QTRS.items():
                subset = at[(at["canonical_fact"] == concept) & (at["qtrs"] == int(qtrs))]
                cited[concept] = None if subset.empty else subset.sort_values("tag_priority").iloc[0]["tag"]
        elif not pd.isna(row["period"]):
            period_end = str(int(row["period"]))
        mapped_domestic = {c: [tag for _, tag in S.FACTS[c].tags] for c in A.FLOW_QTRS}
        mapped_foreign = {c: [tag for _, tag in (*X.IFRS_FACTS[c], *X.US_GAAP_FACTS[c])] for c in A.FLOW_QTRS}
        mapped = mapped_foreign if row["form"] in FOREIGN_ANNUAL_FORMS else mapped_domestic
        held = shares[shares["accession"] == item.accession]
        share_tag = None if held.empty else held["tag"].iloc[0]
        wanted_by_archive.setdefault(row["source_archive"], {})[item.accession] = {"period_end": period_end, "currency": currency, "tags": cited, "share_tag": share_tag, "mapped": mapped}
        records.append({"stratum": item.stratum, "cik": item.cik, "accession": item.accession, "selection_key": item.selection_key, "name": row["name"],
                        "form": row["form"], "accepted_at": str(row["accepted_at"]), "source_archive": row["source_archive"], "period_end": period_end,
                        "regime": row["regime"], "multi_listed": bool(row["multi_listed"]), "reporting_currency": currency,
                        "taxonomy_family": None if pd.isna(row.get("taxonomy_family")) else row.get("taxonomy_family"),
                        "curated_facts": int(len(curated)), "_curated": curated, "_held": held})

    raw = {}
    for archive, wanted in wanted_by_archive.items():
        raw.update(A.raw_values(RAW_SEC / archive, wanted))
    for rec in records:
        curated, held = rec.pop("_curated"), rec.pop("_held")
        stored = pd.Timestamp(curated["available_session"].iloc[0]).date() if len(curated) else None
        derived = A.available_session_independent(pd.Timestamp(rec["accepted_at"]), sessions)
        rec.update({"available_session_stored": None if stored is None else str(stored), "available_session_recomputed": None if derived is None else str(derived),
                    "availability_ok": None if stored is None else bool(stored == derived)})
        got = raw.get(rec["accession"], {"same_tag": {}, "alternate": {}, "mapped_present": {}, "shares": []})
        at = curated[pd.to_datetime(curated["period_end"]) == pd.to_datetime(curated["report_period"])] if len(curated) else curated
        for concept, qtrs in A.FLOW_QTRS.items():
            subset = at[(at["canonical_fact"] == concept) & (at["qtrs"] == int(qtrs))] if len(at) else at
            best = subset.sort_values("tag_priority").iloc[0] if len(subset) else None
            rec[f"{concept}_curated"] = None if best is None else float(best["value"])
            rec[f"{concept}_curated_tag"] = None if best is None else best["tag"]
            rec[f"{concept}_raw_same_tag"] = got["same_tag"].get(concept)
            rec[f"{concept}_same_tag_vs_curated"] = A.close(rec[f"{concept}_raw_same_tag"], rec[f"{concept}_curated"])
            rec[f"{concept}_definition_note"] = A.definition_note(rec[f"{concept}_curated"], got["alternate"].get(concept))
            present = got["mapped_present"].get(concept, [])
            rec[f"{concept}_mapped_tags_in_source"] = present
            rec[f"{concept}_dropped_fact"] = (rec[f"{concept}_curated"] is None and bool(present)) if len(curated) else None
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
        for concept in A.FLOW_QTRS:
            rec[f"{concept}_curated_vs_snapshot"] = A.close(rec[f"{concept}_curated"], rec[f"{concept}_snapshot"])
        ni, assets = rec["net_income_raw_same_tag"], rec["assets_raw_same_tag"]
        rec["roa_from_raw"] = None if not assets or ni is None else ni / assets
        rec["roa_recomputed_vs_snapshot"] = A.close(rec["roa_from_raw"], rec["roa_snapshot"])
        if len(held):
            value = float(held["value"].iloc[0])
            basis = held["basis"].iloc[0]
            rows = api_share_rows(rec["cik"], rec["accession"]) if basis == "DEI_COVER" else got["shares"]
            rec.update({"shares_stored": value, "shares_tag": held["tag"].iloc[0], "shares_basis": basis, "shares_source": "sec_api_companyconcept" if basis == "DEI_COVER" else "fsds_num_txt",
                        "shares_raw_rows": [[s, v] for s, v in rows[:8]], "shares_stored_vs_raw": A.shares_reconcile(value, rows)})
        else:
            rec.update({"shares_stored": None, "shares_tag": None, "shares_basis": None, "shares_source": None, "shares_raw_rows": [], "shares_stored_vs_raw": None})
        rec["share_count_defined_in_panel"] = bool(rec["shares_stored"] is not None and not rec["multi_listed"] and rec["regime"] != "FOREIGN_20F_40F")
        after = panel[(panel["v2_cik"] == rec["cik"]) & (panel["date"] >= pd.Timestamp(rec["available_session_stored"] or rec["accepted_at"]))].head(1)
        if len(after):
            r = after.iloc[0]
            rec.update({"panel_first_date": str(r["date"].date()), "panel_symbol": r["symbol"], "panel_identity_grade": r["v2_identity_grade"], "panel_regime": r["v2_filer_regime"],
                        "panel_roa_xs": None if pd.isna(r["roa_xs"]) else float(r["roa_xs"]), "panel_fc_roa_xs": None if pd.isna(r["fc_roa_xs"]) else float(r["fc_roa_xs"])})
        else:
            rec.update({"panel_first_date": None, "panel_symbol": None, "panel_identity_grade": None, "panel_regime": None, "panel_roa_xs": None, "panel_fc_roa_xs": None})
        rec["verdict"] = A.verdict(rec)
        rec["definition_notes"] = [f"{c}: {rec[f'{c}_definition_note']}" for c in A.FLOW_QTRS if rec[f"{c}_definition_note"]]
    return records


def summarise(name: str, strata, pool: pd.DataFrame, records: list[dict]) -> dict:
    return {"name": name, "strata": list(strata), "candidates_per_stratum": {k: int(v) for k, v in pool.groupby("stratum").size().items()},
            "issuer_periods_audited": len(records), "verdicts": {k: int(v) for k, v in pd.Series([r["verdict"] for r in records]).value_counts().items()},
            "with_definition_note": int(sum(bool(r["definition_notes"]) for r in records)),
            "share_counts_traced": int(sum(r["shares_stored_vs_raw"] is not None for r in records)),
            "share_counts_reconciled": int(sum(r["shares_stored_vs_raw"] is True for r in records)), "records": records}


def main() -> int:
    registry = V4.augmented_registry(ROOT)
    panel_ciks = set(pd.read_parquet(ROOT / "data/research/derived/rich_pit_v2_panel.parquet", columns=["v2_cik"])["v2_cik"].dropna().astype("int64"))
    annual, pools = population(registry, panel_ciks)
    audits = {}
    for key, strata in (("frozen", A.FROZEN_STRATA), ("supplementary", A.SUPPLEMENTARY_STRATA)):
        selected = A.select(pools[key], strata=strata)
        audits[key] = summarise(key, strata, pools[key], trace(selected, annual, pools["context"]))
    payload = {"version": A.AUDIT_VERSION, "per_stratum": A.PER_STRATUM, "selection_uses": "identifiers and filing metadata only", "dataset_manifest": "rich_pit_v2_manifest.json",
               "audits": audits}
    atomic_json(MANIFESTS / "manual_audit_v2.json", payload)
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "records"} for k, v in audits.items()}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
