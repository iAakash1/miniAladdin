"""Build the local data inventory: `data/manifests/data_inventory.json` and the final inventory doc.

Numbers (rows, symbols, date range, bytes, columns, hashes) are measured from the files; the
PIT / licence / usability judgements come from the explicit registry below, so a new dataset
without a judgement is reported as UNASSESSED rather than silently trusted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
OUT_JSON = ROOT / "data/manifests/data_inventory.json"
OUT_DOC = ROOT / "docs/LOCAL_DATA_INVENTORY_FINAL.md"
RAW = ROOT / "data/research/raw"

# Judgements. Redistribution is never assumed where a licence is not explicit.
JUDGEMENT: dict[str, dict[str, Any]] = {
    "dolthub_stocks_ohlcv": ("DoltHub post-no-preference/stocks", "point_in_time (unadjusted close-date bars)", "open data on DoltHub; terms not reviewed", "NOT_ASSUMED", True, "RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED", "no adjusted close; delisting bars partial before 2017-10-26; symbol is not a stable identity"),
    "dolthub_stocks_ohlcv_monthly": ("DoltHub post-no-preference/stocks", "derived aggregate", "as above", "NOT_ASSUMED", False, "RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED", "monthly aggregate; not used by the frozen dataset"),
    "dolthub_stocks_split": ("DoltHub post-no-preference/stocks", "point_in_time (ex-date)", "as above", "NOT_ASSUMED", True, "RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED", "pre-2014 adjustments need caution"),
    "dolthub_stocks_dividend": ("DoltHub post-no-preference/stocks", "point_in_time (ex-date)", "as above", "NOT_ASSUMED", True, "RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED", ""),
    "dolthub_stocks_symbol": ("DoltHub post-no-preference/stocks", "NOT point-in-time (current snapshot)", "as above", "NOT_ASSUMED", True, "RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED", "descriptive fields are today's; last_seen is only a delisting bound"),
    "dolthub_earnings_eps_estimate": ("DoltHub post-no-preference/earnings", "point_in_time (weekly consensus vintage)", "as above", "NOT_ASSUMED", True, "RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED", "consensus snapshots, no analyst id; 2017-10-26 onward"),
    "dolthub_earnings_sales_estimate": ("DoltHub post-no-preference/earnings", "point_in_time (weekly consensus vintage)", "as above", "NOT_ASSUMED", True, "RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED", "as EPS estimates"),
    "dolthub_earnings_eps_history": ("DoltHub post-no-preference/earnings", "NOT point-in-time (period-dated, no announcement)", "as above", "NOT_ASSUMED", False, "RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED", "usable only behind the earnings calendar gate"),
    "dolthub_earnings_calendar": ("DoltHub post-no-preference/earnings", "partial (event date; 2020-01-22 onward)", "as above", "NOT_ASSUMED", True, "RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED", "cannot time pre-2020 announcements"),
    "dolthub_earnings_income_statement": ("DoltHub post-no-preference/earnings", "NOT point-in-time (as-of-today values, period end only)", "as above", "NOT_ASSUMED", False, "EXCLUDED_FROM_HISTORICAL_MODELS", "restatements overwritten; superseded by the SEC as-reported store"),
    "dolthub_earnings_balance_sheet_assets": ("DoltHub post-no-preference/earnings", "NOT point-in-time", "as above", "NOT_ASSUMED", False, "EXCLUDED_FROM_HISTORICAL_MODELS", "as income statement"),
    "dolthub_earnings_balance_sheet_liabilities": ("DoltHub post-no-preference/earnings", "NOT point-in-time", "as above", "NOT_ASSUMED", False, "EXCLUDED_FROM_HISTORICAL_MODELS", "as income statement"),
    "dolthub_earnings_balance_sheet_equity": ("DoltHub post-no-preference/earnings", "NOT point-in-time", "as above", "NOT_ASSUMED", False, "EXCLUDED_FROM_HISTORICAL_MODELS", "as income statement"),
    "dolthub_earnings_cash_flow_statement": ("DoltHub post-no-preference/earnings", "NOT point-in-time", "as above", "NOT_ASSUMED", False, "EXCLUDED_FROM_HISTORICAL_MODELS", "as income statement"),
    "dolthub_options_volatility_history": ("DoltHub post-no-preference/options", "point_in_time (snapshot-dated)", "as above", "NOT_ASSUMED", False, "RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED", "2019-05-10 onward; partial universe"),
    "dolthub_options_chain_daily": ("DoltHub post-no-preference/options (aggregated locally)", "point_in_time (snapshot-dated)", "as above", "NOT_ASSUMED", False, "RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED", "2019 onward; irregular cadence"),
    "dolthub_rates_us_treasury": ("DoltHub post-no-preference/rates", "point_in_time for the daily curve (one-session lag in model)", "as above", "NOT_ASSUMED", True, "RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED", "not an ALFRED vintage series"),
    "french_factors_daily": ("Kenneth R. French Data Library", "evaluation series (published with lag)", "free for research; redistribution not assumed", "NOT_ASSUMED", False, "RESEARCH_ONLY", "attribution only, never a feature"),
}
ROOT_DATASETS = {
    "data/raw/sec": ("SEC Financial Statement Data Sets", "as-reported (vintage-preserving source)", "US government public data; SEC fair-access (<=10 requests/s, declared User-Agent)", "PERMITTED_BUT_NOT_COMMITTED_FOR_SIZE", True, "RESEARCH_ONLY_PRODUCT_AFTER_ATTRIBUTION_REVIEW", "58 quarterly ZIPs 2011Q1-2025Q2; no official checksums exist, hashes are self-recorded"),
    "data/raw/security_master": ("SEC company_tickers_exchange.json (current snapshot)", "NOT point-in-time (current only)", "US government public data", "PERMITTED_BUT_NOT_COMMITTED", True, "RESEARCH_ONLY", "must never be back-dated"),
    "data/curated/sec": ("derived from SEC FSDS (this project)", "as-reported vintages", "derived from public data", "NOT_COMMITTED", True, "RESEARCH_ONLY_UNTIL_REBUILT_V3", "v2 store has known defects (see docs/SEC_TAG_MAP_AUDIT.md)"),
    "data/curated/security_master": ("derived (this project)", "PARTIAL (current-snapshot identity)", "derived", "NOT_COMMITTED", True, "RESEARCH_ONLY", "historical intervals incomplete"),
    "data/research/universe": ("derived from the stocks OHLCV (this project)", "point_in_time by construction (trailing windows)", "derived", "NOT_COMMITTED", True, "RESEARCH_ONLY", "top-250 liquid non-ETF; partial delisting inference before 2017-10-26"),
    "data/research/derived": ("derived caches (this project)", "derived", "derived", "NOT_COMMITTED", True, "RESEARCH_ONLY", "frozen frame/panels plus EXP-010B daily panel"),
    "artifacts": ("this project (EXP-006 model + runtime snapshot)", "derived", "n/a", "SMALL_ARTIFACTS_TRACKED_AS_REPO_DECIDES", False, "PRODUCT_RUNTIME_ONLY_NOT_PROMOTED", "EXP-006 model is EXPERIMENTAL, not promoted"),
    "experiments": ("this project (immutable experiment records)", "derived", "n/a", "AGGREGATES_TRACKED_PREDICTIONS_IGNORED", True, "RESEARCH_RECORD", "predictions/checkpoints are git-ignored"),
    "research_vault": ("generated research reports", "n/a", "n/a", "IGNORED_EXCEPT_EXAMPLE", False, "PRODUCT_OUTPUT", "runtime output"),
    "research_papers": ("third-party published PDFs", "n/a", "copyrighted", "MUST_NOT_BE_COMMITTED", False, "LOCAL_READING_ONLY", "gitignored"),
    "datasets": ("DoltHub clones (stocks/options/earnings/rates)", "raw clones", "open data on DoltHub; terms not reviewed", "NOT_COMMITTED", True, "RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED", "source of the normalised Parquet under data/research/raw"),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def tracked(path: str) -> bool:
    out = subprocess.run(["git", "ls-files", "--", path], cwd=ROOT, capture_output=True, text=True).stdout
    return bool(out.strip())


def parquet_facts(paths: list[Path]) -> dict[str, Any]:
    rows, columns = 0, None
    for path in paths:
        meta = pq.ParquetFile(path)
        rows += meta.metadata.num_rows
        columns = columns or meta.schema_arrow.names
    return {"rows": rows, "columns": columns or []}


def symbol_count(paths: list[Path], column: str) -> int | None:
    seen: set[str] = set()
    for path in paths:
        if column not in pq.ParquetFile(path).schema_arrow.names:
            return None
        seen.update(pq.read_table(path, columns=[column]).column(column).unique().to_pylist())
    return len(seen)


def normalized_entries() -> list[dict[str, Any]]:
    entries = []
    for directory in sorted(RAW.iterdir()):
        manifest_path = directory / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text())
        paths = sorted(directory.glob("part-*.parquet"))
        facts = parquet_facts(paths)
        symbols = None
        for column in ("symbol", "act_symbol"):
            symbols = symbol_count(paths, column)
            if symbols is not None:
                break
        checksums = sorted(p["checksum"] for p in manifest.get("partitions", []))
        measured = sha256_file(paths[0]) if paths else None
        provider, pit, licence, redistribution, in_frozen_research, use, caveat = JUDGEMENT.get(directory.name, ("UNASSESSED",) * 7)
        entries.append({
            "id": directory.name, "path": str(directory.relative_to(ROOT)), "provider": provider,
            "source": f"{manifest.get('source')}:{manifest.get('source_version')}",
            "rows": facts["rows"], "manifest_rows": manifest.get("rows"), "symbols": symbols,
            "date_min": manifest.get("min_date"), "date_max": manifest.get("max_date"),
            "bytes": tree_size(directory), "columns": facts["columns"],
            "pit_status": pit, "manifest_pit_status": manifest.get("point_in_time_status"),
            "license": licence, "redistribution": redistribution,
            "sha256": {"method": "sha256 over the sorted per-partition checksums recorded in manifest.json",
                       "value": hashlib.sha256("".join(checksums).encode()).hexdigest(),
                       "first_partition_recomputed_matches": bool(paths) and measured == next(
                           (p["checksum"] for p in manifest["partitions"] if p["path"] == paths[0].name), None)},
            "usable_for_research": use, "usable_for_product": use.startswith("RESEARCH_AND_PRODUCT"),
            "used_by_frozen_research": in_frozen_research,
            "caveats": caveat, "tracked_in_git": tracked(str(directory.relative_to(ROOT))),
        })
    return entries


def directory_entries() -> list[dict[str, Any]]:
    entries = []
    for relative, (provider, pit, licence, redistribution, in_frozen_research, use, caveat) in ROOT_DATASETS.items():
        path = ROOT / relative
        if not path.exists():
            entries.append({"id": relative, "path": relative, "status": "ABSENT"})
            continue
        files = [p for p in path.rglob("*") if p.is_file()]
        parquet = sorted(p for p in files if p.suffix == ".parquet")
        digest = hashlib.sha256()
        hashed = relative not in ("datasets",)
        if hashed:
            for file in sorted(files):
                if file.name == ".DS_Store" or file.suffix == ".part":
                    continue
                digest.update(str(file.relative_to(path)).encode())
                digest.update(sha256_file(file).encode())
        entry = {
            "id": relative, "path": relative, "provider": provider, "source": provider, "files": len(files),
            "bytes": sum(p.stat().st_size for p in files), "pit_status": pit, "license": licence,
            "redistribution": redistribution, "usable_for_research": use,
            "usable_for_product": use.startswith("RESEARCH_AND_PRODUCT"), "used_by_frozen_research": in_frozen_research,
            "caveats": caveat,
            "sha256": {"method": "sha256 over relative path + sha256 of every file, sorted" if hashed else "NOT_COMPUTED (14 GB Dolt clones; see per-partition checksums of the normalised copies)",
                       "value": digest.hexdigest() if hashed else None},
            "tracked_in_git": tracked(relative),
        }
        if parquet:
            facts = parquet_facts(parquet)
            entry.update(rows=facts["rows"], columns=facts["columns"])
        entries.append(entry)
    return entries


def render_doc(inventory: dict[str, Any]) -> str:
    def size(n: int) -> str:
        return f"{n / 1024**3:.2f} GiB" if n >= 1024**3 else f"{n / 1024**2:.1f} MiB"

    lines = [
        "# Local data inventory (final)", "",
        f"Generated {inventory['generated_at']} by `python -m scripts.quant.data_inventory` from measured file metadata.",
        "Machine-readable: `data/manifests/data_inventory.json`. Row counts, sizes, columns and hashes are measured; the",
        "PIT, licence and usability columns are explicit judgements (`UNASSESSED` if none was recorded). Nothing listed",
        "as `NOT_COMMITTED` is in git.", "",
        "## Normalised research partitions (`data/research/raw/*`)", "",
        "| Dataset | Provider | Rows | Symbols | Dates | Size | PIT status | Research use | Caveats |", "|---|---|---:|---:|---|---:|---|---|---|",
    ]
    for e in inventory["normalized_datasets"]:
        lines.append(f"| `{e['id']}` | {e['provider']} | {e['rows']:,} | {e['symbols'] if e['symbols'] is not None else '-'} | "
                     f"{e['date_min']} → {e['date_max']} | {size(e['bytes'])} | {e['pit_status']} | {e['usable_for_research']} | {e['caveats']} |")
    lines += ["", "## Other stores", "", "| Path | Provider / source | Files | Rows | Size | PIT status | Licence / redistribution | Use | Git | Caveats |", "|---|---|---:|---:|---:|---|---|---|---|---|"]
    for e in inventory["stores"]:
        if e.get("status") == "ABSENT":
            lines.append(f"| `{e['path']}` | ABSENT | | | | | | | | |")
            continue
        lines.append(f"| `{e['path']}` | {e['provider']} | {e['files']:,} | {e.get('rows', '-') if e.get('rows') is None else f'{e['rows']:,}'} | {size(e['bytes'])} | "
                     f"{e['pit_status']} | {e['license']}; redistribution {e['redistribution']} | {e['usable_for_research']} | "
                     f"{'tracked' if e['tracked_in_git'] else 'not tracked'} | {e['caveats']} |")
    lines += ["", "## Reading this table", "",
              "* `usable_for_product` is true only where a licence review and attribution are complete; nothing here is currently product-cleared.",
              "* Dolt-sourced datasets carry an \"open data on DoltHub\" note, not a licence: redistribution is **not assumed**, and none is committed.",
              "* `data/curated/sec` is the v2 store with the defects recorded in `docs/SEC_TAG_MAP_AUDIT.md`; it is superseded by the v3 rebuild.",
              "* Every symbol-keyed dataset is keyed by ticker, which is not a stable identity (`docs/PIT_SECURITY_MASTER_PLAN.md`).", ""]
    return "\n".join(lines)


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    inventory = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "normalized_datasets": normalized_entries(), "stores": directory_entries(),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(inventory, indent=2, sort_keys=True, default=str) + "\n")
    OUT_DOC.write_text(render_doc(inventory))
    print(f"wrote {OUT_JSON.relative_to(ROOT)} and {OUT_DOC.relative_to(ROOT)}: "
          f"{len(inventory['normalized_datasets'])} normalised datasets, {len(inventory['stores'])} stores")
    return 0


if __name__ == "__main__":
    sys.exit(main())
