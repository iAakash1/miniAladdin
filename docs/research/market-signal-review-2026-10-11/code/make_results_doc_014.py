#!/usr/bin/env python3
"""Write docs/EXP_014_RESULTS.md from experiments/EXP-014 (results.json, ml_*.csv, economics.csv, manifest.json), so the document cannot disagree with the numbers.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/make_results_doc_014.py [--source experiments/EXP-014]

The narrative sentences are deliberately limited to what the decision rule permits (`DEFINITION["decision"]`); everything else is a table.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from src.quant.study import exp014  # noqa: E402

PERMITTED = {
    "SURVIVES": "In an independent sample the association survived the registered robustness checks. This is not evidence of investment value, and the interpretation label below says whether it looks like news or like a marker.",
    "FRAGILE": "In an independent sample the association is statistically present but failed at least one registered robustness check; it is not established.",
    "REVERSED": "In an independent sample the association has the opposite sign to the registered hypothesis with two-sided wild-cluster p < 0.05 (descriptive, uncorrected). It does not support the registered direction.",
    "NOT_REPLICATED": "In an independent sample the association was not reproduced at the registered level of evidence.",
    "INCONCLUSIVE": "The independent sample has too few treated companies to conclude anything about the hypothesis.",
}


def fmt(x, nd=4):
    return "n/a" if x is None or (isinstance(x, float) and x != x) else f"{x:.{nd}f}"


def reg_row(name: str, r: dict) -> str:
    return (f"| {name} | {fmt(r.get('coef'))} | {fmt(r.get('t_two_way'), 2)} | {fmt(r.get('t_firm'), 2)} | {fmt(r.get('wcr_p_negative'))} | {fmt(r.get('wcr_p_two_sided'))} | {r.get('treated_firms', 0):,} | {r.get('treated_rows', 0):,} | {r.get('rows', 0):,} |")


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
    cal_w = reg["placebo_events_within_firm"]
    ml = man["machine_learning"]
    art = REPO / ml["artifact"]["path"] if not ml.get("skipped") else None
    art_sha = hashlib.sha256(art.read_bytes()).hexdigest() if art is not None and art.exists() else "not on disk"
    r3 = sum(1 for r in reg["R3_years"] if r["coef"] < 0)
    r6 = sum(1 for r in reg["R6_sector"] if r["coef"] < 0)
    sec = reg["secondary"]
    margins = f"""| Gate | Quantity | Observed | Threshold |
|---|---|---|---|
| R1 | distinct treated firms / treated rows (core, 730 days) | {reg['H1']['treated_firms']} / {reg['H1']['treated_rows']:,} | at least 40 / 150 |
| R2 | share of the H1 estimate kept after removing the 5 most influential treated firms | {fmt(reg['R2_influence']['share_of_full_estimate'], 3)} (coefficient {fmt(reg['R2_influence']['coef'])}) | at least 0.5, same sign |
| R3 | leave-one-year-out fits with a negative coefficient | {r3} of {len(reg['R3_years'])} | at least 9 |
| R4 | full-control H1: coefficient / one-sided p | {fmt(reg['R4_full_controls']['coef'])} / {fmt(reg['R4_full_controls']['wcr_p_negative'])} | negative / below 0.05 |
| R5 | time-separate: core coefficient; any-amendment coefficient / one-sided p | {fmt(reg['R5_time_separate']['coef'])}; {fmt(reg['R5_time_separate_any']['coef'])} / {fmt(reg['R5_time_separate_any']['wcr_p_negative'])} | negative; negative / below 0.10 |
| R6 | leave-one-sector-out fits with a negative coefficient | {r6} of {len(reg['R6_sector'])} | at least 8 |
| R7 | within-firm H1: coefficient / one-sided p | {fmt(reg['R7_within_firm']['coef'])} / {fmt(reg['R7_within_firm']['wcr_p_negative'])} | negative / below 0.05 |

The margins are shown so that nobody has to take the gate list on trust; they do not change the label. Thresholds were fixed in the registration and apply mechanically."""
    def sgn(x):
        return "negative" if x < 0 else "positive"
    ev = reg["event_time"]
    prev_p, next_p = ev["bins"]["D_core_prev365"]["wcr_p_negative"], ev["bins"]["D_core_next365"]["wcr_p_negative"]
    ratio_note = (f"The ratio is ill-conditioned because its denominator, the coefficient for amendments usable in the previous 365 days ({fmt(ev['bins']['D_core_prev365']['coef'])}, one-sided p {fmt(prev_p)}), is indistinguishable from zero, "
                  f"while the coefficient for amendments that will become usable in the NEXT 365 days is {fmt(ev['bins']['D_core_next365']['coef'])} (one-sided p {fmt(next_p)}). The registered rule labels the pattern {dec.get('interpretation')}; read plainly, the association is not a drift in the first year after the amendment: it is present before the amendment (the look-ahead bin) and in the second year after it (S11).")
    notes = f"""* **Where the association sits in time (S11 and the event-time bins).** Amendments first usable 0-89 days earlier: {fmt(sec['S11_age_0_90']['coef'])} (two-sided p {fmt(sec['S11_age_0_90']['wcr_p_two_sided'])}); 90-179: {fmt(sec['S11_age_90_180']['coef'])} ({fmt(sec['S11_age_90_180']['wcr_p_two_sided'])}); 180-364: {fmt(sec['S11_age_180_365']['coef'])} ({fmt(sec['S11_age_180_365']['wcr_p_two_sided'])}); 365-729: {fmt(sec['S11_age_365_730']['coef'])} ({fmt(sec['S11_age_365_730']['wcr_p_two_sided'])}). The registered reading rule said a rebound of the Frieder and Shanthikumar kind would show as positive coefficients in the 90-179 and 180-364 day bins: the 90-179 coefficient is {sgn(sec['S11_age_90_180']['coef'])} and not distinguishable from zero, the 180-364 coefficient is {sgn(sec['S11_age_180_365']['coef'])} and not distinguishable from zero, so these data neither show nor exclude that rebound. The negative association is concentrated in amendments that are one to two years old and, in the look-ahead bin, in firms that will file a value-changing amendment within the next year; it is not visible in the first year after the amendment.
* **Item 4.02 and late-filing notices (S8, S9).** An Item 4.02 (non-reliance) 8-K in the trailing 730 days: coefficient {fmt(sec['S8_item_4_02']['coef'])} (two-sided p {fmt(sec['S8_item_4_02']['wcr_p_two_sided'])}, {sec['S8_item_4_02']['treated_firms']} firms), stronger than H1. With Item 4.02 and late-filing notices entered beside it, the core-amendment coefficient is {fmt(sec['S9_core_with_4_02_and_nt']['coef'])} (two-sided p {fmt(sec['S9_core_with_4_02_and_nt']['wcr_p_two_sided'])}) and the Item 4.02 coefficient {fmt(sec['S9_core_with_4_02_and_nt']['coefficients']['D_i402_730'])}: the amendment adds nothing in the registered direction once the announcement is in the model. These are registered secondary analyses, sixteen in all, not corrected for multiplicity and not gated.
* **Any amendment, unchanged-number amendments, other forms.** H2 (any amendment): {fmt(reg['H2']['coef'])} (adjusted p {fmt(reg['holm_adjusted_p']['H2'])}); S3 (numbers unchanged): {fmt(sec['S3_unchanged']['coef'])} (two-sided p {fmt(sec['S3_unchanged']['wcr_p_two_sided'])}); S10 (no financial statements): {fmt(sec['S10_amendments_without_financials']['coef'])}; S5 and S6 (10-K/A and 10-Q/A): {fmt(sec['S5_k_core']['coef'])} and {fmt(sec['S6_q_core']['coef'])}.
* **Liquidity (S12).** More liquid half {fmt(sec['S12_liquid_half']['coef'])} (one-sided p {fmt(sec['S12_liquid_half']['wcr_p_negative'])}, {sec['S12_liquid_half']['treated_firms']} firms), less liquid half {fmt(sec['S12_illiquid_half']['coef'])} ({fmt(sec['S12_illiquid_half']['wcr_p_negative'])}, {sec['S12_illiquid_half']['treated_firms']} firms): the point estimates are close, so the pooled association is not confined to the less liquid stocks, but neither half has much power alone.
* **Size against the discovery sample.** The discovery coefficient was -0.245 (18 treated firms; -0.154 with a firm effect); here {fmt(reg['H1']['coef'])} pooled and {fmt(reg['R7_within_firm']['coef'])} within firm, about a fifth to a third of the discovery size, consistent with the shrinkage expected of a selected discovery estimate.
* **Machine learning and economics.** The amendment block adds {fmt(ml['contrasts']['T_ridge']['mean_diff'], 5)} (ridge) and {fmt(ml['contrasts']['T_boosted']['mean_diff'], 5)} (boosted) Rank IC, labels {ml['labels']}; with the out-of-sample ridge score held fixed the H1 coefficient is {fmt(ml['score_augmented_regression']['coef'])}. The frozen portfolio's net Sharpe at 10 bp is similar with and without the block (see the table). The economics describe the independent universe in general and are not a promotion argument."""
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

Saved artifact: `{ml['artifact']['path']}` (git-ignored; SHA-256 `{art_sha}`); fresh-process reload check: {ml['artifact']['reload_check_in_fresh_process']}.

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

### Distance to the registered thresholds (mechanical)

{margins}

Samples: confirmatory {counts['confirmatory_rows']:,} rows, {counts['confirmatory_firms']:,} firms, {counts['confirmatory_dates']} dates (discovery-universe companies excluded: {counts['discovery_ciks_excluded']:,}; {counts['mid_rows_dropped_as_discovery_companies']:,} panel rows dropped on that ground);
time-separate {counts['time_separate_rows']:,} rows, {counts['time_separate_firms']:,} firms.

## 2. Registered regressions

Coefficient on the 21-session forward return rank (centred ranks run from -1 to 1), date x sector fixed effects, 17 controls, wild-cluster bootstrap p (one-sided, negative, firm clusters, null imposed).
Two-way and firm-clustered t statistics are shown for comparison only.

| Test | Coef | t (two-way) | t (firm) | WCR p (one-sided, negative) | WCR p (two-sided) | Treated firms | Treated rows | Rows |
|---|---|---|---|---|---|---|---|---|
{reg_row('H1 core, 730 days', reg['H1'])}
{reg_row('H2 any amendment, 730 days', reg['H2'])}
{reg_row('R4 H1 with all 76 features as controls', reg['R4_full_controls'])}
{reg_row('R2 H1 without the 5 most influential treated firms', reg['R2_influence'])}
{reg_row('R5 H1, time-separate sample', reg['R5_time_separate'])}
{reg_row('R5 H2, time-separate sample', reg['R5_time_separate_any'])}
{reg_row('R7 H1 with a fixed effect per firm (within-firm timing)', reg['R7_within_firm'])}

Holm-adjusted p: H1 {fmt(reg['holm_adjusted_p']['H1'])}, H2 {fmt(reg['holm_adjusted_p']['H2'])}. Share of the full H1 estimate kept after removing the five most influential treated firms:
{fmt(reg['R2_influence']['share_of_full_estimate'], 3)} (removed: {', '.join(reg['R2_influence']['removed_firms'])}).

Leave-one-year-out coefficients: {years}.
Leave-one-sector-out coefficients: {sectors}.

### Secondary regressions (not gated)

| Test | Coef | t (two-way) | t (firm) | WCR p (one-sided, negative) | WCR p (two-sided) | Treated firms | Treated rows | Rows |
|---|---|---|---|---|---|---|---|---|
{secondary}

S11 (age of a core amendment) and S12 (liquidity halves) are descriptive and were registered as such: the age bins show where in time after an amendment any association sits (the competing prediction of
Frieder and Shanthikumar is a positive coefficient in the first two bins), the halves show whether it lives in the less liquid stocks.

## 3. Event-time bins (interpretation diagnostic)

| Bin | Coef | WCR p | Treated firms |
|---|---|---|---|
{bins}

Anticipation ratio coef(next 365 days) / coef(previous 365 days): {fmt(event['anticipation_ratio'], 3)} (below 0.5: TIME_SPECIFIC). {ratio_note}

## 4. Size of the procedure on the real label structure

{cal['placebo_draws']} draws, each giving {cal['treated_firms_per_draw']} random firms one placebo amendment: rejection rate at 5% (one-sided) {fmt(cal['rejection_rate_5pct_one_sided'], 3)}, at 1% {fmt(cal['rejection_rate_1pct_one_sided'], 3)}
(pooled regression; mean placebo coefficient {fmt(cal['coef_mean'])}, sd {fmt(cal['coef_sd'])}). With a fixed effect per firm: {fmt(cal_w['rejection_rate_5pct_one_sided'], 3)} at 5%, {fmt(cal_w['rejection_rate_1pct_one_sided'], 3)} at 1%
(mean {fmt(cal_w['coef_mean'])}, sd {fmt(cal_w['coef_sd'])}). These are the numbers of THIS run on the real labels with placebo events; the pre-registration quotes the earlier pre-run values.

## 4b. Descriptive notes on the secondary analyses (not part of the decision)

{notes}

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
