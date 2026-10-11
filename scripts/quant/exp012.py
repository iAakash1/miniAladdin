"""EXP-012 command line: disclosure-process reliability and the value of company information.

    python -m scripts.quant.exp012 fingerprint        # the value the preregistration must embed
    python -m scripts.quant.exp012 gate               # refuses unless the registration is committed and on the research branch
    python -m scripts.quant.exp012 dry-run            # load, build and fit three cheap arms; no result is produced
    python -m scripts.quant.exp012 rehearse --workers 4  # every code path on a shuffled label; writes to /tmp, no result
    python -m scripts.quant.exp012 run --workers 6    # the registered study (gate first)
    python -m scripts.quant.exp012 infer --artifact experiments/EXP-012/model/A5.joblib --input rows.parquet --output scores.csv
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

from src.quant.study import exp012


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["fingerprint", "gate", "dry-run", "rehearse", "run", "infer"])
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--rehearsal-output", type=Path, default=Path("/tmp/exp012_rehearsal"))
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--input", type=Path, help="parquet or csv with every feature column the artifact lists")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    if args.command == "fingerprint":
        print(exp012.definition_fingerprint())
    elif args.command == "gate":
        print(json.dumps(exp012.prereg_gate(), indent=2))
    elif args.command == "dry-run":
        print(json.dumps(exp012.dry_run(), indent=2, default=str))
    elif args.command == "rehearse":
        result = exp012.run_study(workers=args.workers, output=args.rehearsal_output, rehearsal=True)
        print(json.dumps(result["verdicts"], indent=2))
    elif args.command == "infer":
        if not (args.artifact and args.input and args.output):
            parser.error("infer needs --artifact, --input and --output")
        bundle = exp012.load_artifact(args.artifact)
        frame = pd.read_parquet(args.input) if args.input.suffix == ".parquet" else pd.read_csv(args.input)
        scores = exp012.predict_with_artifact(bundle, frame)
        out = frame[[c for c in ("date", "symbol") if c in frame.columns]].assign(score=scores.to_numpy())
        out.to_csv(args.output, index=False)
        print(f"wrote {len(out)} scores to {args.output} ({bundle['arm']}, trained through {bundle['trained_through']}, {bundle['status']})")
    else:
        result = exp012.run_study(workers=args.workers)
        print(json.dumps(result["verdicts"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
