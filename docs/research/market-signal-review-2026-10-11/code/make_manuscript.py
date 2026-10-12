#!/usr/bin/env python3
"""Write manuscript/draft.md: a feasibility-study draft of EXP-012 whose every number is read from the study's output files and whose references come from papers.json.

The prose states only what those files support. It refuses to run unless the verdicts are the ones the discussion was written for. The draft is for the owner's review; it is not submission-ready (the
literature positions rest on abstracts and verified metadata, and the declarations are deliberately incomplete).

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/make_manuscript.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
BASE = REPO / "docs/research/market-signal-review-2026-10-11"
EXP = REPO / "experiments/EXP-012"
CITED = ["Zhang2006Information", "Francis2007Information", "Chan2001Earnings", "Bannouh2019Filing", "Brooks2023Timeliness", "Chen2020Firm", "Richardson2005Accrual", "Palmrose2001Determinants",
         "Hribar2004Effect", "Dechow2011Predicting", "Freyberger2024Missing", "Gu2020Empirical", "Kelly2023Virtue", "Lalwani2025Empirical", "Hou2018Replicating", "Harvey2014Expected", "Jensen2023There",
         "Guo2009Data", "Cohen2018Lazy"]


def main() -> None:
    manifest = json.loads((EXP / "manifest.json").read_text())
    verdicts = {k: v["label"] for k, v in manifest["verdicts"].items()}
    if verdicts != {"T1": "SUPPORTED", "T2": "NOT_SUPPORTED", "T3": "NOT_SUPPORTED"}:
        sys.exit(f"the discussion was written for T1 SUPPORTED, T2 and T3 NOT_SUPPORTED; got {verdicts}")
    paired = {r["contrast"]: r for r in csv.DictReader((EXP / "paired_tests.csv").open())}
    arms = list(csv.DictReader((EXP / "per_arm_metrics.csv").open()))
    folds = list(csv.DictReader((EXP / "fold_metrics.csv").open()))
    naive = json.loads((EXP / "reference_naive.json").read_text())
    papers = {p["key"]: p for p in json.loads((BASE / "papers.json").read_text())}
    exp13 = REPO / "experiments/EXP-013"
    m13 = json.loads((exp13 / "manifest.json").read_text())
    if m13["attribution"] != {"P": "CARRIES", "M": "SHARES", "U": "NOT_CARRYING"}:
        sys.exit(f"the attribution paragraphs were written for P CARRIES, M SHARES, U NOT_CARRYING; got {m13['attribution']}")
    a13 = json.loads((exp13 / "attribution.json").read_text())
    p13 = {r["contrast"]: r for r in csv.DictReader((exp13 / "paired_tests.csv").open())}
    ic13 = a13["mean_rank_ic"]
    gain13 = ic13["B5"] - ic13["B1"]
    f = lambda r, k: float(r[k])

    def arm_mean(name, key):
        vals = [f(r, key) for r in arms if r["arm"] == name]
        return sum(vals) / len(vals)

    def fold_ic(name):
        by = {}
        for r in folds:
            if r["arm"] == name:
                by.setdefault(int(r["fold"]), []).append(f(r, "mean_rank_ic"))
        return [sum(v) / len(v) for _, v in sorted(by.items())]

    def row(k):
        r = paired[k]
        return f"| {k} | {r['left']} - {r['right']} | {f(r, 'mean_diff'):+.5f} | {f(r, 'hac_t'):.2f} | [{f(r, 'boot95_low'):+.4f}, {f(r, 'boot95_high'):+.4f}] | {r['positive_folds']}/8 |"

    a1, a5 = fold_ic("A1"), fold_ic("A5")
    t1 = json.loads(paired["T1"]["fold_diffs"])
    years = ["2017-18", "2018-19", "2019-20", "2020-21", "2021-22", "2022-23", "2023-24", "2024-25"]
    fold_rows = "\n".join(f"| {years[i]} | {a1[i]:+.4f} | {a5[i]:+.4f} | {t1[i]:+.4f} |" for i in range(8))

    def ref(key):
        p = papers[key]
        authors = p["authors"].replace("; ", ", ")
        ident = f"doi:{p['doi']}" if p["doi"] else ""
        status = "" if p["pub_status"] == "peer_reviewed_journal" else " [working paper or preprint]"
        return f"- {authors} ({p['year']}). {p['title'].rstrip('*')}. {p['venue']}. {ident}{status}"

    references = "\n".join(ref(k) for k in sorted(CITED, key=lambda k: papers[k]["authors"]))
    doc = f"""# Do disclosure-process variables add to a point-in-time ranking of US stocks? A preregistered, placebo-controlled feasibility study

**Status of this draft.** Written for the owner's review; a feasibility study; exploratory; **not submission-ready.** Every number below is read from the registered study's output files
(`experiments/EXP-012/`, summarised in `docs/EXP_012_RESULTS.md`). The positions taken on the literature rest on abstracts and verified bibliographic metadata, not full texts. The declarations at the end are
incomplete on purpose and must be completed by the owner.

## Abstract

Reporting behaviour (whether a firm amends its financial reports, files late relative to its own habit, or misses periodic filings) may signal how far its fundamentals can be trusted. We construct four such
disclosure-process variables strictly point in time from the SEC's filing registry and ask, in a preregistered test, whether they improve a ridge ranking of about 250 liquid US stocks over 404 decision dates (2017-2025,
eight yearly validation folds) beyond a 76-feature point-in-time set. Adding them raised the mean Rank IC from {arm_mean('A1', 'mean_rank_ic'):.4f} to {arm_mean('A5', 'mean_rank_ic'):.4f}
(+{f(paired['T1'], 'mean_diff'):.4f}; Newey-West t {f(paired['T1'], 'hac_t'):.2f}; Holm-adjusted p {manifest['verdicts']['T1']['adjusted_p']:.3f}), and a placebo that permutes the same columns across firms added nothing. The gain
was positive in six of eight folds but negative in the last two, about half of it survived a one-year shift of the columns, a gradient-boosting model gained nothing, and the frozen cost-aware portfolio did not improve.
Letting the variables moderate fundamentals signals did not help. A separately registered attribution check found that the gain is carried by the filing-process ranks, chiefly the count of amendments to periodic
reports in the previous two years, a rare event (about six names per date, from 60 firms). We read this as a lead, not a finding, and set out what would be needed to settle it.

## 1. Introduction

A fundamentals-based signal is computed from a filing. If the filing is old, was filed late, has since been amended, or belongs to a firm that files irregularly, the signal may describe the firm less well. The
idea that the strength of a signal depends on how uncertain or unreliable the underlying information is has a long record in finance and accounting (Zhang 2006; Francis et al. 2007; Chan et al. 2001; Richardson et al.
2005; Chen et al. 2020), and filing timeliness has been reported to predict returns (Bannouh et al. 2019; Brooks et al. 2023). Amendments and restatements are studied mostly as events (Palmrose et al. 2001; Hribar and
Jenkins 2004; Dechow et al. 2011). What this paper adds is modest and is stated as such: a vendor-free, strictly point-in-time construction of disclosure-process variables from the filing registry, and a preregistered test
of their incremental value inside a cost-aware machine-learning ranking, with placebos that destroy the link to the firm and a noise floor measured in a world with no signal.

The study is also a methodological exercise. Machine-learning return prediction (Gu et al. 2020; Kelly et al. 2023) reports results that move with research design choices (Lalwani et al. 2025); the replication
and multiple-testing literature asks for stricter standards (Harvey et al. 2014; Hou et al. 2018; Jensen et al. 2023); real-time data change what forecasts can achieve (Guo 2009); missing characteristics need explicit
treatment (Freyberger et al. 2024); and filing-derived signals can be under-used by investors (Cohen et al. 2018). We therefore fix the model class, folds and costs from earlier registered work, register the
contrasts and the decision rule before the run, and compare every real information set with a placebo.

## 2. Data and construction

**Universe and panel.** A frozen point-in-time panel of the 250 most liquid US non-ETF names per decision date (every fifth session; 139,292 name-dates, 762 securities, 2014-04-03 to 2025-05-09), 76 features (26
price, liquidity and macro features and 50 SEC-derived characteristics), and the label `fwd_rank_21`, the cross-sectional rank of the next 21 sessions' return. Prices come from a community source whose terms have not been
reviewed; this limits redistribution, not the analysis.

**Disclosure-process variables.** From the SEC Financial Statement Data Sets registry (371,229 filings), each filing becomes usable from the first session whose close-based decision may use it (a filing accepted before the
close is usable that day, otherwise the next session). Four variables result: the number of amendments to periodic reports usable in the trailing 730 days; whether the latest original periodic report has already been
amended; the number of original periodic reports in the trailing 400 days; and the lateness of the latest filing relative to the median of the firm's previous four of the same kind. Values are missing, never zero, before a
firm has any filing history; the registry column that records a *later* amendment is never read. Cross-sectional ranks of these, a count of missing fundamentals and a composite unreliability rank (the mean of five oriented
ranks, two of which are already in the 76 features) form the new block of six columns; 48 interaction terms multiply the fundamentals features by the composite.

**Validation of the construction.** Nine unit tests, including that filings usable after day d cannot change a value at day d; an independent recomputation of 4,000 sampled rows by a deliberately naive path (16,000
comparisons, no mismatch); two deliberate mutations that each broke the intended tests. Coverage is 91.8%. Three of the four raw variables are almost constant (an amendment in the trailing two years appears in 3.5%
of the non-missing rows, an amended latest report in 0.2%, and 98% of rows show four or five periodic reports), so the block is informative mainly through lateness and a small set of rows.

## 3. Design

Eight yearly expanding-window validation folds (validation windows from 2017-05 to 2025-05) with a purge; ridge with alpha 10 (no search); boosted settings frozen in an earlier experiment; the frozen 21-session
portfolio at a 10 basis point half-spread for economics. Fourteen arms and thirty fits: the baseline (A0) and rich (A1) sets that reproduce an earlier experiment, a rich set without its two existing reliability variables
(A2), the new block on the baseline (A4) and on the rich set (A5), the block with interactions (A6), and placebo arms in which the new block (and so the interactions built from it) or the two existing variables are
permuted across firms within each date (five draws) or shifted by 252 sessions within each firm. Three confirmatory contrasts, each of a paired difference of per-date Spearman Rank ICs: T1, A5 - A1; T2, A6 - A5; T3, A1 - A2,
tested one-sided with a Newey-West variance (4 lags) and adjusted by Holm's method; a contrast is SUPPORTED only if the adjusted p is below 0.05, at least six of eight folds are positive, and every mapped placebo is beaten.
The study is exploratory: the same folds were used by earlier experiments (1,029 cumulative trials), the holdout is sealed and was not used, and nothing is promoted. A follow-up attribution study (EXP-013; section 4.1) was registered and pushed separately before it was run. The design, the gates and the likely outcome of the main study were
committed and pushed before the run (registration commit `{manifest['registration_commit'][:12]}`; GitHub is not an independent registry).

## 4. Results

The run reproduced the parent experiment's baseline and rich arms to 4e-17 (gate), all predictions were finite, and the pipeline returned NOT_SUPPORTED on every test in a rehearsal with the label shuffled within each date.

| Test | Contrast | Mean Rank IC difference | HAC t | 95% block-bootstrap interval | Positive folds |
|---|---|---|---|---|---|
{row('T1')}
{row('T2')}
{row('T3')}

Holm-adjusted p: T1 {manifest['verdicts']['T1']['adjusted_p']:.3f} (SUPPORTED), T2 {manifest['verdicts']['T2']['adjusted_p']:.3f}, T3 {manifest['verdicts']['T3']['adjusted_p']:.3f} (NOT_SUPPORTED).

| Control | Contrast | Mean difference | HAC t | 95% interval | Positive folds |
|---|---|---|---|---|---|
{row('C1')}
{row('C2')}

| Fold (validation year) | A1 | A5 | A5 - A1 |
|---|---|---|---|
{fold_rows}

### 4.1 Attribution (EXP-013, separately registered; same folds, so another look)

Arms with each column and each group added to the rich set or removed from the full block (ridge, 34 fits, gates identical to the main study), against permuted and shifted placebos. The labels are descriptive rules fixed in advance.

| Group | Adds to the rich set | HAC t | Positive folds | Share of the T1 gain added / lost on removal | Label |
|---|---|---|---|---|---|
""" + "\n".join(f"| {a13['groups'][g]['what']} | {float(p13['G_' + g]['mean_diff']):+.5f} | {float(p13['G_' + g]['hac_t']):.2f} | {p13['G_' + g]['positive_folds']}/8 | {a13['groups'][g]['add_share']:+.2f} / {a13['groups'][g]['drop_share']:+.2f} | {a13['groups'][g]['label']} |" for g in ("P", "M", "U")) + f"""

The amendment count alone adds {float(p13['add_amended']['mean_diff']):+.5f} (t {float(p13['add_amended']['hac_t']):.2f}, {p13['add_amended']['positive_folds']}/8 folds); lateness deterioration, the regularity count and the latest-report-amended flag add
nothing on their own, and the composite adds nothing. The Holm-adjusted p of the leading group is {float(p13['G_P']['holm_adjusted_p']):.3f}. The amendment variable is non-zero in 2.6% of the validation rows, from 60 of 754 symbols
(about six names per date).

Secondary contrasts (descriptive): the new block alone on the baseline adds {f(paired['S1'], 'mean_diff'):+.4f} ({paired['S1']['positive_folds']}/8 folds); the boosted learner's gain from the block is {f(paired['S3'], 'mean_diff'):+.4f}
(t {f(paired['S3'], 'hac_t'):.2f}, {paired['S3']['positive_folds']}/8). The unfitted 12-1 momentum rank, a pre-declared reference, has a Rank IC of {naive['mean_rank_ic']:.4f} (t {naive['hac_t']:.2f}) and a net Sharpe of
{naive['portfolio_b1_10bp']['b1_net_sharpe_10bp']:+.2f} in the frozen portfolio at 10 bp; the rich ridge set with the block (A5) has {arm_mean('A5', 'b1_net_sharpe_10bp'):+.2f}, and the boosted arms about
{arm_mean('G1', 'b1_net_sharpe_10bp'):+.2f}.

## 5. Discussion

The registered rule supports T1: six disclosure-process columns add measurable ordering information to a ridge model of fundamentals, and a version of the same columns scrambled across firms does not. Four features of
the evidence argue against reading more into it. The gain is absent in the two most recent validation years. A one-year shift of the columns, which preserves a firm's slow-moving profile but breaks its timing, keeps about
half of the gain (the margin over that placebo is {f(paired['C2'], 'mean_diff'):+.4f}, t {f(paired['C2'], 'hac_t'):.2f}), so a persistent firm trait probably carries much of it. The boosted model, which is the
stronger learner here by a wide margin, gains nothing measurable, and the frozen portfolio does not improve. Finally, the realised standard errors were larger than the registered sensitivity analysis assumed (1.9 times for T1),
so the T1 effect sits near the smallest detectable one, where estimates tend to overstate. The failure of T2 and the non-significance of T3 are weak evidence against moderation and for the timeliness literature respectively:
the tests had little power.

The attribution check changes the reading. The registered expectation was that the composite and lateness deterioration would carry the gain and the amendment count almost none; the opposite held. The filing-process ranks
carry about {(ic13['C_P'] - ic13['B1']) / gain13:.0%} of the gain and their removal loses about {(ic13['B5'] - ic13['D_P']) / gain13:.0%}, chiefly through the amendment count, which is zero in 97% of rows. That puts the result close to
the literature on restatements and later returns (Palmrose et al. 2001; Hribar and Jenkins 2004), and it rests on a few dozen firm-episodes: the date-level standard errors used here do not account for clustering by firm, so
the evidence is thinner than the t-statistic suggests. A firm-level analysis is the necessary next step.

What the study does show is that the construction is sound and cheap, that a preregistered placebo-controlled test of this kind is feasible on public data, and that a small linear-model gain can coexist with no gain for the
model that matters. It does not show a mechanism: an amendment is not a restatement, and nothing here separates a correction effect from the characteristics of firms that amend.

## 6. Limitations

A single, narrow universe of liquid names, where amendments and late filing are rare, and an effect that rests on about sixty firms; folds reused by many earlier experiments; a registry that holds only filings with financial statements (late-filing notices and
non-reliance events are absent); price data of unreviewed licence; no full-text reading of the closest literature; economics reported as exploratory only; and a ridge-centred test of an incremental block, which cannot
find nonlinear moderation.

## 7. Conclusion

An exploratory, preregistered test finds a small, time-unstable, linear-model gain from point-in-time disclosure-process variables and no gain for gradient boosting or for the frozen portfolio. It does not justify a
claim of new alpha or a change to any production score. A separately registered attribution check traced the gain to the count of recent amendments, a rare event. It justifies one event-level, firm-clustered analysis and, if the owner chooses, one frozen look at data not used to design the study.

## Declarations (to be completed by the owner)

- **Preregistration.** `docs/EXP_012_PREREGISTRATION.md`, committed and pushed before the run (commit `{manifest['registration_commit'][:12]}`); the attribution study is `docs/EXP_013_PREREGISTRATION.md` (commit `{m13['registration_commit'][:12]}`). Not an independent registry.
- **Data and code availability.** SEC filing data are public records; the reliability table can be rebuilt from them in seconds (`09_REPRODUCIBILITY_PLAN.md`). The price panel's community source has unreviewed terms and is not
  redistributed. Code, tests, manifests and results are in the repository's research branch.
- **Competing interests.** The author develops the OmniSignal platform to which the research is applied.
- **Funding.** None declared.
- **Use of automated tools in the research and in preparing this text.** [To be completed by the owner, truthfully and as the target journal's policy requires; see `10_JOURNAL_POSITIONING.md`. The repository's rule against
  naming tools as authors does not govern a journal declaration.]

## References

{references}
"""
    out = BASE / "manuscript"
    out.mkdir(exist_ok=True)
    (out / "draft.md").write_text(doc)
    print("written", len(doc), "characters")


if __name__ == "__main__":
    main()
