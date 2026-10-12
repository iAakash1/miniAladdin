"""EXP-014 command line: an independent-firm test of the restating-amendment signal.

    python -m scripts.quant.exp014 fingerprint        # the value the preregistration must embed
    python -m scripts.quant.exp014 inputs             # write docs/EXP_014_INPUTS.json (sha256 of every registered input)
    python -m scripts.quant.exp014 counts             # label-free feasibility counts for the registration (reads no label)
    python -m scripts.quant.exp014 gate               # refuses unless the registration is committed and on the research branch
    python -m scripts.quant.exp014 rehearse --workers 4   # every code path on a shuffled label; writes outside the experiment directory, no result
    python -m scripts.quant.exp014 run --workers 6    # the registered study (gate first)
    python -m scripts.quant.exp014 infer --artifact experiments/EXP-014/model/M1.joblib --input rows.parquet --output scores.csv
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import pandas as pd

from src.quant.study import exp012, exp014, prereg


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["fingerprint", "inputs", "counts", "gate", "rehearse", "run", "infer"])
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--rehearsal-output", type=Path, default=Path("/tmp/exp014_rehearsal"))
    parser.add_argument("--skip-ml", action="store_true")
    parser.add_argument("--skip-economics", action="store_true")
    parser.add_argument("--draws", type=int, default=exp014.WEBB_DRAWS)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--input", type=Path, help="parquet or csv with every feature column the artifact lists")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    root = Path(".")
    if args.command == "fingerprint":
        print(exp014.definition_fingerprint(root))
    elif args.command == "inputs":
        hashes = {name: prereg.sha256_file(root / path) for name, path in exp014.input_paths().items()}
        (root / exp014.INPUTS_FILE).write_text(json.dumps({"experiment": exp014.EXPERIMENT_ID, "sha256": hashes}, indent=2, sort_keys=True) + "\n")
        print(json.dumps(hashes, indent=2))
    elif args.command == "counts":
        print(json.dumps(exp014.label_free_counts(root), indent=2, default=str))
    elif args.command == "gate":
        print(json.dumps(exp014.prereg_gate(root), indent=2))
    elif args.command == "rehearse":
        result = exp014.run_study(root, workers=args.workers, output=args.rehearsal_output, rehearsal=True, skip_ml=args.skip_ml, skip_economics=args.skip_economics,
                                  draws=min(args.draws, 1999), robust_draws=min(args.draws, 999))
        print(json.dumps(result["decision"], indent=2))
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
        result = exp014.run_study(root, workers=args.workers, skip_ml=args.skip_ml, skip_economics=args.skip_economics, draws=args.draws, robust_draws=min(args.draws, exp014.ROBUST_DRAWS))
        print(json.dumps(result["decision"], indent=2))
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)         # interpreter teardown after BLAS work can hang on this platform after everything has been written; see src/quant/study/exp014.py
