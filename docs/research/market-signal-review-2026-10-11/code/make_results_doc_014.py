#!/usr/bin/env python3
"""Write docs/EXP_014_RESULTS.md from experiments/EXP-014 (results.json, ml_*.csv, economics.csv, manifest.json), so the document cannot disagree with the numbers.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/make_results_doc_014.py [--source experiments/EXP-014]

The narrative sentences are deliberately limited to what the decision rule permits (`DEFINITION["decision"]`); everything else is a table.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from src.quant.study import exp014  # noqa: E402

PERMITTED = {
    "SURVIVES": "In an independent sample the association survived the registered robustness checks. This is not evidence of investment value, and the interpretation label below says whether it looks like news or like a marker.",
    "FRAGILE": "In an independent sample the association is statistically present but failed at least one registered robustness check; it is not established.",
    "NOT_REPLICATED": "In an independent sample the association was not reproduced at the registered level of evidence.",
    "INCONCLUSIVE": "The independent sample has too few treated companies to conclude anything about the hypothesis.",
}


def fmt(x, nd=4):
    return "n/a" if x is None or (isinstance(x, float) and x != x) else f"{x:.{nd}f}"


def reg_row(name: str, r: dict) -> str:
    return (f"| {name} | {fmt(r.get('coef'))} | {fmt(r.get('t_two_way'), 2)} | {fmt(r.get('t_firm'), 2)} | {fmt(r.get('wcr_p_negative'))} | {r.get('treated_firms', 0):,} | {r.get('treated_rows', 0):,} | {r.get('rows', 0):,} |")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="experiments/EXP-014")
    args = ap.parse_args()
    src = REPO / args.source
    res = json.loads((src / "results.json").read_text())
    man = json.loads((src / "manifest.json").read_text())
    reg, dec, counts = res["regressions"], res["decision"], res["counts"]
    fp = exp014.definition_fingerprint(REPO)
    gates = "\n".join(f"| {g} | {'passed' if ok else '**failed**'} |" for g, ok in dec["gates"].items())
    secondary = "\n".join(reg_row(k, v) for k, v in reg["secondary"].items())
    years = ", ".join(f"{r['left_out']}: {r['coef']:+.3f}" for r in reg["R3_years"])
    sectors = ", ".join(f"{r['left_out']}: {r['coef']:+.3f}" for r in reg["R6_sector"])
    event = reg["event_time"]
    bins = "\n".join(f"| {k} | {fmt(v['coef'])} | {fmt(v['wcr_p_negative'])} | {v['treated_firms']:,} |" for k, v in event["bins"].items())
    cal = reg["placebo_events"]
    ml = man["machine_learning"]
    ml_text = "Skipped."
    if not ml.get("skipped"):
        rows = "\n".join(f"| {k} | {v['left']} vs {v['right']} | {fmt(v['mean_diff'], 5)} | {fmt(v.get('hac_t'), 2)} | {fmt(v.get('p_one_sided'))} | {fmt(v.get('holm_adjusted_p'))} | {v['positive_folds']} of 8 | [{fmt(v['boot95_low'], 5)}, {fmt(v['boot95_high'], 5)}] |" for k, v in ml["contrasts"].items())
        sa = ml.get("score_augmented_regression", {})
        econ = ml.get("economics", {})
        erows = "\n".join(f"| {k} | {fmt(v.get('mean_rank_ic'), 5)} | {fmt(v.get('b1_net_sharpe_10bp'), 3)} | {fmt(v.get('b1_gross_sharpe'), 3)} | {fmt(v.get('b1_annualised_turnover'), 2)} | {fmt(v.get('b1_cost_share_of_gross'), 3)} |" for k, v in econ.items())
        ml_text = f"""Labels (separate verdicts, not part of the decision): {ml['labels']}.

| Contrast | Arms | Mean Rank-IC difference | HAC t | one-sided p | Holm p | Positive folds | Block-bootstrap 95% |
|---|---|---|---|---|---|---|---|
{rows}

Secondary S7, H1 with the out-of-sample ridge score held fixed: coefficient {fmt(sa.get('coef'))}, wild-cluster one-sided p {fmt(sa.get('wcr_p_negative'))}, {sa.get('treated_firms', 0):,} treated firms, {sa.get('rows', 0):,} rows.

Saved artifact: `{ml['artifact']['path']}`; fresh-process reload check: {ml['artifact']['reload_check_in_fresh_process']}.

### Economics (the frozen 21-session portfolio, 10 bp)

| Arm:seed | Mean Rank IC | Net Sharpe 10 bp | Gross Sharpe | Annualised turnover | Cost share of gross |
|---|---|---|---|---|---|
{erows}
"""
    doc = f"""# EXP-014 results - the restating-amendment signal in firms the discovery never saw

Registration: `docs/EXP_014_PREREGISTRATION.md`, fingerprint `{fp}`. Run: commit `{man.get('git_commit')}`, dirty tree: {man.get('git_dirty')}. Completion: **{man.get('completion')}**. Wall time {man['compute']['wall_seconds']:.0f} s.
Holdout sealed (untouched). Promotion not assessed.

## 1. Outcome

**{dec['label']}.** {PERMITTED[dec['label']]}
{('Interpretation: **' + dec['interpretation'] + '**.') if dec.get('interpretation') else ''}

| Gate | Result |
|---|---|
{gates}

Samples: confirmatory {counts['confirmatory_rows']:,} rows, {counts['confirmatory_firms']:,} firms, {counts['confirmatory_dates']} dates (discovery-universe companies excluded: {counts['discovery_ciks_excluded']:,}; {counts['mid_rows_dropped_as_discovery_companies']:,} panel rows dropped on that ground);
time-separate {counts['time_separate_rows']:,} rows, {counts['time_separate_firms']:,} firms.

## 2. Registered regressions

Coefficient on the 21-session forward return rank (centred ranks run from -1 to 1), date x sector fixed effects, 17 controls, wild-cluster bootstrap p (one-sided, negative, firm clusters, null imposed).
Two-way and firm-clustered t statistics are shown for comparison only.

| Test | Coef | t (two-way) | t (firm) | WCR p | Treated firms | Treated rows | Rows |
|---|---|---|---|---|---|---|---|
{reg_row('H1 core, 730 days', reg['H1'])}
{reg_row('H2 any amendment, 730 days', reg['H2'])}
{reg_row('R4 H1 with all 76 features as controls', reg['R4_full_controls'])}
{reg_row('R2 H1 without the 5 most influential treated firms', reg['R2_influence'])}
{reg_row('R5 H1, time-separate sample', reg['R5_time_separate'])}
{reg_row('R5 H2, time-separate sample', reg['R5_time_separate_any'])}

Holm-adjusted p: H1 {fmt(reg['holm_adjusted_p']['H1'])}, H2 {fmt(reg['holm_adjusted_p']['H2'])}. Share of the full H1 estimate kept after removing the five most influential treated firms:
{fmt(reg['R2_influence']['share_of_full_estimate'], 3)} (removed: {', '.join(reg['R2_influence']['removed_firms'])}).

Leave-one-year-out coefficients: {years}.
Leave-one-sector-out coefficients: {sectors}.

### Secondary regressions (not gated)

| Test | Coef | t (two-way) | t (firm) | WCR p | Treated firms | Treated rows | Rows |
|---|---|---|---|---|---|---|---|
{secondary}

## 3. Event-time bins (interpretation diagnostic)

| Bin | Coef | WCR p | Treated firms |
|---|---|---|---|
{bins}

Anticipation ratio coef(next 365 days) / coef(previous 365 days): {fmt(event['anticipation_ratio'], 3)} (below 0.5: TIME_SPECIFIC).

## 4. Size of the procedure on the real label structure

{cal['placebo_draws']} draws, each giving {cal['treated_firms_per_draw']} random firms one placebo amendment: rejection rate at 5% (one-sided) {fmt(cal['rejection_rate_5pct_one_sided'], 3)}, at 1% {fmt(cal['rejection_rate_1pct_one_sided'], 3)}.

## 5. Machine-learning increment and economics (reported separately)

{ml_text}

## 6. Reproduction

`python -m scripts.quant.exp014 run --workers 6` (gate first); outputs under `experiments/EXP-014/` with a manifest of SHA-256 hashes; saved model scored again in a fresh process by `python -m scripts.quant.exp014 infer`.
"""
    out = REPO / "docs/EXP_014_RESULTS.md"
    out.write_text(doc, encoding="utf-8")
    print(f"wrote {out} ({len(doc):,} characters)")


if __name__ == "__main__":
    main()
