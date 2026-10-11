#!/usr/bin/env python3
"""Export the research-signal registry from the repository's own declarations.

The rows come from code, not from prose: `src/quant/features/registry.py` (57 definitions, each declaring its
formula, rationale, lookback, availability lag and point-in-time status), the arm definitions in
`src/quant/study/families.py` resolved against the frozen EXP-007 column list, `src/quant/pit/rich_panel_catalog.py`
(the rich point-in-time characteristics) and the EXP-011 preregistered feature lists. Interpretive fields that code
cannot supply (live-product signals, hypotheses beyond the registry rationale) are added by the audit shards and
merged later; every row here is marked VERIFIED-IN-CODE with the module that declares it.

Run with the repository interpreter:  .venv/bin/python docs/research/market-signal-review-2026-10-11/code/export_signal_registry.py
Read-only with respect to the repository: it imports declarations and reads artifacts; it writes only signals_core.csv.
"""

from __future__ import annotations

import csv
import importlib
import json
import pkgutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "signals_core.csv"
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))

import src.quant.features as features_pkg  # noqa: E402
from src.quant.features.registry import REGISTRY  # noqa: E402
from src.quant.pit.rich_panel_catalog import CATALOG  # noqa: E402
from src.quant.study.families import DEFAULT_ARMS, arm_features  # noqa: E402

for mod in pkgutil.iter_modules(features_pkg.__path__):
    importlib.import_module(f"src.quant.features.{mod.name}")

FIELDS = ["signal_id", "name", "layer", "scope", "family", "definition", "hypothesis", "inputs", "source_datasets",
          "frequency", "timestamp_semantics", "expected_lag", "missing_semantics", "normalization", "known_failure_modes",
          "related_literature", "empirical_status", "experiments_used", "code_refs", "redundancy_notes", "verified", "confidence"]

#: Duplicates and strong overlaps that the repository itself measured (docs/CURRENT_QUANT_RESEARCH_AUDIT.md, feature audit).
REDUNDANT = {
    "dist_52w_high": "exactly -max_drawdown_252 as a cross-sectional axis (Spearman -1.000); retain one",
    "max_drawdown_252": "exactly -dist_52w_high as a cross-sectional axis (Spearman -1.000); retain one",
    "mom_63": "Spearman 0.953 with trend_strength_63; 0.831 with ma_gap",
    "trend_strength_63": "Spearman 0.953 with mom_63",
    "downside_vol_63": "Spearman 0.915 with vol_63",
    "vol_63": "0.915 with downside_vol_63; 0.853 with vol_21",
    "vol_21": "0.853 with vol_63",
    "ma_gap": "0.831 with mom_63",
    "amihud_21": "-0.788 with log_dollar_volume_21 (same liquidity axis)",
    "log_dollar_volume_21": "-0.788 with amihud_21 (same liquidity axis)",
    "rates_short": "-0.903 Spearman with rates_slope",
    "rates_slope": "-0.903 Spearman with rates_short",
    "market_vol_21": "0.816 with market_vol_percentile",
    "market_vol_percentile": "0.816 with market_vol_21",
}

SOURCE_BY_GROUP = {
    "price": "daily adjusted OHLCV panel", "volatility": "daily adjusted OHLCV panel", "volume": "daily OHLCV panel",
    "structure": "daily adjusted OHLCV panel", "cross_sectional": "daily OHLCV panel (cross-sectional stage)",
    "macro": "Treasury par yield curve and market-state series", "options": "vendor options implied-volatility history",
    "fundamental": "SEC-derived or vendor statements / earnings / analyst estimates (per feature prefix)",
}


def main() -> int:
    ds = json.loads((REPO / "artifacts/experiments/EXP-007/final_selection.json").read_text())
    columns = ds["dataset"]["features"]
    arms = {arm.name: set(arm_features(arm, columns)) for arm in DEFAULT_ARMS}
    exp7_arms = ("C_base", "D_base_options", "E_base_estimates")
    exp011 = json.loads((REPO / "experiments/EXP-011/config.json").read_text())["features"]
    rows = []

    for name in sorted(REGISTRY.definitions):
        d = REGISTRY.definitions[name]
        xs = f"{name}_xs" in columns
        used = sorted({a for a, cols in arms.items() if (f"{name}_xs" in cols or name in cols)})
        in_exp7 = [a for a in used if a in exp7_arms]
        in_011 = [k for k, v in exp011.items() if f"{name}_xs" in v or name in v]
        rows.append({
            "signal_id": f"reg.{name}", "name": name, "layer": "transformed_feature", "scope": "research_only",
            "family": d.group.value, "definition": d.formula, "hypothesis": d.rationale or d.description,
            "inputs": ";".join(d.required_columns), "source_datasets": SOURCE_BY_GROUP.get(d.group.value, ""),
            "frequency": "daily values, sampled every 5 sessions in the EXP-007 panel",
            "timestamp_semantics": f"availability_lag_sessions={d.availability_lag_sessions}; point_in_time_safe={d.point_in_time_safe}; "
                                   f"backward-looking window of {d.lookback_sessions} sessions",
            "expected_lag": f"{d.availability_lag_sessions} session(s)",
            "missing_semantics": f"NULL until {d.lookback_sessions} sessions of history exist; never imputed to zero (registry docstring)",
            "normalization": "cross-sectional rank exposed as %s_xs" % name if xs else "used raw (not cross-sectionally ranked)",
            "known_failure_modes": "; ".join(d.notes), "related_literature": d.citation,
            "empirical_status": "no stand-alone evaluation recorded; evaluated only as part of arms: " + (", ".join(used) or "none")
                                + ("; EXP-011 baseline feature list" if "baseline" in in_011 else ""),
            "experiments_used": ";".join(["EXP-007:" + a for a in in_exp7] + (["EXP-011:" + k for k in in_011])),
            "code_refs": f"src/quant/features/registry.py (definition); module for '{name}' under src/quant/features/",
            "redundancy_notes": REDUNDANT.get(name, ""), "verified": "VERIFIED-IN-CODE", "confidence": "high",
        })

    rich = exp011.get("rich", [])
    for name, (formula, inputs, limitation) in sorted(CATALOG.items()):
        used = [k for k in ("rich",) if name in rich or f"{name}_xs" in rich]
        rows.append({
            "signal_id": f"pit.{name}", "name": name, "layer": "transformed_feature", "scope": "research_only",
            "family": "rich_pit_characteristic", "definition": formula, "hypothesis": "see related literature in the formula; no hypothesis text in the catalogue",
            "inputs": inputs, "source_datasets": "SEC as-reported XBRL facts (sec-core-facts-v3) with PIT market data",
            "frequency": "quarterly filings, aligned to the daily panel",
            "timestamp_semantics": "SEC acceptance-time gated (as-reported); restatement vintage not certified (docs/CURRENT_QUANT_RESEARCH_AUDIT.md)",
            "expected_lag": "filing acceptance date to next session", "missing_semantics": "NULL when the filing history or denominator is unavailable",
            "normalization": "cross-sectional rank in the rich arm" if used else "see panel build",
            "known_failure_modes": limitation, "related_literature": "see catalogue formula",
            "empirical_status": "EXP-011 2x2: IMPROVES_ONLY_LINEAR for the preregistered 50-feature extension as a block; no per-feature result",
            "experiments_used": "EXP-011:rich" if used else "rich PIT panel (not in the EXP-011 preregistered list)" ,
            "code_refs": "src/quant/pit/rich_panel_catalog.py", "redundancy_notes": "", "verified": "VERIFIED-IN-CODE", "confidence": "high",
        })

    with OUT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    summary = {"registry_definitions": len(REGISTRY.definitions), "rich_catalog": len(CATALOG),
               "frozen_columns": len(columns), "xs_variants": sum(c.endswith("_xs") for c in columns), "rows_written": len(rows),
               "arm_sizes": {k: len(v) for k, v in arms.items()}}
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
