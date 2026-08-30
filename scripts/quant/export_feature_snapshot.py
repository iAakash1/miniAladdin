"""Export one dated feature snapshot so inference can be demonstrated.

## Why a snapshot rather than a live feature service

Computing the 27 features for a symbol needs the point-in-time panel, which
needs 14 GB of Dolt clones and a multi-minute build. None of that belongs on an
inference host, and putting it there would make the request path depend on the
research stack — the opposite of the split this deployment exists to create.

So the backend serves a **frozen, dated** snapshot: the feature vector for every
universe member on one specific date. Every response carries that date, because
a stale feature vector presented without its as-of date is indistinguishable
from a live one.

## The date is deliberately pre-holdout

The snapshot is taken at the last panel date strictly before the holdout starts.
The holdout is single-use and locked; computing features against it — even for
inference rather than evaluation — is exactly the kind of incidental contact the
firewall exists to prevent.

    python -m scripts.quant.export_feature_snapshot
"""

from __future__ import annotations

import argparse
import json
from datetime import date as Date
from pathlib import Path

import pandas as pd

from src.quant.datasets.store import RawStore
from src.quant.pit.dataset import DatasetBuilder
from src.quant.pit.universe import UniverseHistory
from src.quant.study.experiment import get_experiment
from src.quant.study.families import FeatureArm, arm_features
from src.quant.study.firewall import FIREWALL


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", default="EXP-006")
    parser.add_argument("--root", default="data/research", type=Path)
    parser.add_argument("--out", default=Path("artifacts"), type=Path)
    args = parser.parse_args()

    metrics = json.loads(
        (Path("experiments") / args.experiment / "metrics.json").read_text(encoding="utf-8")
    )
    definition = get_experiment(args.experiment)
    holdout_start = Date.fromisoformat(metrics["holdout"]["start"])

    store = RawStore(args.root)
    universe = UniverseHistory.load(Path(args.root) / "universe")
    dataset = DatasetBuilder(store, universe).build(
        start=definition.start, end=definition.end or Date.today(),
        step_sessions=definition.step_sessions, workers=6,
    )
    frame, manifest = dataset.frame, dataset.manifest

    cross = [n for n in manifest.features if n.endswith("_xs")]
    macro = [n for n in manifest.features if n.startswith(("rates_", "market_"))]
    features = arm_features(
        FeatureArm("declared", definition.feature_families, "frozen"), cross + macro
    )

    FIREWALL.arm_window(holdout_start, Date.fromisoformat(metrics["holdout"]["end"]))
    eligible = frame[(frame["date"] < holdout_start)]
    if "in_universe" in eligible.columns:
        eligible = eligible[eligible["in_universe"]]
    FIREWALL.assert_clear(eligible, context="feature snapshot export")

    as_of = eligible["date"].max()
    snapshot = eligible[eligible["date"] == as_of][["symbol", *features]].copy()
    snapshot = snapshot.sort_values("symbol").reset_index(drop=True)

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "feature_snapshot.parquet"
    snapshot.to_parquet(path, index=False, compression="zstd")

    meta = {
        "as_of": str(as_of),
        "symbols": int(len(snapshot)),
        "features": features,
        "feature_count": len(features),
        "experiment_id": args.experiment,
        "dataset_version": manifest.dataset_version,
        "dataset_content_hash": manifest.content_hash,
        "holdout_start": str(holdout_start),
        "note": (
            "A FROZEN snapshot at the last panel date strictly before the holdout "
            "begins. It is not live market data. Any prediction served from it "
            "describes conditions on as_of, not today."
        ),
    }
    (args.out / "feature_snapshot.metadata.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    print(f"as_of {as_of} · {len(snapshot)} symbols · {len(features)} features")
    print(f"wrote {path} ({path.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
