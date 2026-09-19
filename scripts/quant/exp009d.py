"""EXP-009D — command line. `run` is refused without a pushed preregistration."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from src.quant.study import exp009d


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["fingerprint", "gate", "run"])
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    if args.command == "fingerprint":
        print(exp009d.definition_fingerprint())
    elif args.command == "gate":
        print(json.dumps(exp009d.prereg_gate(), indent=2))
    else:
        print(json.dumps(exp009d.run_study()["decision"], indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
