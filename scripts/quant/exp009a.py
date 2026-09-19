"""
EXP-009A — command line.

    python -m scripts.quant.exp009a fingerprint   # print the definition fingerprint
    python -m scripts.quant.exp009a diagnose      # turnover forensics on the frozen baseline
    python -m scripts.quant.exp009a gate          # check the preregistration is pushed
    python -m scripts.quant.exp009a run           # execute (refused without a pushed prereg)

`diagnose` evaluates no treatment and reads no forward return in its
decomposition. `run` calls the preregistration gate first and does nothing
else if it fails.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from src.quant.study import exp009a


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["fingerprint", "diagnose", "gate", "run"])
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    if args.command == "fingerprint":
        print(exp009a.definition_fingerprint())
        return 0
    if args.command == "gate":
        print(json.dumps(exp009a.prereg_gate(), indent=2))
        return 0
    if args.command == "diagnose":
        result = exp009a.run_diagnostics()
        print(json.dumps({k: result[k] for k in (
            "engine_turnover", "independent_turnover", "independent_vs_engine_relative_difference", "baseline_reproduction",
            "breakeven", "decomposition")}, indent=2, default=str))
        return 0
    result = exp009a.run_study()
    print(json.dumps(result["metrics"]["decision"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
