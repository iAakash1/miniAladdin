#!/usr/bin/env python3
"""Write docs/EXP_014_PREREGISTRATION.md from the live definition, so the document cannot disagree with the code it registers.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/make_prereg_doc_014.py

Inputs: src/quant/study/exp014.py (definition and fingerprint), docs/EXP_014_INPUTS.json (sha256 of every registered input) and
docs/research/market-signal-review-2026-10-11/validation/exp014_pre_registration_checks.json (label-free counts, size calibration and rehearsal, produced before registration).
Not covered by the fingerprint: the registered object is the document this writes plus the method files it lists.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from src.quant.study import exp014  # noqa: E402

CHECKS = REPO / "docs/research/market-signal-review-2026-10-11/validation/exp014_pre_registration_checks.json"
DOC = REPO / exp014.PREREG_DOC


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def mde(sd: float) -> float:
    """Smallest true coefficient found with 80% power by a one-sided 5% test when the estimator's sampling sd is `sd` (normal approximation)."""
    return (1.6449 + 0.8416) * sd


def power(effect: float, sd: float) -> str:
    """One-sided 5% power at a true coefficient of -`effect` (normal approximation), as a percentage."""
    z = effect / sd - 1.6449
    return f"{100 * 0.5 * (1 + math.erf(z / math.sqrt(2))):.0f}%"


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
    secondary_list = "; ".join(f"{k}: {v}" for k, v in d["secondary_analyses"].items())
    reh_sec = json.loads((REPO / "experiments/EXP-014_rehearsal/results.json").read_text())["regressions"]["secondary"]          # treated counts do not depend on the (shuffled) label
    bin_names = {"S11_age_0_90": "0-89", "S11_age_90_180": "90-179", "S11_age_180_365": "180-364", "S11_age_365_730": "365-729"}
    label_free_s11 = "; ".join(f"first usable {bin_names[k]} days earlier: {reh_sec[k]['treated_firms']} firms / {reh_sec[k]['treated_rows']:,} rows" for k in bin_names)
    label_free_s12 = "; ".join(f"{k.replace('S12_', '').replace('_', ' ')} {reh_sec[k]['treated_firms']} treated firms / {reh_sec[k]['treated_rows']:,} treated rows of {reh_sec[k]['rows']:,}" for k in sorted(reh_sec) if k.startswith("S12_"))
    doc = f"""# EXP-014 preregistration - does the restating-amendment signal survive in firms the discovery never saw?

Definition fingerprint: `{fp}`

Parent: EXP-012 and EXP-013. Status: **CONFIRMATORY on an independent firm sample - holdout sealed - promotion not assessed.** This document is committed and pushed to the research branch before any
arm is fit on the real label and before any relation between an amendment variable and a return is computed on the registered samples. The fingerprint is the SHA-256 of the canonical definition (`src/quant/study/exp014.py`,
`DEFINITION`) and of the bytes of every method file in section 14. If the definition or a method file changes after registration, the gate refuses to run.

## 1. Purpose, and what this is not

EXP-012 and EXP-013 used the 250 most liquid US names each month. On that sample, firms with a recent amendment to a periodic report earn lower next-month return ranks; the whole effect sits in amendments
that change the reported numbers; and it rests on a small number of firms (60 with any amendment, 18 with a changing amendment). **The sign is not settled by the literature.** Studies of restatement announcements
disagree about what follows: negative long-run abnormal returns in several older studies, no drift where the news is about cash flows, and, in the one paper read in full for this registration (Frieder and
Shanthikumar 2008), no significant negative drift and a significant POSITIVE return 64 to 126 trading days after the announcement; a 2025 paper finds negative drift after material-weakness disclosures
(`16_FRIEDER_SHANTHIKUMAR_FULLTEXT_REVIEW.md`, `17_RECENT_LITERATURE_2022_2026.md`). None of the studies found treats content-classified amendments to periodic reports as a cross-sectional predictor. This study
asks the narrower, testable question: **in firms the discovery never saw, with a point-in-time construction, valid inference for few treated firms and the established controls, is a value-changing amendment followed by
lower return ranks (the registered direction), by higher ones (the opposite direction, reported if the data show it), or by neither; and does it add to a conventional ranking and to a cost-aware portfolio?**

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
* **Literature-driven amendments, made before registration and before any relation between an amendment variable and a return was computed on the independent sample.** After a full-text reading of Frieder and
  Shanthikumar (2008) and an update of the literature to 12 October 2026, the protocol gained (a) the label REVERSED (a positive H1 coefficient with two-sided wild-cluster p < 0.05), because the sign is contested;
  (b) secondary S11, the age of a past core amendment in four bins, because the only significant post-restatement drift in that paper is positive and sits in trading days 64 to 126; (c) secondary S12, H1 in the
  more and the less liquid half, because the machine-learning and design-sensitivity literature finds effects concentrated in difficult-to-trade stocks. None of the three can change SURVIVES, FRAGILE or INCONCLUSIVE.
* **Rehearsal:** the whole pipeline (regressions, machine-learning arms, economics, saved-artifact reload) was run with the label shuffled across firms within each date, to prove that every code path runs
  and that nothing is reported as a result of that run (the regression stage alone had also been rehearsed in an earlier session, before the literature-driven amendments). Its outcome was {reh['decision']['label']} with H1 Holm-adjusted p {reh['decision']['h1_adjusted_p']:.3f}, as it must be on a shuffled label.

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
- **Power (approximate).** Taking the spread of the placebo coefficients above as the sampling standard deviation of the estimator under the null (a normal approximation, ignoring the bootstrap's own noise), the smallest
  true coefficient detected with 80% power by a one-sided 5% test is {mde(calib['coef_sd']):.3f} for the pooled regression and {mde(calib_w['coef_sd']):.3f} within firm (centred ranks run from -1 to 1, so 0.1 is
  five percentile points). Power at a true coefficient of -0.245 / -0.154 / -0.077 / -0.05: pooled {power(0.245, calib['coef_sd'])} / {power(0.154, calib['coef_sd'])} / {power(0.077, calib['coef_sd'])} / {power(0.05, calib['coef_sd'])};
  within firm {power(0.245, calib_w['coef_sd'])} / {power(0.154, calib_w['coef_sd'])} / {power(0.077, calib_w['coef_sd'])} / {power(0.05, calib_w['coef_sd'])}. The discovery sample's estimates (-0.245 pooled, -0.154 within
  firm) are selected and probably too large; against an effect half their size the within-firm gate has roughly two chances in three. A NOT_REPLICATED outcome is therefore evidence against large effects only.
- **Two-sided reporting.** For REVERSED the two-sided wild-cluster p-value of H1 is used; it is not adjusted for multiplicity (the label is descriptive) and it carries no gate.

## 7. Robustness gates

{gates}

Secondary analyses (reported, not gated; `secondary_analyses` in the definition): {secondary_list}

Label-free counts for the two analyses added after the literature update (read from the rehearsal frame; treatment counts do not depend on the label): S11 core amendment {label_free_s11}; S12 {label_free_s12}.

**Reading rule for S11 and S12, fixed now.** They are descriptive and are read only if R1 passes. The rebound reported by Frieder and Shanthikumar, if present, would appear as positive S11 coefficients in the 90-179 and 180-364 day bins (their trading days 64-126 are about 90-180 calendar days after an announcement; an amendment can come later than the announcement, so the bins are a rough guide); a negative association that concentrates in the 0-89 day bin would point to the immediate reaction instead. S12 asks whether the H1 coefficient lives in the less liquid half; a coefficient present only there is reported as such and is not a reason to change the decision.

## 8. Interpretation diagnostic

{d['interpretation_diagnostic']['anticipation_ratio']}

## 9. Decision rule (applied mechanically by `decide`)

{decision}

SURVIVES permits one sentence: "in an independent sample the association survived the registered robustness checks", plus the interpretation label. It does not permit a claim of investment value,
production use or a new anomaly. REVERSED permits: "in an independent sample the association has the opposite sign to the registered hypothesis (descriptive)". NOT_REPLICATED permits: "was not reproduced at the
registered level of evidence", and with the power paragraph in section 6 it excludes only large effects.

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

Two confirmatory hypotheses (Holm), seven gates (mechanical, not tests), sixteen secondary regressions (S1 to S12, S11 being four) and two machine-learning contrasts (reported with their own adjustment), and the cumulative trial count
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
- An amendment is a detection and disclosure event, not the misstatement itself: only detected misstatements are observable (Barton et al. 2022), so the coefficient measures the price relevance of detection and
  disclosure, and an amendment can follow earlier public news (an Item 4.02 8-K or an earnings release), which is why S9 and the age bins are reported.
- Firm type: material weaknesses repeat (79% conditional against 6% unconditional probability in Ghosh et al.) and filing-discipline effects work through the level, not the within-firm change (Zhu 2026). A pooled
  association can therefore reflect which firms get amendments; the within-firm gate R7 exists for that reason and its power is lower than the pooled test's.
- Several 2026 working papers on filing-process signals (late-filing notices, filing timeliness, 8-K irregularity) are not peer reviewed and report very large alphas in small and volatile stocks; they are context,
  not evidence for or against H1.
"""
    DOC.write_text(doc, encoding="utf-8")
    print(f"wrote {DOC} ({len(doc):,} characters), fingerprint {fp}")


if __name__ == "__main__":
    main()
