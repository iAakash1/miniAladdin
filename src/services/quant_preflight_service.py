"""
Read layer for the holdout preflight.

## Why this exists

`src/quant/audit/preflight.py` implements nine integrity gates that decide
whether the holdout may be opened — contract state, artifact presence, holdout
untouched, fold chronology, absence of random splits, registry cleanliness, git
cleanliness, regime balance, and a two-build contamination probe. It is the most
direct answer this product has to "can this research be trusted", and it was
reachable only by running a CLI.

That is the gap this closes. The checks were already written, already tested,
and already the authority the holdout runner defers to; nothing here computes a
new verdict.

## What is deliberately not run

The contamination probe rebuilds the panel twice and takes tens of minutes. It
is skipped here and **the response says so**, because a preflight without it is
a fast read, not the gate the holdout runner requires. The distinction is
carried in `valid_for_run`, which is always false from this surface.

Nothing on this path can open the holdout. `run_preflight` fits no model and
reads no holdout-dated row; the only entry point that can spend the holdout is
`python -m src.quant.study.holdout --run`, which is a deliberate human act.

## Layering

The study artifact is resolved *here* rather than inside the audit package.
`src/quant` must not import from `src/services` — the dependency runs one way —
so the service chooses the path and passes it in.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

#: Where completed experiments land. The legacy standalone report is a fallback.
EXPERIMENTS_ROOT = Path("experiments")
LEGACY_STUDY = Path("data/research/reports/study.json")

#: Studies a later audit invalidated. Mirrors `ml_service.VOID_EXPERIMENT_IDS`;
#: duplicated as a literal so this module does not import another service.
VOID_EXPERIMENT_IDS = frozenset({"EXP-002"})


def _newest_valid_study(root: Optional[Path] = None) -> Optional[tuple[str, Path]]:
    """The newest completed, non-void experiment artifact.

    The legacy `study.json` predates the as-of fix and carries no experiment id,
    so running the preflight against it would gate on a study the register
    already treats as void.
    """
    # Resolved at call time. A module-level constant captured in a signature is
    # bound at import and cannot be overridden by a deployment or a test — the
    # override is accepted and silently ignored, which is worse than not
    # offering one. This is the third instance of that bug in this codebase.
    root = Path(root) if root is not None else EXPERIMENTS_ROOT
    if not root.exists():
        return None
    candidates: list[tuple[str, str, Path]] = []
    for directory in sorted(root.iterdir(), reverse=True):
        artifact = directory / "metrics.json"
        if not artifact.is_file():
            continue
        try:
            payload = json.loads(artifact.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        experiment_id = (payload.get("experiment") or {}).get("experiment_id")
        if experiment_id in VOID_EXPERIMENT_IDS or not payload.get("labels"):
            continue
        candidates.append((str(payload.get("generated_at") or ""),
                           experiment_id or directory.name, artifact))
    if not candidates:
        return None
    _, experiment_id, artifact = max(candidates)
    return experiment_id, artifact


def preflight() -> dict[str, Any]:
    """Run the fast integrity gates and report them.

    Never opens the holdout, never fits a model, never writes.
    """
    from src.quant.audit.preflight import run_preflight

    resolved = _newest_valid_study()
    study_path = resolved[1] if resolved else LEGACY_STUDY
    experiment_id = resolved[0] if resolved else None

    if not study_path.exists():
        return {
            "available": False,
            "detail": (
                f"no study artifact at {study_path}. The preflight gates a study; "
                "without one there is nothing to gate."
            ),
        }

    try:
        report = run_preflight(study_path=study_path, run_contamination=False)
    except Exception as error:  # noqa: BLE001 — reported, never swallowed
        return {
            "available": False,
            "detail": f"preflight could not complete: {type(error).__name__}: {error}",
        }

    payload = report.as_dict()
    blocking = payload["blocking_failures"]
    advisories = payload["advisories"]

    return {
        "available": True,
        "experiment_id": experiment_id,
        "study_artifact": str(study_path),
        # `ready` from a fast preflight means "nothing cheap is blocking", which
        # is a weaker claim than the holdout runner's gate. Renamed on the way
        # out so the two cannot be confused by a reader or a caller.
        "fast_gates_clear": payload["ready"],
        "valid_for_run": False,
        "contamination_probe": {
            "run": False,
            "why": (
                "The two-build contamination probe rebuilds the panel twice and "
                "takes tens of minutes. It is the check that found the as-of join "
                "defect which voided EXP-002, so a preflight without it is a fast "
                "read rather than the gate the holdout runner requires."
            ),
            "command": "python -m src.quant.study.holdout --preflight",
        },
        "holdout_start": payload["holdout_start"],
        "holdout_end": payload["holdout_end"],
        "fingerprint": payload["fingerprint"],
        "checks": payload["checks"],
        "blocking_failures": blocking,
        "advisories": advisories,
        "summary": (
            f"{sum(1 for c in payload['checks'] if c['passed'])} of "
            f"{len(payload['checks'])} fast gates pass"
            + (f"; blocking: {', '.join(blocking)}" if blocking else "")
            + (f"; advisory: {', '.join(advisories)}" if advisories else "")
        ),
        "note": (
            "Clearing these gates does not open the holdout and does not promote "
            "anything. The holdout is spent only by an explicit human run under "
            "docs/HOLDOUT_CONTRACT.md."
        ),
    }
