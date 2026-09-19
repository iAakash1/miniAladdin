"""Import worker results after verifying every receipt against the registered experiment.  Mismatches are rejected."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", nargs="+", required=True, help="one or more worker `results` directories")
    parser.add_argument("--allow-version-drift", action="store_true", help="accept differing numpy/pandas/scikit-learn versions (recorded)")
    parser.add_argument("--output-dir", default=None, help="experiment output directory (default experiments/EXP-011)")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    from src.quant.study import exp011

    fingerprint = exp011.definition_fingerprint(ROOT)
    output = Path(args.output_dir) if args.output_dir else ROOT / exp011.OUTPUT_DIR
    destination = output / "checkpoints"
    accepted, rejected = [], []
    for directory in map(Path, args.results):
        for receipt_path in sorted(directory.glob("*_seed_*.json")):
            match = re.match(r"(E\d)_seed_(\d+)\.json", receipt_path.name)
            if not match:
                rejected.append({"file": str(receipt_path), "problems": ["unrecognised file name"]})
                continue
            arm, seed = match.group(1), int(match.group(2))
            parquet = receipt_path.with_name(f"{arm}_seed_{seed:02d}_predictions.parquet")
            if arm not in exp011.ARMS or seed not in exp011.ARMS[arm]["seeds"] or not exp011.ARMS[arm]["fit"] or not parquet.exists():
                rejected.append({"file": str(receipt_path), "problems": ["not a registered (arm, seed) or predictions missing"]})
                continue
            predictions = pd.read_parquet(parquet)
            predictions["date"] = pd.to_datetime(predictions["date"]).dt.date
            problems = exp011.verify_receipt(json.loads(receipt_path.read_text()), predictions, arm=arm, seed=seed,
                                             fingerprint=fingerprint, strict_versions=not args.allow_version_drift)
            if problems:
                rejected.append({"file": str(receipt_path), "problems": problems})
                continue
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copy2(parquet, destination / f"{arm}_seed_{seed:02d}_predictions.parquet")
            shutil.copy2(receipt_path, destination / f"{arm}_seed_{seed:02d}.json")
            accepted.append(f"{arm}_seed_{seed:02d}")
    report = {"accepted": accepted, "rejected": rejected, "fingerprint": fingerprint}
    output.mkdir(parents=True, exist_ok=True)
    (output / "import_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"accepted": len(accepted), "rejected": len(rejected)}, indent=2))
    for item in rejected:
        print("REJECTED", item["file"], item["problems"])
    return 1 if rejected else 0


if __name__ == "__main__":
    sys.exit(main())
