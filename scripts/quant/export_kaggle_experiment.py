"""Export a preregistered experiment for independent Kaggle workers.

The export is a hash-pinned bundle: date-sharded data, a code bundle, an experiment manifest and the seed
partition.  Workers are INDEPENDENT processes (one per GPU/CPU slot), never DDP and never pooled memory:
two T4s are two 16 GB devices.  The EXP-011 models are scikit-learn (CPU); the bundle records that honestly
and does not pretend a GPU is used.

Refuses to run unless the preregistration gate passes, and refuses to export price-derived data unless the
data-licence acknowledgement is given explicitly (the Dolt-sourced sets carry an "open data" note, not a
reviewed licence).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CODE_FILES = ["requirements-quant.txt", "requirements.txt", "docs/HOLDOUT_CONTRACT.md", "experiments/EXP-006/metrics.json"]
CODE_TREES = ["src/quant", "src/research"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_code_bundle(target: Path) -> str:
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for tree in CODE_TREES:
            base = ROOT / tree
            if not base.exists():
                continue
            for path in sorted(base.rglob("*.py")):
                archive.write(path, path.relative_to(ROOT))
        for name in CODE_FILES:
            if (ROOT / name).exists():
                archive.write(ROOT / name, name)
        archive.write(ROOT / "scripts/quant/kaggle_worker.py", "scripts/quant/kaggle_worker.py")
    return sha256(target)


def partition(seeds: list[int], workers: int) -> list[list[int]]:
    return [seeds[i::workers] for i in range(workers)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", default="EXP-011")
    parser.add_argument("--out", default=None)
    parser.add_argument("--workers", type=int, default=2, help="independent workers (e.g. two T4 slots)")
    parser.add_argument("--shards", type=int, default=6)
    parser.add_argument("--acknowledge-data-license", action="store_true",
                        help="I have reviewed the terms of every source in the panel and external processing is permitted")
    parser.add_argument("--skip-gate", action="store_true", help="test only; the manifest records that the gate was skipped")
    args = parser.parse_args()
    if args.experiment != "EXP-011":
        raise SystemExit("only EXP-011 has a registered export")
    sys.path.insert(0, str(ROOT))
    from src.quant.study import exp011

    out = Path(args.out) if args.out else ROOT / "artifacts/kaggle" / args.experiment
    if not args.acknowledge_data_license:
        raise SystemExit("REFUSED: the panel contains price-derived features from sources whose terms are 'open data, not reviewed'. "
                         "Review them, then re-run with --acknowledge-data-license. Nothing was written.")
    gate = {"skipped": True} if args.skip_gate else exp011.prereg_gate(ROOT)
    panel, checks = exp011.load_rich_panel(ROOT)
    out.mkdir(parents=True, exist_ok=True)
    shards = []
    dates = sorted(panel["date"].unique())
    size = -(-len(dates) // args.shards)
    for index in range(args.shards):
        chunk = panel[panel["date"].isin(dates[index * size:(index + 1) * size])]
        if chunk.empty:
            continue
        path = out / f"panel_shard_{index:02d}.parquet"
        chunk.to_parquet(path, compression="zstd", index=False)
        shards.append({"file": path.name, "rows": int(len(chunk)), "sha256": sha256(path), "bytes": path.stat().st_size,
                       "first_date": str(chunk["date"].min()), "last_date": str(chunk["date"].max())})
    code_sha = build_code_bundle(out / "code_bundle.zip")
    fit_arms = [(a, list(exp011.ARMS[a]["seeds"])) for a in exp011.FIT_ORDER]
    workers = [{"id": f"worker{i}", "assignments": {arm: partition(seeds, args.workers)[i] for arm, seeds in fit_arms if seeds}}
               for i in range(args.workers)]
    manifest = {
        "experiment_id": args.experiment, "definition_fingerprint": exp011.definition_fingerprint(ROOT), "gate": gate,
        "rich_dataset_id": exp011.RICH_DATASET_ID, "rich_content_hash": exp011.RICH_CONTENT_HASH,
        "rich_feature_hash": exp011.RICH_FEATURE_HASH, "panel_checks": checks, "shards": shards,
        "code_bundle": {"file": "code_bundle.zip", "sha256": code_sha}, "workers": workers,
        "compute_note": "scikit-learn models are CPU-only; a GPU is not used. Workers are independent processes, not DDP.",
        "device_policy": "each worker records its own device/CUDA/package versions in every receipt",
        "license_acknowledged_by_user": True, "seeds": list(exp011.SEEDS),
        "requirements": {"scikit-learn": "1.7.2", "numpy": "2.2.6", "pandas": "2.3.3", "scipy": "1.18.1", "pyarrow": "18.1.0"},
        "git_commit": __import__("subprocess").run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (out / "README_KAGGLE.md").write_text("\n".join([
        f"# {args.experiment} on Kaggle", "",
        "1. Create a **private** Kaggle dataset from every file in this directory (panel shards, code_bundle.zip, manifest.json).",
        "2. New notebook -> add that dataset -> Settings: Internet ON (to pin scikit-learn 1.7.2), Accelerator: GPU T4 x2 (optional; unused by sklearn).",
        "3. In two notebook sessions or two cells run independently (never distributed):", "",
        *[f"       python scripts/quant/kaggle_worker.py --bundle /kaggle/input/<dataset> --worker {w['id']} --out /kaggle/working/results_{w['id']}" for w in workers], "",
        "4. Download `results_worker*` and import on the Mac:", "",
        f"       python -m scripts.quant.import_kaggle_results --results <dir> [<dir> ...]", "",
        "5. Then `python -m scripts.quant.exp011 run` finishes E2 (frozen EXP-010A), metrics and the paired analysis from the imported checkpoints.", ""]))
    print(json.dumps({"out": str(out), "shards": len(shards), "workers": [w["id"] for w in workers], "code_sha256": code_sha}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
