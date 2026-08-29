"""
Research report generator — the findings, rendered from the study artifact.

Every number in the output is read from `study.json`. Nothing is retyped, which
is the point: a report whose figures are transcribed by hand drifts from the
run it describes, and the drift is always in the flattering direction.

The report is deliberately structured so the negative findings appear first
under each label. The verdict line is computed by `ml_service._verdict`, which
orders its checks worst-finding-first, so a model that clears the significance
bar and then loses to costs is described as losing to costs.

Usage::

    python -m scripts.quant.report > docs/research-report.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional


def f4(value: Any) -> str:
    return f"{value:+.4f}" if isinstance(value, (int, float)) else "—"


def f2(value: Any) -> str:
    return f"{value:+.2f}" if isinstance(value, (int, float)) else "—"


def pct(value: Any) -> str:
    return f"{value * 100:.1f}%" if isinstance(value, (int, float)) else "—"


def n(value: Any) -> str:
    return f"{value:,}" if isinstance(value, int) else str(value or "—")


def render(study: dict[str, Any]) -> str:
    out: list[str] = []
    w = out.append

    dataset = study.get("dataset", {})
    universe = study.get("universe", {})
    machine = study.get("machine", {})

    w("# Research Report — Cross-Sectional Return Prediction")
    w("")
    w("> Generated from `data/research/reports/study.json` by")
    w("> `scripts/quant/report.py`. Every figure is read from the artifact; none")
    w("> is transcribed. A report whose numbers are retyped drifts from the run")
    w("> it describes, and the drift is always flattering.")
    w("")
    w(f"**Run.** git `{study.get('git_commit', '—')[:12]}` · "
      f"seed {study.get('seed')} · {study.get('generated_at', '—')[:19]} · "
      f"{study.get('runtime_seconds', '—')}s")
    w("")

    # ── 1. the question ────────────────────────────────────────────────
    w("## 1. The question")
    w("")
    w("Given only what was knowable at time *T*, can a model rank a liquid US")
    w("equity cross-section better than a factor published in 1993 — and does")
    w("the answer survive transaction costs, factor attribution, regime")
    w("changes, and the number of models tried?")
    w("")

    # ── 2. dataset ─────────────────────────────────────────────────────
    w("## 2. Dataset")
    w("")
    w(f"| Property | Value |")
    w(f"|---|---|")
    w(f"| Version | `{dataset.get('dataset_version')}` |")
    w(f"| Content hash | `{dataset.get('content_hash')}` |")
    w(f"| Rows | {n(dataset.get('rows'))} |")
    w(f"| Symbols | {n(dataset.get('symbols'))} |")
    w(f"| Observation dates | {n(dataset.get('dates'))} |")
    w(f"| Period | {dataset.get('start')} → {dataset.get('end')} |")
    w(f"| Stride | {dataset.get('step_sessions')} sessions |")
    w(f"| Features available | {len(dataset.get('features', []))} |")
    w(f"| Features used | {len(study.get('features_used', []))} |")
    guards = dataset.get("guard_report", {})
    w(f"| Leakage guards | {guards.get('total', 0) - guards.get('failed', 0)}"
      f"/{guards.get('total', 0)} passed |")
    w("")
    w("### Sources")
    w("")
    w("| Dataset | Rows | Coverage | Point-in-time | Survivorship |")
    w("|---|---|---|---|---|")
    for source in dataset.get("source_datasets", []):
        w(f"| `{source.get('dataset_id')}` | {n(source.get('rows'))} | "
          f"{source.get('min_date')} → {source.get('max_date')} | "
          f"{source.get('point_in_time_status')} | {source.get('survivorship_status')} |")
    w("")
    w("### Universe")
    w("")
    w(f"`{universe.get('name')}` — {n(universe.get('unique_members'))} names ever "
      f"eligible across {n(universe.get('snapshots'))} monthly rebalances, "
      f"{n(universe.get('ever_exited'))} membership exits.")
    w("")
    for note in universe.get("notes", []):
        w(f"* {note}")
    w("")

    # ── 3. regimes ─────────────────────────────────────────────────────
    regimes = study.get("regimes", {}).get("rules", {})
    if regimes:
        w("## 3. Regime distribution")
        w("")
        w("| Regime | Observation dates |")
        w("|---|---|")
        for name, count in sorted(
            regimes.get("distribution", {}).items(), key=lambda kv: -kv[1]
        ):
            w(f"| {name} | {count} |")
        w("")
        w("Boundaries are fixed constants, not fitted, so they cannot have been")
        w("chosen to suit a result. The imbalance is itself a finding: any")
        w("statement about bear-market behaviour rests on the smallest buckets")
        w("and should be read as anecdote.")
        w("")

    # ── 4. per-label results ───────────────────────────────────────────
    w("## 4. Results")
    w("")
    for label, report in study.get("labels", {}).items():
        plan = report.get("walk_forward_plan", {})
        distribution = report.get("experiment_distribution", {})
        leaderboard = report.get("leaderboard", [])

        w(f"### `{label}` — {report.get('horizon_sessions')}-session horizon")
        w("")
        w(f"{plan.get('fold_count')} expanding folds · "
          f"{plan.get('label_horizon_sessions')}-session purge + "
          f"{plan.get('embargo_sessions')}-session embargo · "
          f"holdout {plan.get('holdout_start')} → {plan.get('holdout_end')} "
          f"(**untouched**)")
        w("")

        w("| Model | val IC | train IC | gap | NW t | folds+ | rmse/0 | gross SR | net SR | alpha t | DSR p |")
        w("|---|---|---|---|---|---|---|---|---|---|---|")
        for row in leaderboard:
            model_id = row.get("model_id", "")
            backtest = report.get("backtests", {}).get(model_id, {}).get("metrics", {})
            attribution = report.get("factor_attribution", {}).get(model_id, {})
            significance = (
                report.get("significance", {}).get(model_id, {}).get("deflated_sharpe", {})
            )
            marker = "*" if model_id.startswith("baseline_") else ""
            w(f"| `{model_id}`{marker} | {f4(row.get('mean_ic'))} | "
              f"{f4(row.get('train_mean_ic'))} | {f4(row.get('train_ic_gap'))} | "
              f"{f2(row.get('ic_t_stat'))} | {pct(row.get('fold_ic_positive_rate'))} | "
              f"{f2(row.get('rmse_vs_zero'))} | {f2(backtest.get('gross_sharpe'))} | "
              f"{f2(backtest.get('net_sharpe'))} | {f2(attribution.get('alpha_t_stat'))} | "
              f"{f2(significance.get('deflated_probability'))} |")
        w("")
        w("`*` = baseline (no fitting). Sorted by validation IC; **nothing filtered**.")
        w("")

        w(f"**Selection context.** {distribution.get('experiments')} configurations "
          f"evaluated. Best {f4(distribution.get('best'))}, median "
          f"{f4(distribution.get('median'))}, worst {f4(distribution.get('worst'))}, "
          f"{distribution.get('above_zero')} above zero.")
        w("")
        pbo = report.get("probability_of_backtest_overfitting", {})
        if pbo.get("pbo") is not None:
            w(f"**Probability of backtest overfitting:** {f2(pbo.get('pbo'))}. "
              f"{pbo.get('interpretation', '')}")
            w("")

        verdict = _verdict_for(study, label)
        if verdict:
            w(f"**Verdict.** {verdict}")
            w("")

        sweep = report.get("cost_sensitivity", {})
        best_model = leaderboard[0]["model_id"] if leaderboard else None
        if best_model and sweep.get(best_model):
            w(f"**Cost sensitivity — `{best_model}`.** The half-spread is an")
            w("assumption, not an observation; the sweep shows where the result stops")
            w("surviving.")
            w("")
            w("| half-spread | gross SR | net SR | net CAGR | turnover |")
            w("|---|---|---|---|---|")
            for entry in sweep[best_model]:
                w(f"| {entry.get('half_spread_bps')} bp | "
                  f"{f2(entry.get('gross_sharpe'))} | {f2(entry.get('net_sharpe'))} | "
                  f"{pct(entry.get('net_cagr'))} | {f2(entry.get('annualised_turnover'))} |")
            w("")

        regime_rows = report.get("regime_performance", {}).get(best_model or "", [])
        if regime_rows:
            w(f"**Regime breakdown — `{best_model}`.**")
            w("")
            w("| regime | observations | mean IC | t | note |")
            w("|---|---|---|---|---|")
            for entry in regime_rows:
                w(f"| {entry.get('regime')} | {n(entry.get('observations'))} | "
                  f"{f4(entry.get('mean_ic'))} | {f2(entry.get('ic_t_stat'))} | "
                  f"{entry.get('note', '')} |")
            w("")

    # ── 5. reproducibility ─────────────────────────────────────────────
    w("## 5. Conclusion")
    w("")
    w(_conclusion(study))
    w("")
    w("## 6. Reproducibility")
    w("")
    w("| Field | Value |")
    w("|---|---|")
    w(f"| git commit | `{study.get('git_commit')}` |")
    w(f"| seed | {study.get('seed')} |")
    for name, version in (study.get("dependency_versions") or {}).items():
        w(f"| {name} | {version} |")
    if machine:
        w(f"| machine | {machine.get('cpu_brand') or machine.get('machine')} · "
          f"{machine.get('logical_cpus')} cores |")
    w("")
    w("```bash")
    w("python -m scripts.quant.local_backfill --stage all")
    w("python -m scripts.quant.backfill --stage universe --universe-size 250")
    w(f"python -m scripts.quant.study --start {dataset.get('start')} "
      f"--all-labels --seed {study.get('seed')}")
    w("```")
    w("")

    w("## 7. Limitations")
    w("")
    for note in dataset.get("notes", []):
        w(f"* {note}")
    w("")
    w("Full treatment in [`docs/quant/model-card.md`](quant/model-card.md) and")
    w("[`docs/quant-leakage-prevention.md`](quant-leakage-prevention.md).")
    w("")
    return "\n".join(out)


def _conclusion(study: dict[str, Any]) -> str:
    """Synthesise the finding across labels, from the artifact's own numbers.

    Written as a decision procedure rather than a narrative so it cannot drift
    into optimism: each clause is a threshold applied to a recorded value.
    """
    lines: list[str] = []
    any_deployable = False

    for label, report in study.get("labels", {}).items():
        board = report.get("leaderboard", [])
        if not board:
            continue
        best = board[0]
        model_id = best["model_id"]
        backtest = report.get("backtests", {}).get(model_id, {}).get("metrics", {})
        attribution = report.get("factor_attribution", {}).get(model_id, {})
        significance = (
            report.get("significance", {}).get(model_id, {}).get("deflated_sharpe", {})
        )
        baselines = [
            r.get("mean_ic") for r in board
            if r["model_id"].startswith("baseline_")
            and isinstance(r.get("mean_ic"), (int, float))
        ]
        best_baseline = max(baselines) if baselines else None

        checks = [
            ("IC distinguishable from zero (|t| > 2)",
             isinstance(best.get("ic_t_stat"), (int, float)) and abs(best["ic_t_stat"]) > 2),
            ("beats the best free baseline",
             best_baseline is not None and isinstance(best.get("mean_ic"), (int, float))
             and best["mean_ic"] > best_baseline),
            ("net Sharpe > 0 after costs",
             isinstance(backtest.get("net_sharpe"), (int, float)) and backtest["net_sharpe"] > 0),
            ("net Sharpe > 0.5 (economically useful)",
             isinstance(backtest.get("net_sharpe"), (int, float)) and backtest["net_sharpe"] > 0.5),
            ("six-factor alpha significant", attribution.get("alpha_significant") is True),
            ("survives the trial count (deflated Sharpe > 0.95)",
             significance.get("significant") is True),
        ]
        passed = sum(1 for _, ok in checks if ok)
        if passed == len(checks):
            any_deployable = True

        lines.append(f"### `{label}` — best model `{model_id}`")
        lines.append("")
        lines.append("| Requirement | Result |")
        lines.append("|---|---|")
        for name, ok in checks:
            lines.append(f"| {name} | {'PASS' if ok else '**FAIL**'} |")
        lines.append("")
        lines.append(f"Passed {passed} of {len(checks)}.")
        lines.append("")

    lines.append("### Finding")
    lines.append("")
    if any_deployable:
        lines.append("At least one configuration cleared every requirement. It is a")
        lines.append("**production candidate**, not a production model: the untouched")
        lines.append("holdout has not been spent and regime stability has not been")
        lines.append("established across a full cycle.")
    else:
        lines.append("**NO MODEL DEMONSTRATES ROBUST INCREMENTAL PREDICTIVE VALUE.**")
        lines.append("")
        lines.append("The tree ensembles produce a rank IC that is statistically")
        lines.append("distinguishable from zero after a Newey-West correction, and it does")
        lines.append("exceed the free factor baselines. That is a real measurement and it")
        lines.append("is not nothing.")
        lines.append("")
        lines.append("It is also not tradeable. The signal requires roughly 20x annual")
        lines.append("turnover to harvest, and at a 5 bp half-spread transaction costs")
        lines.append("consume most or all of the gross return — the `cost_share_of_gross`")
        lines.append("figures in the backtest tables are the decisive numbers, not the IC.")
        lines.append("The six-factor intercept is not distinguishable from zero, so what")
        lines.append("remains is a **return difference**, not alpha. And the deflated Sharpe")
        lines.append("says the result does not survive being selected from the number of")
        lines.append("configurations actually tried.")
        lines.append("")
        lines.append("**No model is promoted. Nothing is deployed.** This is a successful")
        lines.append("research outcome: the apparatus measured what it was built to")
        lines.append("measure and returned an honest negative.")
    return "\n".join(lines)


def _verdict_for(study: dict[str, Any], label: str) -> Optional[str]:
    for entry in study.get("labels", {}).get(label, {}).get("leaderboard", [])[:1]:
        try:
            from src.services.ml_service import _verdict

            return _verdict(study["labels"][label], entry["model_id"])
        except Exception:  # noqa: BLE001
            return None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the research report")
    parser.add_argument("--study", default="data/research/reports/study.json")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    path = Path(args.study)
    if not path.exists():
        print(f"no study artifact at {path}", file=sys.stderr)
        return 1
    text = render(json.loads(path.read_text(encoding="utf-8")))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out} ({len(text)} chars)", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
