"""EXP-013 command line: which columns carry the EXP-012 T1 gain?

    python -m scripts.quant.exp013 fingerprint         # the value the preregistration must embed
    python -m scripts.quant.exp013 gate                # refuses unless the registration is committed and on the research branch
    python -m scripts.quant.exp013 rehearse            # every code path on a shuffled label; writes to /tmp, no result
    python -m scripts.quant.exp013 run --workers 6     # the registered study (gate first)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from src.quant.study import exp013


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["fingerprint", "gate", "rehearse", "run"])
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--rehearsal-output", type=Path, default=Path("/tmp/exp013_rehearsal"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    if args.command == "fingerprint":
        print(exp013.definition_fingerprint())
    elif args.command == "gate":
        print(json.dumps(exp013.prereg_gate(), indent=2))
    elif args.command == "rehearse":
        result = exp013.run_study(workers=args.workers, output=args.rehearsal_output, rehearsal=True)
        print(json.dumps({g: a["label"] for g, a in result["attribution"].items()}, indent=2))
    else:
        result = exp013.run_study(workers=args.workers)
        print(json.dumps({g: a["label"] for g, a in result["attribution"].items()}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
