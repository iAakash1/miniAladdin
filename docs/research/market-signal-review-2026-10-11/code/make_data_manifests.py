#!/usr/bin/env python3
"""Write dataset_catalogue.csv, data_manifest.json and provenance_manifest.json.

Sources: the manifests the repository already keeps (data_inventory.json, sec_download_manifest.json, the rich-panel manifest, the reliability manifest), fresh SHA-256 of the three
files EXP-012 reads or builds, the git history of the code that produced them, and (when the study has run) the hashes in experiments/EXP-012/manifest.json. Nothing is downloaded.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/make_data_manifests.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import subprocess
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
REPO = HERE.parents[3]
TODAY = date.today().isoformat()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout.strip()


def file_entry(rel: str, role: str, **extra) -> dict:
    p = REPO / rel
    return {"path": rel, "role": role, "bytes": p.stat().st_size, "sha256": sha256(p), **extra}


def main() -> None:
    inventory = json.loads((REPO / "data/manifests/data_inventory.json").read_text())
    sec = json.loads((REPO / "data/manifests/sec_download_manifest.json").read_text())
    rel = json.loads((REPO / "data/manifests/reliability_v1_manifest.json").read_text())
    rich = json.loads((REPO / "data/manifests/rich_pit_panel_manifest.json").read_text())

    # ── catalogue: every store and normalised dataset in the inventory, plus the table this study builds ──
    columns = ["id", "kind", "path", "rows", "bytes", "sha256", "provider", "source", "license", "redistribution", "pit_status", "tracked_in_git",
               "usable_for_research", "usable_for_product", "used_by_frozen_research", "caveats"]
    rows = []
    for s in inventory["stores"]:
        rows.append({"kind": "store", **{k: s.get(k, "") for k in columns if k != "kind"}, "sha256": json.dumps(s["sha256"]) if isinstance(s.get("sha256"), dict) else s.get("sha256", "")})
    for d in inventory["normalized_datasets"]:
        rows.append({"kind": "normalized_dataset", **{k: d.get(k, "") for k in columns if k != "kind"}})
    rows.append({"id": "reliability_v1", "kind": "derived", "path": rel["output"]["path"], "rows": rel["rows"], "bytes": rel["output"]["bytes"], "sha256": rel["output"]["sha256"],
                 "provider": "derived from the SEC Financial Statement Data Sets registry", "source": rel["inputs"]["filings_parquet"], "license": rel["license"],
                 "redistribution": "derived counts only; the parquet is git-ignored, its manifest is committed", "pit_status": rel["rule"], "tracked_in_git": "False (manifest: True)",
                 "usable_for_research": "True", "usable_for_product": "False", "used_by_frozen_research": "False (used by EXP-012)",
                 "caveats": "coverage 91.8%; three of four variables nearly constant; see data_quality_report.md"})
    with (BASE / "dataset_catalogue.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    # ── data manifest: the files EXP-012 reads or builds, with fresh hashes ──
    filings = file_entry(rel["inputs"]["filings_parquet"], "input: SEC filing registry", rows=rel["inputs"]["filings_rows"], recorded_sha256=rel["inputs"]["filings_sha256"])
    panel = file_entry("data/research/derived/rich_pit_panel.parquet", "input: rich point-in-time panel", rows=rich.get("rows"), dataset_id=rich.get("dataset_id"),
                       content_hash=rich.get("content_hash"), date_min=rich.get("date_min"), date_max=rich.get("date_max"))
    table = file_entry(rel["output"]["path"], "derived: reliability table", rows=rel["rows"], coverage=rel["coverage"], recorded_sha256=rel["output"]["sha256"])
    for entry in (filings, panel, table):
        if entry.get("recorded_sha256"):
            entry["matches_recorded_hash"] = entry["sha256"] == entry["recorded_sha256"]
    outputs = []
    study = REPO / "experiments/EXP-012"
    if (study / "manifest.json").exists():
        outputs = [file_entry(str(p.relative_to(REPO)), "output: EXP-012") for p in sorted(study.glob("*")) if p.is_file()]
        outputs += [file_entry(str(p.relative_to(REPO)), "output: saved research model (git-ignored)") for p in sorted((study / "model").glob("*.joblib"))]
    manifest = {
        "generated": TODAY, "study": "EXP-012", "licence_note": "SEC filings are public records; no filing text is redistributed. The price panel's community source has terms that were not reviewed (datasets.csv L04).",
        "inputs": [filings, panel], "derived": [table], "outputs": outputs,
        "checks": {"reliability_manifest_matches_file": table["matches_recorded_hash"], "filings_match_recorded_hash": filings["matches_recorded_hash"],
                   "validation": "validation/reliability_validation.json (0 mismatches in 16,000 independent comparisons)", "data_quality": "data_quality_report.md"},
    }
    (BASE / "data_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")

    # ── provenance: the chain from the SEC archives to the study outputs, with the code that made each step ──
    commits = {name: git("log", "-1", "--format=%H", "--", *paths) for name, paths in {
        "reliability_code": ["src/quant/pit/reliability.py"], "study_code_and_registration": ["src/quant/study/exp012.py", "docs/EXP_012_PREREGISTRATION.md"]}.items()}
    results = json.loads((study / "manifest.json").read_text()) if (study / "manifest.json").exists() else {}
    provenance = {
        "generated": TODAY, "branch": git("rev-parse", "--abbrev-ref", "HEAD"), "head": git("rev-parse", "HEAD"),
        "identity_of_head": {"author": git("show", "-s", "--format=%an", "HEAD"), "committer": git("show", "-s", "--format=%cn", "HEAD"),
                             "author_and_committer_addresses_equal": git("show", "-s", "--format=%ae", "HEAD") == git("show", "-s", "--format=%ce", "HEAD")},
        "lineage": [
            {"step": 1, "what": "SEC Financial Statement Data Sets quarterly archives", "count": len(sec["archives"]), "first": sec["archives"][0]["filename"], "last": sec["archives"][-1]["filename"],
             "bytes": sec["total_bytes"], "retrieved": [sec["archives"][0]["retrieved_at"], sec["archives"][-1]["retrieved_at"]], "manifest": "data/manifests/sec_download_manifest.json",
             "manifest_sha256": sha256(REPO / "data/manifests/sec_download_manifest.json"), "fair_access_max_requests_per_second": sec["fair_access_max_requests_per_second"],
             "note": "no official checksums exist; hashes were recorded at download"},
            {"step": 2, "what": "curated filing registry", "output": filings["path"], "sha256": filings["sha256"], "rows": filings["rows"], "built_by": "scripts/quant/build_pit_data.py build-facts-v3"},
            {"step": 3, "what": "rich point-in-time panel (EXP-011 identity)", "output": panel["path"], "sha256": panel["sha256"], "dataset_id": panel["dataset_id"], "built_by": "scripts/quant/build_pit_data.py build-rich-panel"},
            {"step": 4, "what": "reliability table", "output": table["path"], "sha256": table["sha256"], "built_by": "python -m src.quant.pit.reliability build", "code_commit": commits["reliability_code"],
             "inputs": [filings["sha256"], rel["inputs"]["rich_panel_content_hash"]]},
            {"step": 5, "what": "EXP-012 registered study", "code_and_registration_commit": commits["study_code_and_registration"], "fingerprint": results.get("definition_fingerprint"),
             "manifest": "experiments/EXP-012/manifest.json" if results else "not yet run", "manifest_sha256": sha256(study / "manifest.json") if results else None,
             "run_git_commit": results.get("git_commit"), "run_git_dirty": results.get("git_dirty"), "completion": results.get("completion")},
        ],
        "environment": {"python": platform.python_version(), "platform": platform.platform(), "dependencies": results.get("dependency_versions")},
        "protected": "EXP-006 and EXP-007 files unchanged (hash comparison before and after); the holdout is sealed and untouched",
    }
    (BASE / "provenance_manifest.json").write_text(json.dumps(provenance, indent=1) + "\n")
    print(f"catalogue rows {len(rows)}; manifest inputs {len(manifest['inputs'])}, outputs {len(outputs)}; provenance steps {len(provenance['lineage'])}")


if __name__ == "__main__":
    main()
