#!/usr/bin/env python3
"""Write docs/EXP_014_PREREGISTRATION.md from the live definition, so the document cannot disagree with the code it registers.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/make_prereg_doc_014.py

Inputs: src/quant/study/exp014.py (definition and fingerprint), docs/EXP_014_INPUTS.json (sha256 of every registered input) and
docs/research/market-signal-review-2026-10-11/validation/exp014_pre_registration_checks.json (label-free counts, size calibration and rehearsal, produced before registration).
Not covered by the fingerprint: the registered object is the document this writes plus the method files it lists.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from src.quant.study import exp014  # noqa: E402

CHECKS = REPO / "docs/research/market-signal-review-2026-10-11/validation/exp014_pre_registration_checks.json"
DOC = REPO / exp014.PREREG_DOC


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def main() -> None:
    fp = exp014.definition_fingerprint(REPO)
    inputs = json.loads((REPO / exp014.INPUTS_FILE).read_text())["sha256"]
    chk = json.loads(CHECKS.read_text())
    counts, calib, panel, edgar = chk["label_free_counts"], chk["size_calibration"], chk["mid_panel"], chk["edgar_registry"]
    d = exp014.DEFINITION
    gates = "\n".join(f"- **{k}**: {v}" for k, v in d["robustness_gates"].items())
    decision = "\n".join(f"- **{k}**: {v}" for k, v in d["decision"].items() if k != "no_other_outcomes")
    hashes = "\n".join(f"| `{k}` | `{exp014.input_paths()[k]}` | `{v}` |" for k, v in inputs.items())
    methods = "\n".join(f"- `{m}`" for m in exp014.METHOD_SOURCES)
    conf, sep = counts["confirmatory"], counts["time_separate"]
    reh_path = REPO / "experiments/EXP-014_rehearsal/manifest.json"
    if not reh_path.exists():
        sys.exit("run the FULL rehearsal first: python -m scripts.quant.exp014 rehearse --workers 6 --draws 999 --rehearsal-output experiments/EXP-014_rehearsal")
    reh = json.loads(reh_path.read_text())
    if reh.get("completion") != "REHEARSAL" or reh["machine_learning"].get("skipped") or "economics" not in reh["machine_learning"]:
        sys.exit("the rehearsal on disk skipped the machine-learning or economics stage; the registration may only say the whole pipeline was rehearsed when it was")
    calib_w = chk["size_calibration_within_firm"]
    doc = f"""# EXP-014 preregistration - does the restating-amendment signal survive in firms the discovery never saw?

Definition fingerprint: `{fp}`

Parent: EXP-012 and EXP-013. Status: **CONFIRMATORY on an independent firm sample - holdout sealed - promotion not assessed.** This document is committed and pushed to the research branch before any
arm is fit and before any relation between an amendment variable and a return is computed on the registered samples. The fingerprint is the SHA-256 of the canonical definition (`src/quant/study/exp014.py`,
`DEFINITION`) and of the bytes of every method file in section 14. If the definition or a method file changes after registration, the gate refuses to run.

## 1. Purpose, and what this is not

EXP-012 and EXP-013 used the 250 most liquid US names each month. On that sample, firms with a recent amendment to a periodic report earn lower next-month return ranks; the whole effect sits in amendments
that change the reported numbers; and it rests on a small number of firms (60 with any amendment, 18 with a changing amendment). The literature already reports that restating firms underperform for years
(`12_FULLTEXT_REVIEW_AND_NOVELTY_MATRIX.md`, A01), so the sign is not a discovery. This study asks the narrower, testable question: **in firms the discovery never saw, with a point-in-time construction, valid
inference for few treated firms and the established controls, is a value-changing amendment followed by lower return ranks, and does it add to a conventional ranking and to a cost-aware portfolio?**

It does not scale the discovery model, claims no investment value, and does not touch the holdout (2025-08-26 onward). A failure is a result.

## 2. What was known and done before registration (disclosure)

* **Discovery sample, exploratory, already analysed** (`validation/phase2_*.json`, `docs/EXP_012_RESULTS.md`, `docs/EXP_013_RESULTS.md`): coefficient on any amendment in two years -0.092 (60 treated firms), on
  changing amendments -0.245 (18 treated firms), on unchanged-number amendments -0.049; wild-cluster bootstrap p about 1e-4 for both; still -0.126 after removing the ten most influential treated firms; the
  paired rank-IC gain of the machine-learning model is fragile. The category definitions, the 730-day window and the control list used here come from that analysis and are therefore **not** independent of it;
  only the sample is.
* **Choices fixed after seeing the discovery results and before touching the independent sample:** the four exhaustive amendment categories, the 730-day window, the controls, the fixed effects (date x
  Fama-French 12), the wild-cluster bootstrap as the decision statistic, and the gates below.
* **Independent sample, what has been looked at:** universe construction (membership counts only), price ingestion checks, the baseline frame's row and label coverage, identity coverage, the
  label-free counts of treated companies in section 4, and a size calibration with placebo events. **No relation between an amendment variable and a return, rank or label has been computed on it.**
* **Label-only descriptives computed on the independent sample** (no amendment variable involved): mean return rank by tenure and by time to a firm's last row (end-of-life rows carry systematically low ranks:
  -0.083 in the final quarter), and by firm lifespan. They motivated the within-firm gate R7 and the position-neutral placebo windows.
* **Rehearsal:** the whole pipeline (regressions, machine-learning arms, economics, saved-artifact reload) was run once with the label shuffled across firms within each date, to prove that every code path runs
  and that nothing is reported as a result of that run. Its outcome was {reh['decision']['label']} with H1 Holm-adjusted p {reh['decision']['h1_adjusted_p']:.3f}, as it must be on a shuffled label.

## 3. Data

All inputs are verified by SHA-256 before the study runs (`docs/EXP_014_INPUTS.json`).

| Input | Path | sha256 |
|---|---|---|
{hashes}

* **Prices and labels:** the community `post-no-preference/stocks` Dolt dataset (commit recorded in `data/manifests/mid_sample_ingest.json`), read from the local clone into a NEW store
  `data/research_mid/`, capped at 2025-06-30 (holdout starts 2025-08-26; the listing-snapshot table that runs to 2026-08 was deliberately not copied). Its redistribution terms have not been reviewed
  (`datasets.csv` L04): derived statistics are published, prices are not.
* **Universe:** liquidity ranks 251 to 1,000 by three-month median dollar volume (non-ETF, non-test issue, close >= 5), read from each month's whole-market cross-section so that delisted names are present in
  the months they were liquid ({panel['universe_snapshots']} snapshots, {panel['universe_unique_members']:,} members; size-250 rebuild equals the frozen universe on all 171 snapshots).
* **Identity:** ticker to company links graded by name history and exit evidence (`security_master_mid`); only rows with a trusted identity enter. Trusted share of rows: {pct(panel['trusted_share'])}.
* **SEC filings:** Financial Statement Data Sets (public domain) for amendments and their content; the EDGAR submissions registry for filing history ({edgar['companies']:,} companies,
  {edgar['rows']:,} filings of interest). The registry's acceptance stamps were audited against the FSDS and found unreliable for {pct(edgar['share_registry_stamp_wrong'])} of matched 10-K/10-Q filings
  (`data/manifests/edgar_filings_v1.json`, `clock_audit`); the study uses only the FSDS stamps for availability.
* **Panel:** 76 point-in-time features (26 price/liquidity, 50 SEC characteristics), size and industry-relative controls withheld as in the frozen panel; {panel['rows']:,} rows,
  {panel['dates']} dates, {panel['symbols']:,} symbols.

## 4. Samples, and how many companies carry each treatment (label-free)

**Confirmatory** (mid-liquidity universe, trusted identity, company never in the discovery universe, 2014-04-01 to 2025-05-09): {conf['rows']:,} labelled rows, {conf['firms']:,} firms, {conf['dates']} dates.
**Time-separate** (discovery firms on 2014-04-01 to 2017-03-31, used by EXP-011 to EXP-013 only for training): {sep['rows']:,} rows, {sep['firms']:,} firms.

| Treatment (trailing 730 days) | Confirmatory rows | Confirmatory firms | Time-separate rows | Time-separate firms |
|---|---|---|---|---|
{chr(10).join(f"| {k} | {conf['treatments'][k]['rows']:,} | {conf['treatments'][k]['firms']:,} | {sep['treatments'][k]['rows']:,} | {sep['treatments'][k]['firms']:,} |" for k in ('core_730', 'other_730', 'unchanged_730', 'unclass_730', 'any_730'))}

## 5. Variables

- Outcome: `fwd_rank_21`, the centred cross-sectional rank of the 21-session forward return within the universe-date.
- Treatment: four exhaustive, mutually exclusive categories of amendment to a periodic report available in the trailing 730 days: **core** (some of revenue, net income, assets, liabilities, equity or operating
  cash flow differs by more than 1% from the previous version), **other_changed**, **unchanged**, **unclass** (no comparable previous version). Indicators are NaN before the firm has any original periodic report.
  Availability: the first session whose close-based decision may use the amendment (accepted before 16:00 New York time: that session, otherwise the next).
- Controls (17, rank-centred, missing set to 0): {', '.join(exp014.BASE_CONTROLS)}. The full control set adds all 76 features.
- Fixed effects: date x Fama-French 12 sector.

## 6. Hypotheses and inference

- **H1:** the coefficient on core_730 is negative (with other_730, unchanged_730, unclass_730 as separate regressors).
- **H2:** the coefficient on any_730 (the EXP-012 definition) is negative.
- Holm across H1 and H2 on the wild-cluster bootstrap p-values (one-sided, negative; Webb six-point weights, null imposed, {exp014.WEBB_DRAWS:,} draws, firm clusters, seed {exp014.SEED}).
- The two-way (firm, date) clustered t and the firm-clustered t are reported, never used to decide.
- **Why the bootstrap:** in a simulation with three treated firms of fifty and no effect a plain firm-clustered t rejects 22.5% of the time at the nominal 5%; the bootstrap rejects 4.0% (one-sided).
- **Size on the real label structure.** Each really treated firm is paired with an untreated firm of similar length (rows within 25%) and the same sector, and the partner receives one placebo amendment: a
  730-day window starting on a day drawn uniformly, so that every row of the partner has the same chance of being flagged. The registered regression is then re-estimated and the bootstrap rejection rate counted.
  Pooled regression: {pct(calib['rejection_rate_5pct_one_sided'])} of {calib['placebo_draws']} draws reject at 5% (one-sided), {pct(calib['rejection_rate_1pct_one_sided'])} at 1%, mean placebo coefficient
  {calib['coef_mean']:+.4f} (sd {calib['coef_sd']:.4f}). With a fixed effect per firm: {pct(calib_w['rejection_rate_5pct_one_sided'])} and {pct(calib_w['rejection_rate_1pct_one_sided'])}, mean coefficient {calib_w['coef_mean']:+.4f}
  (sd {calib_w['coef_sd']:.4f}). The pooled regression over-rejects because flagged firms matched on length are short-lived, and short-lived firms have systematically lower return ranks (a firm-length / exit
  confound that is part of what a pooled association means); the within-firm regression is the size-correct test. That is why **SURVIVES requires both** the pooled H1 and the within-firm gate R7.

## 7. Robustness gates

{gates}

Secondary regressions (reported, not gated): S1 core amendment in 365 days; S2 in 1,095 days; S3 amendments without number changes; S4 unclassifiable amendments; S5 and S6 core amendments by 10-K/A and
10-Q/A; S7 H1 with the out-of-sample ridge score held fixed (machine-learning section); S8 8-K Item 4.02 (non-reliance) in 730 days; S9 core amendment with Item 4.02 and late-filing notices as competing
restatement indicators; S10 amendments that carry no financial statements. Registry events are usable from the first session after their event date (`registry_availability` in the definition).

## 8. Interpretation diagnostic

{d['interpretation_diagnostic']['anticipation_ratio']}

## 9. Decision rule (applied mechanically by `decide`)

{decision}

SURVIVES permits one sentence: "in an independent sample the association survived the registered robustness checks", plus the interpretation label. It does not permit a claim of investment value,
production use or a new anomaly.

## 10. Machine-learning increment (reported separately; cannot rescue a failed H1)

Arms: M0 ridge on the 76 features (alpha 10, no search); M1 adds the amendment block (core, other_changed, unchanged, unclass indicators and log1p of the count); G0 and G1 boosted equivalents (frozen
EXP-010A settings, 3 seeds); placebos of M1 (block permuted within date x 5 seeds; block shifted 252 sessions within firm). Test: paired mean Rank IC difference on identical dates, Newey-West HAC (4 lags),
moving-block bootstrap (block 6, 4,000 draws), Holm across the ridge and boosted contrasts, eight recorded folds. No hyperparameter is chosen on any data, so no selection correction is needed. The saved
M1 ridge is scored again in a fresh process and must reproduce the in-memory scores to 1e-9. Secondary S7 re-estimates H1 on the validation-period rows with the M0 out-of-sample score (ranked within date) added
to the controls.

## 11. Economics (reported separately; not part of the decision)

The frozen EXP-010B 21-session portfolio at 10 bp for M0, M1, G0 and G1 on the mid-sample daily panel, with 30 and 50 bp reported alongside. The previous result on the discovery sample was negative for every
ridge portfolio (net Sharpe -0.34 for A1, -0.49 for A5 at 10 bp) and that result is not hidden by this study.

## 12. Multiple testing and the ledger

Two confirmatory hypotheses (Holm), seven gates (mechanical, not tests), ten secondary regressions and two machine-learning contrasts (reported with their own adjustment), and the cumulative trial count
of the eight folds (1,029 before EXP-012; EXP-012 to EXP-013 added more and are counted in `docs/EXP_013_RESULTS.md`). The confirmatory regressions run on a sample that no earlier trial used.

## 13. Acceptance gates, reproducibility and compute

{chr(10).join('- ' + g for g in d['acceptance_gates'])}

`python -m scripts.quant.exp014 rehearse` runs everything on a shuffled label (writes outside `experiments/EXP-014`); `python -m scripts.quant.exp014 run` is the registered study. Wall time on a
laptop with six workers: minutes for the regressions, under an hour in all.

## 14. Method files covered by the fingerprint

{methods}

## 14b. What happens next, whatever the outcome

The sealed holdout (2025-08-26 to 2026-08-28) remains untouched and is the only unused period. Opening it needs a separate, frozen design and the owner's decision; this study does not.

## 15. Known threats, stated in advance

- The independent sample shares calendar months with the discovery sample: common shocks are absorbed by date fixed effects but cannot be removed from the evidence; the time-separate sample is the only
  separation in calendar time and it has 9 treated companies for the core definition.
- Names that delist inside the 21-session window have no label and drop out; restating firms delist more often, which works against finding a negative effect and makes the economic result optimistic.
- The classification of amendments needs a previous version with comparable facts; {pct(0.45)} of amendments in the discovery registry are unclassifiable and enter as their own category.
- Identity grades are lower for small and delisted names; only trusted rows enter, which selects on identity.
- The price source's licence has not been reviewed; nothing derived from it is a basis for a product claim.
"""
    DOC.write_text(doc, encoding="utf-8")
    print(f"wrote {DOC} ({len(doc):,} characters), fingerprint {fp}")


if __name__ == "__main__":
    main()
