"""Run a slice of preregistered fits inside an exported bundle.  Independent process; one per worker id."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pandas as pd


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def device_info() -> str:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"], capture_output=True, text=True, timeout=10)
        return ("gpu:" + out.stdout.strip().replace("\n", "|")) if out.returncode == 0 and out.stdout.strip() else "cpu"
    except Exception:
        return "cpu"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    bundle, out = Path(args.bundle), Path(args.out)
    manifest = json.loads((bundle / "manifest.json").read_text())
    work = out / "_work"
    work.mkdir(parents=True, exist_ok=True)
    code = bundle / manifest["code_bundle"]["file"]
    if sha256(code) != manifest["code_bundle"]["sha256"]:
        raise SystemExit("REJECTED: code bundle hash differs from the manifest")
    with zipfile.ZipFile(code) as archive:
        archive.extractall(work)
    sys.path.insert(0, str(work))
    os.chdir(work)
    parts = []
    for shard in manifest["shards"]:
        path = bundle / shard["file"]
        if sha256(path) != shard["sha256"]:
            raise SystemExit(f"REJECTED: shard {shard['file']} hash differs from the manifest")
        parts.append(pd.read_parquet(path))
    panel = pd.concat(parts, ignore_index=True)
    panel_path = work / "rich_panel.parquet"
    panel.to_parquet(panel_path, index=False)

    from src.quant.study import exp011

    exp011.RICH_DATASET_ID  # imported to fail loudly if the bundle code is not the registered code
    if exp011.RICH_CONTENT_HASH != manifest["rich_content_hash"] or exp011.RICH_FEATURE_HASH != manifest["rich_feature_hash"]:
        raise SystemExit("REJECTED: bundled code registers a different dataset than the manifest")
    frame, checks = exp011.load_rich_panel(work, path=panel_path)
    plan = exp011.exp009b.recorded_plan(work)
    fingerprint = manifest["definition_fingerprint"]
    assignments = next(w for w in manifest["workers"] if w["id"] == args.worker)["assignments"]
    device = device_info()
    results = out / "results"
    results.mkdir(parents=True, exist_ok=True)
    for arm, seeds in assignments.items():
        for seed in seeds:
            result = exp011.fit_arm_seed(arm, seed, frame, plan)
            if result.errors or result.predictions is None or len(result.folds) != 8:
                raise SystemExit(f"{arm} seed {seed} failed: {result.errors}")
            parquet, receipt_path = exp011.checkpoint_paths(results.parent, arm, seed)
            parquet = results / parquet.name
            receipt_path = results / receipt_path.name
            result.predictions.to_parquet(parquet, index=False)
            receipt = exp011.receipt_for(arm, seed, result.predictions, float(result.seconds), fingerprint=fingerprint, root=work,
                                         device=device, commit=manifest["git_commit"])
            receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True, default=str) + "\n")
            print(f"{args.worker}: {arm} seed {seed} done on {device} in {result.seconds:.0f}s", flush=True)
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
