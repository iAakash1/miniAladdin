"""EXP-011 data-value study command line."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from src.quant.study import exp011


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["fingerprint", "gate", "dry-run", "benchmark", "run", "summary"])
    parser.add_argument("--workers", type=int, default=4, help="parallel single-threaded fits (Mac: 4-6)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    if args.command == "fingerprint":
        print(exp011.definition_fingerprint())
    elif args.command == "gate":
        print(json.dumps(exp011.prereg_gate(), indent=2))
    elif args.command == "dry-run":
        print(json.dumps(exp011.dry_run(workers=args.workers), indent=2, default=str))
    elif args.command == "benchmark":
        print(json.dumps(exp011.benchmark(), indent=2))
    elif args.command == "summary":
        print(json.dumps(exp011.read_summary(), indent=2))
    else:
        result = exp011.run_study(workers=args.workers)
        print(json.dumps(result["analysis"]["classification"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
