"""EXP-010A multi-seed noise-floor command line."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from src.quant.study import exp010a


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["fingerprint", "gate", "dry-run", "run", "summary"])
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    if args.command == "fingerprint":
        print(exp010a.definition_fingerprint())
    elif args.command == "gate":
        print(json.dumps(exp010a.prereg_gate(), indent=2))
    elif args.command == "dry-run":
        print(json.dumps(exp010a.dry_run(), indent=2))
    elif args.command == "summary":
        print(json.dumps(exp010a.read_summary(), indent=2))
    else:
        result = exp010a.run_study()
        print(json.dumps(result["metrics"]["across_seeds"]["primary_noise_distributions"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
