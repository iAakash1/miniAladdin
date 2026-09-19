"""
EXP-009B — command line.

    python -m scripts.quant.exp009b fingerprint   # the definition fingerprint
    python -m scripts.quant.exp009b gate          # is the preregistration pushed?
    python -m scripts.quant.exp009b run           # execute (refused without a pushed prereg)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from src.quant.study import exp009b


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["fingerprint", "gate", "run"])
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    if args.command == "fingerprint":
        print(exp009b.definition_fingerprint())
    elif args.command == "gate":
        print(json.dumps(exp009b.prereg_gate(), indent=2))
    else:
        out = exp009b.run_study(workers=args.workers)
        print(json.dumps(out["decision"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
