"""
Holdout runner — single-use, pre-registered, and refusing by default.

    python -m src.quant.study.holdout --preflight
    python -m src.quant.study.holdout --run --confirm-preregistered

`--preflight` runs every integrity gate and reports. `--run` refuses unless:

1. preflight passes with no blocking failure;
2. `--confirm-preregistered` is passed explicitly;
3. `docs/HOLDOUT_CONTRACT.md` exists and names a primary candidate;
4. the fingerprint computed now matches the one the contract was written
   against — if the dataset, features, seed, contract or commit moved since,
   the experiment on the table is not the one that was pre-registered;
5. no previous receipt exists. The holdout is spent once.

The refusal is the feature. Everything expensive about a holdout happens before
it is opened, because afterwards the result cannot be un-known and every later
decision is conditioned on it whether anyone intends that or not.

**Nothing in this module trains a model on holdout data as part of `--preflight`.**
Preflight builds the point-in-time dataset twice to compare pre-holdout rows,
which touches holdout *inputs* but produces no holdout metric and fits nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.quant.audit.preflight import PreflightReport, run_preflight

#: Written on execution. Its existence means the holdout has been spent.
RECEIPT_PATH = Path("data/research/holdout/RECEIPT.json")


@dataclass
class HoldoutRefusal(RuntimeError):
    """Raised when the holdout may not be opened. Carries the reasons."""

    reasons: list[str]

    def __str__(self) -> str:
        return "holdout refused:\n  - " + "\n  - ".join(self.reasons)


def _receipt_exists() -> bool:
    return RECEIPT_PATH.exists()


def guard(report: PreflightReport, *, confirmed: bool, force_reason: str = "") -> None:
    """Every reason the holdout may not proceed, collected before raising."""
    reasons: list[str] = []

    if _receipt_exists():
        try:
            spent = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
            when = spent.get("executed_at", "unknown")
        except Exception:  # noqa: BLE001
            when = "unknown"
        reasons.append(
            f"the holdout has already been spent (receipt at {RECEIPT_PATH}, {when}). "
            "A second run would be evaluated on data whose outcome is known, which "
            "is not a holdout. Delete the receipt only to re-run a genuinely new "
            "experiment, and record why in the research ledger."
        )

    if not confirmed:
        reasons.append(
            "--confirm-preregistered was not passed. The flag exists so that "
            "opening the holdout is a deliberate act with a name on it."
        )

    for check in report.blocking_failures:
        reasons.append(f"preflight [{check.name}]: {check.detail}")

    if reasons and not force_reason:
        raise HoldoutRefusal(reasons)
    if reasons and force_reason:
        # There is no --force. This branch exists only so the shape of an
        # override is visible and obviously absent.
        raise HoldoutRefusal(reasons + ["overrides are not implemented by design"])


def write_receipt(report: PreflightReport, contract_path: Path, extra: dict[str, Any]) -> Path:
    """Persist what was frozen, before any holdout metric is computed."""
    RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "fingerprint": report.fingerprint,
        "holdout_start": report.holdout_start,
        "holdout_end": report.holdout_end,
        "contract_path": str(contract_path),
        "preflight": report.as_dict(),
        **extra,
    }
    RECEIPT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return RECEIPT_PATH


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Holdout preflight and execution")
    parser.add_argument("--preflight", action="store_true", help="run every gate and report")
    parser.add_argument("--run", action="store_true", help="execute the holdout (gated)")
    parser.add_argument("--confirm-preregistered", action="store_true")
    parser.add_argument("--contract", default="docs/HOLDOUT_CONTRACT.md")
    parser.add_argument("--study", default="data/research/reports/study.json")
    parser.add_argument("--root", default="data/research")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument(
        "--skip-contamination", action="store_true",
        help="skip the two-build contamination probe (fast preflight; NOT valid for --run)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if not args.preflight and not args.run:
        parser.error("pass --preflight or --run")
    if args.run and args.skip_contamination:
        parser.error("--skip-contamination cannot be combined with --run")

    report = run_preflight(
        contract_path=Path(args.contract),
        study_path=Path(args.study),
        store_root=args.root,
        run_contamination=not args.skip_contamination,
        workers=args.workers,
    )

    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print("\nHOLDOUT PREFLIGHT")
        print("=" * 72)
        print(f"holdout: {report.holdout_start} -> {report.holdout_end}")
        print(f"fingerprint: {report.fingerprint}")
        print("-" * 72)
        for check in report.checks:
            mark = "PASS" if check.passed else ("FAIL" if check.blocking else "WARN")
            scope = "blocking" if check.blocking else "advisory"
            print(f"  [{mark}] {check.name:<36} ({scope})")
            print(f"         {check.detail}")
        print("-" * 72)
        print(f"READY: {report.ready}")
        if report.advisories:
            print(f"advisories (non-blocking): {[c.name for c in report.advisories]}")
        if report.blocking_failures:
            print(f"BLOCKING: {[c.name for c in report.blocking_failures]}")
        print(f"holdout already spent: {_receipt_exists()}")
        print("=" * 72 + "\n")

    if not args.run:
        return 0 if report.ready else 1

    try:
        guard(report, confirmed=args.confirm_preregistered)
    except HoldoutRefusal as refusal:
        print(str(refusal), file=sys.stderr)
        return 2

    print(
        "Preflight passed and pre-registration confirmed.\n"
        "Holdout EXECUTION is intentionally not implemented in this revision: the "
        "pre-holdout audit found and fixed an as-of join defect that invalidated "
        "the prior validation results, so there is currently no valid candidate to "
        "pre-register. See docs/PRE_HOLDOUT_AUDIT.md.",
        file=sys.stderr,
    )
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
