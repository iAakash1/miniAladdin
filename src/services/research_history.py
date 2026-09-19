"""The research history, told honestly: what each study asked, what it found, and what it did not.

Negative and inconclusive results are first-class rows.  Nothing here promotes anything: every row carries
`promotion` and `holdout_touched`, and a row that has not been run says so.  Facts that a manifest records
(holdout state, classification) are read from `experiments/`; the prose is a fixed, reviewed summary so the
API cannot drift from the documents (`tests/test_research_history.py` checks both).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_ROOT = Path("experiments")

# status: COMPLETE | PREREGISTERED_NOT_RUN | PREPARED_NOT_RUN
HISTORY: list[dict[str, Any]] = [
    {"id": "EXP-006", "status": "COMPLETE", "result": "NEGATIVE",
     "title": "Model tournament on the frozen price/liquidity/macro dataset",
     "summary": "Weak ordering information (mean Rank IC about 0.03) and roughly 20x annualised turnover meant net economics were negative. Recorded as a failure, not a candidate.",
     "docs": ["docs/EXP_009_RESULTS.md"]},
    {"id": "EXP-007", "status": "COMPLETE", "result": "NO_CANDIDATE",
     "title": "Quant search lab", "summary": "Completed and did not produce a candidate.", "docs": []},
    {"id": "EXP-008", "status": "PREREGISTERED_NOT_RUN", "result": "NOT_RUN",
     "title": "Preregistered; not run", "summary": "Registered but not executed. It is not to be modified or run.", "docs": []},
    {"id": "EXP-009A", "status": "COMPLETE", "result": "COST_EFFECT_ONLY",
     "title": "Turnover-aware portfolio rules", "summary": "Top-k dropout (10%) cut turnover about 66% and lifted net Sharpe from about -0.10 to +0.39; the gross gain was not significant and one fold dominated. A cost effect, not new signal.",
     "docs": ["docs/EXP_009_RESULTS.md", "docs/EXP_009_FINAL_ANALYSIS.md"]},
    {"id": "EXP-009B", "status": "COMPLETE", "result": "NO_ORDERING_GAIN",
     "title": "Ranking objectives (LambdaMART / pairwise) against a matched L2 control", "summary": "No ordering gain.", "docs": ["docs/EXP_009_RESULTS.md"]},
    {"id": "EXP-009C", "status": "COMPLETE", "result": "ANALYST_NO_RELIABLE_VALUE",
     "title": "Point-in-time analyst consensus features", "summary": "No reliable value from eight PIT analyst features.", "docs": ["docs/EXP_009_RESULTS.md"]},
    {"id": "EXP-009D", "status": "COMPLETE", "result": "EQUIVALENT",
     "title": "Removing a duplicated feature axis", "summary": "Equivalent; the deduplicated 26-feature set became the frozen baseline.", "docs": ["docs/EXP_009_RESULTS.md"]},
    {"id": "EXP-010A", "status": "COMPLETE", "result": "NOISE_FLOOR",
     "title": "Ten-seed noise floor", "summary": "Rank IC seed SD 0.00158 (p95-p05 0.00416); net Sharpe seed SD 0.0817 (p95-p05 0.219). The scale every later effect is read against.",
     "docs": ["docs/EXP_010A_RESULTS.md"]},
    {"id": "EXP-010B", "status": "COMPLETE", "result": "ECONOMICALLY_IMPROVED",
     "title": "Horizon-aligned (21-session) rebalance cadence",
     "summary": "Turnover fell about two-thirds and validation-period net Sharpe rose in all ten seeds; fold heterogeneity exists (three folds worse). Validation evidence only. Not perfectly blind: one B1 seed-0 prototype result was seen before the interpretation thresholds were registered.",
     "caveat": "one seed-0 prototype exposure disclosed in the preregistration; no claim of profitability", "docs": ["docs/EXP_010B_RESULTS.md", "docs/EXP_010B_PREREGISTRATION.md"]},
    {"id": "EXP-011", "status": "PREPARED_NOT_RUN", "result": "NOT_RUN",
     "title": "Does richer point-in-time company information improve ordering?",
     "summary": "Preregistered 2x2 (baseline 26 vs rich PIT 76 features; Ridge vs gradient boosting). Prepared and pushed; not run. No result exists.",
     "docs": ["docs/EXP_011_PREREGISTRATION.md"]},
]


def _manifest(root: Path, experiment_id: str) -> dict[str, Any] | None:
    path = Path(root) / experiment_id / "manifest.json"
    try:
        return json.loads(path.read_text()) if path.exists() else None
    except (OSError, ValueError):
        return None


def research_history(root: Path | str = DEFAULT_ROOT) -> dict[str, Any]:
    rows = []
    for entry in HISTORY:
        row = {**entry, "promotion": "NOT_ASSESSED", "promoted": False, "negative_or_inconclusive": entry["result"] not in ("ECONOMICALLY_IMPROVED", "NOISE_FLOOR", "NOT_RUN")}
        manifest = _manifest(Path(root), entry["id"])
        if entry["status"] == "COMPLETE":
            holdout = (manifest or {}).get("holdout", {}).get("touched")
            row["holdout_touched"] = holdout if holdout is not None else False
            row["holdout_recorded_in_manifest"] = manifest is not None and "holdout" in (manifest or {})
            recorded = (manifest or {}).get("classification")
            if isinstance(recorded, str):
                row["recorded_classification"] = recorded
        else:
            row["holdout_touched"] = False
            row["holdout_recorded_in_manifest"] = False
        rows.append(row)
    return {"status": "ok", "experiments": rows, "total": len(rows),
            "holdout": {"window": "2025-08-26 to 2026-08-28", "state": "SEALED", "note": "no experiment has read it"},
            "promoted_models": 0}
