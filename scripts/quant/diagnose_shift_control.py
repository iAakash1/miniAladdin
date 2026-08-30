"""
Diagnostic: is the shifted-target control detecting leakage, or persistence?

The `shifted_forward` control replaces each row's target with one from four
rebalance periods (~20 sessions) further ahead and expects predictability to
collapse. It did not: the gradient-boosting probe scored IC +0.0271 on the
displaced target, close to its score on the real one.

Two explanations, with opposite implications:

**Leakage.** The features carry information about the future, so displacing the
target does not help. This would invalidate the whole study.

**Persistence.** The features are slow-moving characteristics — 12-1 momentum,
63-day volatility, liquidity — and those are documented to predict returns over
horizons of months, not days. A target 20 sessions further out is still inside
the window such a signal acts over, so a positive IC is exactly what theory
predicts.

The discriminator is `baseline_momentum`: a pure passthrough of
`mom_252_21_xs`, computed from a backward rolling window with no fitting, no
join and no as-of merge. **It cannot leak.** If it scores comparably on the
shifted target, the effect is persistence and the control's premise is wrong
for this signal class. If it collapses while the learned model does not, the
learned model is reading something the baseline is not, and that is the
leakage signature.

    python -m scripts.quant.diagnose_shift_control
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date as Date
from pathlib import Path

import pandas as pd

from src.quant.datasets.store import RawStore
from src.quant.models.factory import ModelSpec
from src.quant.pit.dataset import DatasetBuilder
from src.quant.pit.universe import UniverseHistory
from src.quant.study.experiment import exp_004
from src.quant.validation.controls import shift_target_forward, shuffle_within_date
from src.quant.validation.parallel import evaluate_specs
from src.quant.validation.walkforward import build_plan

logging.basicConfig(level=logging.WARNING, format="%(levelname)-7s %(message)s", stream=sys.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose the shifted-target control")
    parser.add_argument("--root", default="data/research")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--shift", type=int, default=4)
    parser.add_argument("--out", default="experiments/EXP-004/shift_diagnostic.json")
    args = parser.parse_args()

    definition = exp_004()
    store = RawStore(args.root)
    universe = UniverseHistory.load(Path(args.root) / "universe")

    print("building dataset ...", flush=True)
    dataset = DatasetBuilder(store, universe).build(
        start=definition.start, end=Date.today(),
        step_sessions=definition.step_sessions, workers=args.workers,
    )
    frame = dataset.frame
    features = [n for n in dataset.manifest.features
                if n.endswith("_xs") or n.startswith(("rates_", "market_"))]
    target = definition.primary_target

    plan = build_plan(
        dataset.calendar, start=definition.start, end=max(frame["date"]),
        label_horizon_sessions=21,
        validation_sessions=definition.validation_sessions,
        min_train_sessions=definition.min_train_sessions,
        embargo_sessions=definition.embargo_sessions,
        holdout_sessions=definition.holdout_sessions,
    )

    # A passthrough of a backward-rolling price feature: provably leak-free.
    momentum = ModelSpec("baseline_momentum", "passthrough",
                         (("feature", "mom_252_21_xs"),), definition.seed)
    low_vol = ModelSpec("baseline_low_volatility", "passthrough",
                        (("feature", "vol_63_xs"), ("sign", -1.0)), definition.seed)
    probes = [momentum, low_vol]

    variants = {
        "real_target": frame,
        f"shifted_forward_{args.shift}": shift_target_forward(frame, target, periods=args.shift),
        "shuffled_within_date": shuffle_within_date(frame, target, seed=definition.seed),
    }

    rows = []
    for variant, data in variants.items():
        print(f"evaluating {variant} ...", flush=True)
        results, failures, _ = evaluate_specs(
            probes, data, plan, features=features, label=target,
            step_sessions=definition.step_sessions, workers=min(args.workers, 2),
        )
        for result in results:
            rows.append({
                "variant": variant,
                "model": result.model_id,
                "mean_ic": result.pooled_ic.get("mean_ic"),
                "t_stat": result.pooled_ic.get("t_stat"),
                "observations": result.pooled_ic.get("observations"),
            })
        for failure in failures:
            rows.append({"variant": variant, "model": failure["model"], "error": failure["error"][:200]})

    table = pd.DataFrame(rows)
    print("\n" + "=" * 74)
    print("SHIFTED-TARGET DIAGNOSTIC — leak-free passthrough baselines")
    print("=" * 74)
    print(f"{'variant':<26}{'model':<28}{'IC':>10}{'t':>8}")
    for row in rows:
        if "error" in row:
            print(f"{row['variant']:<26}{row['model']:<28}  FAILED")
            continue
        ic = row["mean_ic"]
        t = row["t_stat"]
        print(f"{row['variant']:<26}{row['model']:<28}"
              f"{(f'{ic:+.4f}' if isinstance(ic, float) else 'n/a'):>10}"
              f"{(f'{t:+.2f}' if isinstance(t, float) else 'n/a'):>8}")
    print("=" * 74)

    real = {r["model"]: r.get("mean_ic") for r in rows if r["variant"] == "real_target"}
    shifted = {r["model"]: r.get("mean_ic")
               for r in rows if r["variant"].startswith("shifted_forward")}
    verdict_lines = []
    for model, value in shifted.items():
        base = real.get(model)
        if isinstance(value, float) and isinstance(base, float):
            retained = value / base if abs(base) > 1e-9 else float("nan")
            verdict_lines.append(
                f"{model}: retains {retained:.0%} of its real-target IC on a target "
                f"displaced {args.shift} periods"
            )
    print("\n".join(verdict_lines))
    print(
        "\nA leak-free passthrough retaining most of its IC on the displaced target "
        "means the shifted-target control measures HORIZON PERSISTENCE, not leakage: "
        "these are slow-moving characteristics documented to act over months.\n"
        "If instead the baselines collapse while the learned model does not, the "
        "learned model is reading something they cannot, and that IS the leakage "
        "signature."
    )

    target_path = Path(args.out)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps({
        "shift_periods": args.shift, "target": target,
        "rows": rows, "verdict_lines": verdict_lines,
    }, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {target_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
