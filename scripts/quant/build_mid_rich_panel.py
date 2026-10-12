"""Assemble the rich point-in-time panel (26 baseline + 50 SEC characteristics) for the independent firm sample, with the same construction as the frozen panel.

`src/quant/pit/rich_panel_build.build` assembled the frozen panel from the frozen frame and the frozen security master. This script repeats that construction for the sample of liquidity ranks 251 to 1,000:

* the baseline frame comes from `data/research_mid/derived/mid_baseline_frame.parquet` (built by `scripts/quant/build_independent_sample.py baseline`);
* identities, classification and share counts come from `data/curated/security_master_mid/` (built by `scripts/quant/build_mid_security_master.py`);
* SEC facts are the shared curated store (`data/curated/sec_v3`, all Financial Statement Data Sets filers, accepted on or before 2025-05-09);
* size and industry-relative controls are withheld, as in the frozen panel: the market-capitalisation gate is reported but never used to widen the feature set;
* nothing after 2025-05-09 is read or written, and the holdout firewall is checked on the frame.

The coverage of the identity layer is reported with the repository's own gate (`pit_coverage.security_master_status`), so that a sample whose identities cannot be trusted says so before anything is fitted.
No relationship between a feature and a label is computed here.

    python -m scripts.quant.build_mid_rich_panel
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.quant.build_mid_security_master import load_mid_ohlcv
from src.quant.features import pit_fundamentals as F
from src.quant.pit import pit_coverage as C
from src.quant.pit import rich_panel as R
from src.quant.pit import security_master as M
from src.quant.pit.rich_panel_build import CUTOFF, feature_coverage, load_facts, missingness_versus_exit
from src.quant.pit.sec_foundation import atomic_json, sha256_file
from src.quant.study import exp009b
from src.quant.study.firewall import FIREWALL

ROOT = Path(".")
FRAME = ROOT / "data/research_mid/derived/mid_baseline_frame.parquet"
TABLES = ROOT / "data/curated/security_master_mid"
PANEL = ROOT / "data/research_mid/derived/rich_pit_panel_mid.parquet"
MANIFEST = ROOT / "data/manifests/rich_pit_panel_mid_manifest.json"
CONTROLS_ALLOWED = False          # decided before the build: the 76-feature set of the frozen panel, no size or industry-relative controls


def main() -> int:
    began = time.perf_counter()
    exp009b.arm_firewall(ROOT)
    frame = pd.read_parquet(FRAME)
    frame["date"] = pd.to_datetime(frame["date"])
    FIREWALL.assert_clear(frame.assign(date=frame["date"].dt.date), context="mid baseline frame")
    assert frame["date"].max() <= CUTOFF, "the frame extends past the research cutoff"
    frame = frame[frame["in_universe"]].copy()
    base = frame[["date", "symbol", "close", *R.PASSTHROUGH[:2], *R.LABELS, *R.BASELINE_FEATURES]].copy()
    identities = pd.read_parquet(TABLES / "security_identity_interval.parquet")
    classification = pd.read_parquet(TABLES / "security_classification_interval.parquet")
    shares = pd.read_parquet(TABLES / "shares_fact_vintage.parquet")
    trusted_ciks = set(identities.loc[identities["status"].isin(C.TRUSTED_GRADES), "cik"].astype("int64"))
    facts = load_facts(ROOT, trusted_ciks)
    snapshots = F.build_snapshots(facts)
    splits = pd.read_parquet(ROOT / "data/research_mid/raw/dolthub_stocks_split/part-all.parquet")
    panel = R.build_panel(base, identities=identities, classification=classification, shares=shares, snapshots=snapshots, split_table=C.split_factor_table(splits),
                          controls_allowed=CONTROLS_ALLOWED)
    folds = [f.as_dict() for f in exp009b.recorded_plan(ROOT).folds]
    coverage = C.coverage_tables(panel, folds)
    gate = C.security_master_status(coverage)
    out = R.assemble(panel, CONTROLS_ALLOWED)
    assert out["date"].max() <= CUTOFF
    PANEL.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(PANEL, compression="zstd", index=False)
    features = R.feature_columns(CONTROLS_ALLOWED)
    columns = ["date", "symbol", "security_id", "cik", "identity_grade", "ff12", "ff17", "ff48", "sic", *R.PASSTHROUGH, *R.LABELS, *features]
    new_columns = [c for c in features if c not in R.BASELINE_FEATURES]
    ohlcv = load_mid_ohlcv()
    windows = M.price_windows(ohlcv[ohlcv["symbol"].isin(set(out["symbol"]))])
    manifest: dict[str, Any] = {
        "dataset": "rich point-in-time panel for the independent firm sample (liquidity ranks 251-1,000)", "panel_version": R.PANEL_VERSION, "content_hash": R.content_hash(out, columns),
        "rows": int(len(out)), "securities": int(out["security_id"].nunique()), "symbols": int(out["symbol"].nunique()), "dates": int(out["date"].nunique()),
        "date_min": str(out["date"].min().date()), "date_max": str(out["date"].max().date()), "feature_count": len(features), "feature_hash": R.feature_hash(features), "features": features,
        "targets": list(R.LABELS), "primary_target": "fwd_rank_21", "controls_allowed": CONTROLS_ALLOWED, "controls_withheld": list(R.CONTROL_FEATURES),
        "identity": {"rows_with_trusted_identity": int(out["security_id"].notna().sum()), "share_trusted": float(out["security_id"].notna().mean()),
                     "grades": {str(k): int(v) for k, v in out["identity_grade"].value_counts(dropna=False).items()}},
        "identity_gate": gate, "coverage_by_year": coverage["by_year"], "coverage_by_period": coverage["by_period"],
        "feature_coverage": feature_coverage(out, new_columns, folds), "missingness_vs_exit": missingness_versus_exit(out, windows),
        "inputs": {"baseline_frame": {"path": str(FRAME), "sha256": sha256_file(FRAME)},
                   "security_master_tables": {p.name: sha256_file(p) for p in sorted(TABLES.glob("*.parquet"))}},
        "cutoff": str(CUTOFF.date()), "holdout": {"start": "2025-08-26", "touched": False},
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "build_seconds": round(time.perf_counter() - began, 1),
    }
    atomic_json(MANIFEST, manifest)
    print(json.dumps({k: manifest[k] for k in ("rows", "securities", "symbols", "dates", "date_min", "date_max", "identity", "identity_gate")}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
