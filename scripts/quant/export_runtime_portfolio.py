"""Export a compact, deployable portfolio artifact from a frozen experiment.

This is an export, not training. It selects one model from the experiment's
existing prediction record, preserves the observed target and predicted rank
verbatim, and writes the minimum history required by Book/Risk/Covariance.
The output is content-addressed in adjacent metadata so deployment can reject
partial or stale files instead of attempting to interpret them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = 1


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export(experiment_id: str, model_id: str, target: str, source: Path) -> Path:
    frame = pd.read_parquet(source)
    required = ["date", "symbol", target, "prediction", "model"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"source artifact is missing columns: {', '.join(missing)}")

    runtime = frame.loc[frame["model"] == model_id, required].copy()
    if runtime.empty:
        raise ValueError(f"source artifact contains no rows for {model_id}")
    runtime = runtime.sort_values(["date", "symbol"], kind="stable").reset_index(drop=True)

    output_dir = ROOT / "artifacts" / "runtime" / "portfolio" / experiment_id / target
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{model_id}.parquet"
    runtime.to_parquet(output, index=False, compression="zstd")

    config = ROOT / "experiments" / experiment_id / "config.json"
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": experiment_id,
        "model_id": model_id,
        "target": target,
        "rows": int(len(runtime)),
        "symbols": int(runtime["symbol"].nunique()),
        "start": str(runtime["date"].min()),
        "end": str(runtime["date"].max()),
        "columns": required,
        "source_artifact": source.name,
        "source_artifact_sha256": sha256(source),
        "source_experiment_config_sha256": sha256(config) if config.exists() else None,
        "artifact_sha256": sha256(output),
        "semantics": (
            "Frozen out-of-sample cross-sectional ranks from the named experiment; "
            "prediction is a rank signal and the target is not a return."
        ),
    }
    output.with_suffix(".json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", default="EXP-006")
    parser.add_argument("--model", default="gradient_boosting")
    parser.add_argument("--target", default="fwd_rank_21")
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    source = args.source or (
        ROOT / "experiments" / args.experiment / f"predictions_{args.target}.parquet"
    )
    output = export(args.experiment, args.model, args.target, source.resolve())
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    main()
