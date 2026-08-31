"""
Stage 5 of EXP-007 — turn a completed search into one defended decision.

The search ranks configurations by validation IC. IC is not a reason to trade
anything: it says the ordering has some information, not that the information
survives costs, turnover, factor exposure, or the size of the search that found
it. This script takes the finalists, refits them with predictions retained,
runs the same economics every earlier study ran, and applies the predeclared
gates.

The gates do not move here. `heavy.evaluate_gates` holds them, they mirror
`ModelRegistry.CANDIDATE_THRESHOLDS`, and one of them —
`survives_search_size` — is *stricter* the larger the search was. NO PRODUCTION
CANDIDATE is a legitimate output and the most likely one.

The holdout is not read. The plan reserves it, the firewall refuses its rows,
and the best available verdict is DEVELOPMENT CANDIDATE.

    python -m scripts.quant.select_candidate --experiment EXP-007
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date as Date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.quant.backtest.attribution import attribute_returns
from src.quant.datasets.store import RawStore
from src.quant.models.factory import default_specs
from src.quant.pit.dataset import DatasetBuilder
from src.quant.pit.universe import UniverseHistory
from src.quant.regime import classify_rules, performance_by_regime
from src.quant.study import search as space
from src.quant.study.experiment import get_experiment, git_commit, git_dirty
from src.quant.study.firewall import FIREWALL
from src.quant.study.heavy import (
    ConfigResult, OVERFIT_GAP, SearchContext, _walk_forward_plan,
    evaluate_gates, rank_candidates, selection_verdict,
)
from src.quant.study.run import _backtest, _pbo, _safe_read
from src.quant.validation.parallel import evaluate_specs
from src.quant.validation.significance import (
    deflated_sharpe_ratio, minimum_track_record_length,
)

#: Baselines refit alongside the finalists in every context they are judged in.
#: `beats_best_baseline` compares like with like or it compares nothing: a
#: finalist on arm C_base / fwd_rank_21 must beat the best baseline measured on
#: THOSE folds, with THAT label, not a number carried over from another study.
BASELINE_PREFIX = "baseline_"


def _finalists(results: list[ConfigResult], count: int) -> list[ConfigResult]:
    """Top configurations, one per (family, arm, target).

    Deduplicated because a search's top ten is frequently the same family at ten
    adjacent hyperparameters, and defending ten near-identical models is not a
    broader search — it is one model reported ten times.
    """
    seen: set[tuple[str, str, str]] = set()
    chosen: list[ConfigResult] = []
    for result in rank_candidates(results):
        if (result.train_ic_gap or 0.0) > OVERFIT_GAP:
            continue
        key = (result.family, result.arm, result.target)
        if key in seen:
            continue
        seen.add(key)
        chosen.append(result)
        if len(chosen) >= count:
            break
    return chosen


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.quant.select_candidate")
    parser.add_argument("--experiment", default="EXP-007")
    parser.add_argument("--root", default="data/research", type=Path)
    parser.add_argument("--out", default="experiments", type=Path)
    parser.add_argument("--artifacts", default="artifacts/experiments", type=Path)
    parser.add_argument("--finalists", type=int, default=6)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    search_path = args.out / args.experiment / "search.json"
    if not search_path.exists():
        print(f"error: {search_path} not found — run the search first.", file=sys.stderr)
        return 2
    artifact = json.loads(search_path.read_text(encoding="utf-8"))
    if not artifact.get("complete"):
        print(f"error: {search_path} records an INCOMPLETE search "
              f"({artifact['search']['configurations_failed']} failures).",
              file=sys.stderr)
        print("       Selecting from a partial search hides whatever the failures were.",
              file=sys.stderr)
        return 3

    began = time.perf_counter()
    definition = get_experiment(args.experiment, args.seed)
    results = [c for c in (ConfigResult.from_dict(r) for r in artifact["results"])
               if c is not None]
    finalists = _finalists(results, args.finalists)
    if not finalists:
        print("error: no non-overfit configuration in the search.", file=sys.stderr)
        return 4

    print("=" * 78)
    print(f"  SELECTION — {args.experiment}")
    print("=" * 78)
    for rank, f in enumerate(finalists, 1):
        print(f"  {rank}. {f.family:<24} {f.arm}/{f.target:<12} "
              f"IC {f.mean_ic:+.4f}  t {f.ic_t_stat:+.2f}  gap {f.train_ic_gap:+.4f}"
              if f.ic_t_stat is not None else
              f"  {rank}. {f.family:<24} {f.arm}/{f.target}  IC {f.mean_ic:+.4f}")

    # ── panel ────────────────────────────────────────────────────────────
    print("\n[1/4] rebuilding the panel")
    store = RawStore(str(args.root))
    universe = UniverseHistory.load(args.root / "universe")
    dataset = DatasetBuilder(store, universe).build(
        start=definition.start, end=definition.end or Date.today(),
        step_sessions=definition.step_sessions, workers=args.workers,
    )
    frame, manifest = dataset.frame, dataset.manifest
    if manifest.content_hash != artifact["dataset"]["content_hash"]:
        print(f"error: panel hash {manifest.content_hash} does not match the search's "
              f"{artifact['dataset']['content_hash']}.", file=sys.stderr)
        print("       The data moved under the search. Re-run the search rather than "
              "selecting across two panels.", file=sys.stderr)
        return 5
    print(f"      {manifest.rows:,} rows · hash {manifest.content_hash} — matches the search")

    cross = [c for c in manifest.features if c.endswith("_xs")]
    macro = [c for c in manifest.features if c.startswith(("rates_", "market_"))]
    context = SearchContext(frame=frame, manifest=manifest, calendar=dataset.calendar,
                            available_features=cross + macro)
    macro_frame = (frame[["date", *macro]].drop_duplicates("date")
                   .sort_values("date").reset_index(drop=True))
    regimes = classify_rules(macro_frame)
    factors = _safe_read(store, "french_factors_daily")

    # ── refit, with predictions ──────────────────────────────────────────
    #
    # The search discards predictions — several hundred prediction frames will
    # not fit in memory and are not needed to rank. The economics need them, so
    # the handful that survived are refit. Same specs, same folds, same seed:
    # the IC reproduces or the refit is telling us something is wrong.
    print(f"\n[2/4] refitting {len(finalists)} finalist(s) + baselines, keeping predictions")
    grouped: dict[tuple[str, str], list[ConfigResult]] = {}
    for f in finalists:
        grouped.setdefault((f.arm, f.target), []).append(f)

    economics: dict[str, dict[str, Any]] = {}
    baseline_ic: dict[tuple[str, str], float] = {}
    reproduction: list[dict[str, Any]] = []
    series: dict[str, pd.Series] = {}

    for (arm, target), members in grouped.items():
        features = context.features_for(arm)
        plan = _walk_forward_plan(context, target, definition)
        specs = [space.to_spec(f.family, f.params, name=f.config_id, seed=args.seed)
                 for f in members]
        specs += [s for s in default_specs(args.seed) if s.name.startswith(BASELINE_PREFIX)]
        print(f"      {arm}/{target}: {len(specs)} specs on {len(features)} features")
        outcomes, failures, _ = evaluate_specs(
            specs, frame, plan, features=features, label=target,
            step_sessions=definition.step_sessions, workers=args.workers,
        )
        for failure in failures:
            print(f"      FAILED {failure.get('model')}: "
                  f"{str(failure.get('error'))[:120]}")

        forward = f"fwd_ret_{definition.step_sessions}"
        returns_panel = (frame[["date", "symbol", "dollar_volume", forward]]
                         if forward in frame.columns else None)
        horizon = int(target.rsplit("_", 1)[-1]) if target.rsplit("_", 1)[-1].isdigit() else 21

        for outcome in outcomes:
            ic = outcome.pooled_ic.get("mean_ic")
            if outcome.model_id.startswith(BASELINE_PREFIX):
                if ic is not None:
                    key = (arm, target)
                    baseline_ic[key] = max(baseline_ic.get(key, -1e9), float(ic))
                continue

            recorded = next((m for m in members if m.config_id == outcome.model_id), None)
            if recorded is not None:
                delta = None if ic is None or recorded.mean_ic is None else ic - recorded.mean_ic
                reproduction.append({
                    "config_id": outcome.model_id,
                    "search_mean_ic": recorded.mean_ic,
                    "refit_mean_ic": ic,
                    "delta": delta,
                    "reproduces": delta is not None and abs(delta) < 1e-12,
                })

            entry: dict[str, Any] = {
                "config_id": outcome.model_id,
                "family": recorded.family if recorded else None,
                "params": recorded.params if recorded else {},
                "arm": arm, "target": target, "feature_count": len(features),
                "mean_ic": ic,
                "ic_t_stat": outcome.pooled_ic.get("t_stat"),
                "ic_ir": outcome.pooled_ic.get("ic_ir"),
                "train_mean_ic": outcome.stability("train_mean_ic").get("mean"),
                "train_ic_gap": recorded.train_ic_gap if recorded else None,
                "fold_ic_positive_rate": outcome.stability("spearman").get("fold_positive_rate"),
                "folds": len(outcome.folds),
            }

            if outcome.predictions is not None and returns_panel is not None:
                primary = _backtest(outcome.predictions, returns_panel, definition,
                                    definition.primary_half_spread_bps, forward)
                if primary is not None:
                    entry["backtest"] = primary.as_dict()
                    entry["gross_sharpe"] = primary.metrics.get("gross_sharpe")
                    entry["net_sharpe"] = primary.metrics.get("net_sharpe")
                    entry["annualised_turnover"] = primary.metrics.get("annualised_turnover")
                    series[outcome.model_id] = primary.net_returns
                    entry["cost_sensitivity"] = [
                        {"half_spread_bps": bps,
                         **{k: swept.metrics.get(k) for k in
                            ("gross_sharpe", "net_sharpe", "net_cagr",
                             "annualised_turnover", "cost_share_of_gross",
                             "net_max_drawdown", "hit_rate")}}
                        for bps in definition.cost_half_spreads_bps
                        if (swept := _backtest(outcome.predictions, returns_panel,
                                               definition, bps, forward))
                    ]
                    if factors is not None:
                        att = attribute_returns(
                            primary.net_returns, factors,
                            periods_per_year=252 / definition.step_sessions,
                            holding_periods=max(1, horizon // definition.step_sessions),
                        ).as_dict()
                        entry["factor_attribution"] = att
                        entry["alpha_t_stat"] = att.get("alpha_t_stat")
                entry["regime_performance"] = performance_by_regime(
                    outcome.predictions, regimes, label=target)
            economics[outcome.model_id] = entry

    # ── significance, at the size of the search that found it ────────────
    print("\n[3/4] significance against the full trial count")
    trials = artifact["search"]["multiple_testing"]["cumulative_trials"]
    expected_max_t = artifact["search"]["multiple_testing"]["expected_max_abs_t_under_null"]
    trial_sharpes = [float(s.mean() / s.std(ddof=1)) for s in series.values()
                     if len(s) > 2 and s.std(ddof=1) > 0]
    significance = {
        model_id: {
            "deflated_sharpe": deflated_sharpe_ratio(
                s.to_numpy(), trials=trials,
                periods_per_year=252 / definition.step_sessions,
                trial_sharpes=trial_sharpes,
            ).as_dict(),
            "minimum_track_record": minimum_track_record_length(s.to_numpy()),
        }
        for model_id, s in series.items()
    }
    pbo = _pbo(series)
    print(f"      {trials} cumulative trials · a winner must clear |t| > {expected_max_t}")
    print(f"      PBO {pbo.get('probability_of_backtest_overfitting')}")

    # ── gates ────────────────────────────────────────────────────────────
    print("\n[4/4] gates")
    ranked = sorted(
        economics.values(),
        key=lambda e: -(e.get("net_sharpe") if e.get("net_sharpe") is not None else -1e9),
    )
    best = ranked[0]
    gates = evaluate_gates(
        best,
        best_baseline_ic=baseline_ic.get((best["arm"], best["target"])),
        cumulative_trials=trials,
        expected_max_t=expected_max_t,
    )
    verdict = selection_verdict(gates)
    for gate in gates:
        mark = "PASS" if gate.passed else "FAIL"
        print(f"      {mark}  {gate.name:<22} {gate.observed}   required {gate.required}")
    print(f"\n  VERDICT: {verdict['status']}")

    payload = {
        "experiment": args.experiment,
        "fingerprint": definition.fingerprint(),
        "search_artifact": str(search_path),
        "search_fingerprint": artifact["fingerprint"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "git_dirty": git_dirty(),
        "dataset": artifact["dataset"],
        "finalists": [f.as_dict() for f in finalists],
        "refit_reproduction": reproduction,
        "economics": economics,
        "best_baseline_ic": {f"{a}/{t}": v for (a, t), v in baseline_ic.items()},
        "significance": significance,
        "probability_of_backtest_overfitting": pbo,
        "multiple_testing": artifact["search"]["multiple_testing"],
        "selected": {
            "config_id": best["config_id"],
            "family": best["family"],
            "params": best["params"],
            "arm": best["arm"],
            "target": best["target"],
            "ranked_by": "net_sharpe at the declared 10 bp half-spread",
        },
        "verdict": verdict,
        "holdout": {
            **artifact["holdout"],
            "touched": False,
            "note": ("Selection read validation folds only. Promotion to production "
                     "remains blocked until the holdout is spent under the contract."),
        },
        "firewall": FIREWALL.status(),
        "runtime_seconds": round(time.perf_counter() - began, 1),
    }
    destination = args.artifacts / args.experiment
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "final_selection.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\n  wrote {destination / 'final_selection.json'}")
    print("=" * 78)
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
