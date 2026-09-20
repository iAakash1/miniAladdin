"""MODEL-LAB-001: inspect, smoke-test, or resume the declared CPU campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.quant.model_lab.registry import TrialRegistry
from src.quant.model_lab.report import build_summary, write_summary
from src.quant.model_lab.runner import run_family
from src.quant.model_lab.search_space import families


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    sub.add_parser("status")
    aggregate = sub.add_parser("aggregate")
    aggregate.add_argument("--method-commit", required=True)
    run = sub.add_parser("run")
    run.add_argument("--stage", choices=("smoke", "screening"), default="smoke")
    run.add_argument("--families", nargs="+", default=["ridge", "elastic_net", "extra_trees", "hist_gradient_boosting"])
    run.add_argument("--workers", type=int, default=2, help="reserved for family-level orchestration; fits remain single-threaded")
    args = parser.parse_args()

    registry = TrialRegistry()
    if args.command == "plan":
        print(json.dumps({"campaign_id": "MODEL-LAB-001", "families": families()}, indent=2))
        return 0
    if args.command == "status":
        print(json.dumps(build_summary(registry), indent=2))
        return 0
    if args.command == "aggregate":
        from src.quant.model_lab.aggregate import write_campaign_report

        path = write_campaign_report(
            registry, method_commit=args.method_commit, root=Path("."),
        )
        print(json.dumps({"campaign_report": str(path)}, indent=2))
        return 0

    outer_folds = [0] if args.stage == "smoke" else range(8)
    max_configs = 2 if args.stage == "smoke" else None
    for model_name in args.families:
        print(f"MODEL-LAB-001 {args.stage}: {model_name}", flush=True)
        run_family(
            model_name, registry=registry, root=Path("."),
            outer_folds=outer_folds, max_configs=max_configs,
            # Smoke proves data, preprocessing and inner-selection mechanics.
            # It must not consume an outer evaluation before the complete
            # declared search space is available.
            evaluate_outer=args.stage != "smoke",
        )
    path = write_summary(registry)
    print(json.dumps({"summary": str(path), **registry.summary()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
