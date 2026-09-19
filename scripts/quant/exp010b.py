"""EXP-010B horizon / rebalance-cadence command line."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from src.quant.study import exp010b


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["fingerprint", "gate", "dry-run", "run", "summary"])
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    if args.command == "fingerprint":
        print(exp010b.definition_fingerprint())
    elif args.command == "gate":
        print(json.dumps(exp010b.prereg_gate(), indent=2))
    elif args.command == "dry-run":
        result = exp010b.dry_run()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result["all_checks_passed"] else 1
    elif args.command == "summary":
        print(json.dumps(exp010b.read_summary(), indent=2))
    else:
        result = exp010b.run_study()
        print(json.dumps({"classification": result["classification"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
