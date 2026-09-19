"""
EXP-009D — is the exact duplicate feature axis redundant?

`dist_52w_high_xs` and `max_drawdown_252_xs` correlate at −1.000 in the frozen panel
(`docs/CURRENT_QUANT_RESEARCH_AUDIT.md`): the second is the first with the sign
reversed, so the 27-feature set carries 26 independent axes. This is hygiene, not
research: it asks only whether dropping the redundant column changes anything.

It is a separate experiment, not an edit to EXP-006 or to the EXP-009B feature list,
because a feature change moves the model's fitted trees even when the information
is identical (tie-breaking between the two perfectly (anti)correlated columns), and
that has to be measured rather than assumed.

Two arms on the frozen split, the same sklearn model and seed:

    FULL      the 27 frozen features (its predictions are EXP-006's, checked to 1e-9)
    DEDUP     the same, minus `max_drawdown_252_xs`

The criterion is **equivalence**, not superiority. Removing only the exact duplicate is
the one pruning step that needs no justification beyond arithmetic; any other pruning
would be a separate, counted trial and is not attempted here.
"""

from __future__ import annotations

import json
import os
import platform
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.quant.models.factory import ModelSpec
from src.quant.models.registry import dependency_versions
from src.quant.study import exp009a, exp009b, prereg
from src.quant.study.firewall import FIREWALL
from src.quant.validation.metrics import ic_summary
from src.quant.validation.parallel import evaluate_specs

EXPERIMENT_ID = "EXP-009D"
PARENT_EXPERIMENT = "EXP-006"
OUTPUT_DIR = Path("experiments") / EXPERIMENT_ID
PREREG_DOC = Path("docs/EXP_009D_DUPLICATE_AXIS_PREREGISTRATION.md")
DROPPED = "max_drawdown_252_xs"
KEPT = "dist_52w_high_xs"
LABEL = exp009b.LABEL
_C = exp009b._C

DEFINITION: dict[str, Any] = {
    "experiment_id": EXPERIMENT_ID,
    "parent_experiment": PARENT_EXPERIMENT,
    "status": "EXPERIMENTAL - HYGIENE - PROMOTION NOT ASSESSED",
    "question": "Does removing the exact duplicate axis change the model's ordering or its economics?",
    "duplicate": {"dropped": DROPPED, "kept": KEPT,
                  "evidence": "correlation -1.000 to three decimals in the audited panel (docs/CURRENT_QUANT_RESEARCH_AUDIT.md); measured -0.999996 on universe rows and verified again at run time"},
    "data": {"dataset_id": exp009b.DEFINITION["data"]["dataset_id"],
             "returns_panel_sha256": exp009b.DEFINITION["data"]["returns_panel_sha256"],
             "target": LABEL, "features_full": exp009b.FEATURES,
             "features_dedup": [f for f in exp009b.FEATURES if f != DROPPED],
             "folds": "the 8 folds recorded in experiments/EXP-006/metrics.json"},
    "model": {"name": "gradient_boosting", "kind": "gradient_boosting", "params": "repository defaults (unchanged)", "seed": 0},
    "arms": [
        {"id": "FULL", "features": 27, "seed": 0},
        {"id": "DEDUP", "features": 26, "seed": 0},
        {"id": "NOISE", "features": 27, "seed": 1,
         "role": "descriptive noise reference only: the same 27-feature model with a different seed; enters no criterion"},
    ],
    "gates": {
        "dataset_and_panel": "rebuilt dataset id and returns-panel hash equal the preregistered values",
        "full_reproduces": "the FULL arm equals EXP-006's frozen gradient_boosting predictions to 1e-9",
        "duplicate_is_exact": "the absolute correlation of the two columns on universe rows is >= 0.99999 (measured -0.999996 in the frozen panel: rank ties and a constant offset of 2/N separate them from -1)",
    },
    "criteria": {
        "margins": (
            "set from the noise floor EXP-009B measured for a change that alters no information — a different bagging "
            "implementation moved mean Rank IC by 0.0031 and net Sharpe under top-k dropout by 0.067 — not from any "
            "EXP-009D outcome"
        ),
        "E_ordering": "the paired per-date Rank-IC difference (DEDUP - FULL) has |mean| <= 0.005 AND |mean| + 1.96 x HAC SE "
                      "(Bartlett, 4 lags) <= 0.010",
        "E_economics": "under top-k dropout at 10 bp, |net Sharpe difference| <= 0.20 AND the annualised turnover ratio is within [0.9, 1.1]",
        "classification": {"EQUIVALENT": "E_ordering and E_economics",
                           "DIFFERENT": "otherwise (the duplicate is not demonstrably harmless and the 27-feature set stays)"},
        "consequence": "EQUIVALENT: later experiments may use the 26-feature set without a separate justification. "
                       "DIFFERENT: nothing changes. Either way EXP-006, EXP-009A, EXP-009B and EXP-009C keep the 27 features.",
        "descriptive": "the NOISE arm's own differences from FULL are reported beside DEDUP's so the reader can see whether DEDUP "
                       "moved more than a reseed does",
        "promotion": "NOT ASSESSED",
    },
    "inference": {"hac_lags": 4, "seed": 0},
    "trials": {"declared": 2, "note": "the DEDUP fit and the seed-noise reference", "prior_cumulative_evaluations": 164,
               "cumulative_evaluations": 166},
    "holdout": {"read": False},
}

METHOD_SOURCES = (
    "src/quant/backtest/rules.py", "src/quant/backtest/engine.py", "src/quant/backtest/ordering.py",
    "src/quant/validation/runner.py", "src/quant/study/exp009b.py", "src/quant/study/exp009d.py",
)


def definition_fingerprint(root: Path = Path(".")) -> str:
    return prereg.fingerprint(DEFINITION, METHOD_SOURCES, root)


def prereg_gate(root: Path = Path("."), *, fetch: bool = True) -> dict[str, Any]:
    return prereg.check(document=PREREG_DOC, expected_fingerprint=definition_fingerprint(root),
                        method_sources=METHOD_SOURCES, root=root, fetch=fetch)


def classify(ic_diff: dict[str, Any], econ: dict[str, Any]) -> dict[str, Any]:
    e_order = bool(abs(ic_diff["mean_difference"]) <= 0.005
                   and abs(ic_diff["mean_difference"]) + 1.96 * ic_diff["hac_se"] <= 0.010)
    e_econ = bool(abs(econ["net_sharpe_difference"]) <= 0.20 and 0.9 <= econ["turnover_ratio"] <= 1.1)
    return {"E_ordering": e_order, "E_economics": e_econ,
            "classification": "EQUIVALENT" if (e_order and e_econ) else "DIFFERENT", "promotion": "NOT ASSESSED"}


def _write(directory: Path, name: str, payload: Any) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


def run_study(root: Path = Path("."), *, output: Optional[Path] = None) -> dict[str, Any]:
    began = time.perf_counter()
    root = Path(root)
    output = output or (root / OUTPUT_DIR)
    gate = prereg_gate(root)

    start, end = exp009b.arm_firewall(root)
    frame, build = exp009b.load_frame(root)
    panel = frame[["date", "symbol", "dollar_volume", "fwd_ret_5", "fwd_ret_21", "in_universe"]]
    manifest: dict[str, Any] = {
        "experiment_id": EXPERIMENT_ID, "parent": PARENT_EXPERIMENT, "status": DEFINITION["status"], **gate,
        **exp009a._git_state(root),
        "dataset": {"dataset_version": build["dataset_version"], "content_hash": build["content_hash"]},
        "dependency_versions": dependency_versions(),
        "holdout": {"start": str(start), "end": str(end), "touched": False, "firewall": FIREWALL.status()},
    }
    universe_rows = frame[frame["in_universe"]]
    correlation = float(universe_rows[[DROPPED, KEPT]].corr().iloc[0, 1])
    checks = {
        "dataset_id": build["dataset_version"] == DEFINITION["data"]["dataset_id"],
        "returns_panel_hash": exp009a.panel_content_hash(panel) == DEFINITION["data"]["returns_panel_sha256"],
        "duplicate_is_exact": abs(correlation) >= 0.99999,
    }
    manifest["validity_checks"] = {**checks, "measured_correlation": correlation}
    if not all(checks.values()):
        manifest["decision"] = f"INVALID - {checks}"
        _write(output, "manifest.json", manifest)
        raise RuntimeError(manifest["decision"])

    plan = exp009b.recorded_plan(root)
    arms = {}
    for label, features, seed in (
        ("FULL", exp009b.FEATURES, 0),
        ("DEDUP", DEFINITION["data"]["features_dedup"], 0),
        ("NOISE", exp009b.FEATURES, 1),
    ):
        results, failures, _ = evaluate_specs(
            [ModelSpec(f"gb_{label}", "gradient_boosting", (), seed)], frame, plan,
            features=features, label=LABEL, step_sessions=5, workers=1)
        if failures or not results:
            manifest["decision"] = f"INVALID - {label} failed: {failures}"
            _write(output, "manifest.json", manifest)
            raise RuntimeError(manifest["decision"])
        arms[label] = results[0]

    reproduction = exp009b.reproduce_frozen(root, arms["FULL"].predictions)
    manifest["full_reproduces_frozen"] = reproduction
    if not reproduction["passed"]:
        manifest["decision"] = "INVALID - the FULL arm does not reproduce EXP-006"
        _write(output, "manifest.json", manifest)
        raise RuntimeError(manifest["decision"])

    fold_map = exp009a.fold_of_dates(arms["FULL"].predictions)
    cells = {label: exp009b.cell_report(res.predictions, res, panel, fold_map) for label, res in arms.items()}
    hac = exp009a.newey_west_mean_t(
        (cells["DEDUP"]["_ic_series"] - cells["FULL"]["_ic_series"]).dropna().to_numpy(), DEFINITION["inference"]["hac_lags"])
    net = {k: cells[k]["portfolios"]["C_topk_dropout_10"]["_periods"].set_index("date")["net_return"] for k in cells}
    common = net["FULL"].index.intersection(net["DEDUP"].index)
    econ = {
        "net_sharpe_difference": cells["DEDUP"]["portfolios"]["C_topk_dropout_10"]["metrics_at_10bp"]["net_sharpe"]
        - cells["FULL"]["portfolios"]["C_topk_dropout_10"]["metrics_at_10bp"]["net_sharpe"],
        "turnover_ratio": cells["DEDUP"]["portfolios"]["C_topk_dropout_10"]["metrics_at_10bp"]["annualised_turnover"]
        / cells["FULL"]["portfolios"]["C_topk_dropout_10"]["metrics_at_10bp"]["annualised_turnover"],
        "periods_compared": int(len(common)),
    }
    criteria = classify({"mean_difference": hac["mean"], "hac_se": hac["hac_se"]}, econ)
    noise_hac = exp009a.newey_west_mean_t(
        (cells["NOISE"]["_ic_series"] - cells["FULL"]["_ic_series"]).dropna().to_numpy(), DEFINITION["inference"]["hac_lags"])
    noise_econ = {
        "net_sharpe_difference": cells["NOISE"]["portfolios"]["C_topk_dropout_10"]["metrics_at_10bp"]["net_sharpe"]
        - cells["FULL"]["portfolios"]["C_topk_dropout_10"]["metrics_at_10bp"]["net_sharpe"],
        "turnover_ratio": cells["NOISE"]["portfolios"]["C_topk_dropout_10"]["metrics_at_10bp"]["annualised_turnover"]
        / cells["FULL"]["portfolios"]["C_topk_dropout_10"]["metrics_at_10bp"]["annualised_turnover"]}
    noise_reference = {"paired_ic": {"mean_difference": noise_hac["mean"], "hac_se": noise_hac["hac_se"]},
                       "economics": noise_econ, "would_be_classified": classify(
                           {"mean_difference": noise_hac["mean"], "hac_se": noise_hac["hac_se"]}, noise_econ)["classification"]}
    identical = float((arms["DEDUP"].predictions.set_index(["date", "symbol"])["prediction"]
                       - arms["FULL"].predictions.set_index(["date", "symbol"])["prediction"]).abs().max())
    decision = {"classification": criteria["classification"], "promotion": "NOT ASSESSED"}
    manifest.update({"compute": {"wall_seconds": round(time.perf_counter() - began, 1), "cpu_count": os.cpu_count(),
                                 "platform": platform.platform(), "python": platform.python_version()},
                     "definition_sha256": prereg.sha256_bytes(json.dumps(DEFINITION, sort_keys=True, default=str).encode()),
                     "decision": decision})
    output.mkdir(parents=True, exist_ok=True)
    _write(output, "definition.json", DEFINITION)
    for label, res in arms.items():
        FIREWALL.assert_clear(res.predictions, context=f"EXP-009D {label}")
        res.predictions.to_parquet(output / f"predictions_{label}.parquet", compression="zstd")
    _write(output, "metrics.json", {
        "definition": DEFINITION, "cells": exp009b._strip(cells),
        "paired_ic": {"mean_difference": hac["mean"], "hac_se": hac["hac_se"], "hac_t": hac["hac_t"],
                      "ci95": [hac["mean"] - 1.96 * hac["hac_se"], hac["mean"] + 1.96 * hac["hac_se"]]},
        "economics": econ, "noise_reference": noise_reference,
        "max_abs_prediction_difference_between_arms": identical,
        "criteria": criteria, "decision": decision,
        "rank_ic": {k: ic_summary(cells[k]["_ic_series"], horizon_sessions=21, step_sessions=5) for k in cells}})
    manifest["output_sha256"] = {p.name: prereg.sha256_file(p) for p in sorted(output.glob("*")) if p.name != "manifest.json"}
    _write(output, "manifest.json", manifest)
    return {"manifest": manifest, "criteria": criteria, "economics": econ, "decision": decision}
