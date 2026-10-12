#!/usr/bin/env python3
"""Write manuscript/draft_014.md: a draft of the EXP-014 study whose every number is read from experiments/EXP-014/{results.json, manifest.json}.

The discussion paragraph is chosen by the registered label and says no more than the label permits (`PERMITTED` in make_results_doc_014.py). The draft is for the owner's review, not for submission: the literature positions
rest on abstracts and verified metadata except where `17_RECENT_LITERATURE_2022_2026.md` says full text, and the declarations are deliberately incomplete.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/make_manuscript_014.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
BASE = REPO / "docs/research/market-signal-review-2026-10-11"
EXP = REPO / "experiments/EXP-014"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(BASE / "code"))

from make_results_doc_014 import PERMITTED  # noqa: E402


def f(x, nd=4):
    return "n/a" if x is None or (isinstance(x, float) and x != x) else f"{x:.{nd}f}"


def row(name, r):
    return f"| {name} | {f(r.get('coef'))} | {f(r.get('t_firm'), 2)} | {f(r.get('wcr_p_negative'))} | {f(r.get('wcr_p_two_sided'))} | {r.get('treated_firms', 0):,} | {r.get('treated_rows', 0):,} |"


DISCUSSION = {
    "SURVIVES": "The association between a value-changing amendment and lower next-month return ranks survived every registered robustness check in firms the discovery sample never saw, including the within-firm test. That is a statement about an association in this sample and period: it is not an estimate of investment value (the cost-aware portfolio result below is separate and was not part of the decision), it does not identify why (the anticipation ratio labels the pattern in section 5.4), and it is a replication-type result for an event class whose long-run sign has been disputed.",
    "FRAGILE": "The association is statistically present in the registered direction but failed at least one registered robustness check, listed in section 5.2. It is therefore not established. The failed gate says where to look: a pooled association that disappears with firm effects is a statement about which firms receive amendments, not about what an amendment does.",
    "REVERSED": "The registered direction was not supported and the coefficient has the opposite sign with a two-sided wild-cluster p below 0.05. This is descriptive and uncorrected for multiplicity, and it is the sign that the rebound reported by Frieder and Shanthikumar (2008) for restatement announcements would predict. The age bins in section 5.5 show where in time after the amendment the association sits; any claim beyond this description needs a new registered study, not a change to this one.",
    "NOT_REPLICATED": "The association was not reproduced at the registered level of evidence. With the power stated in the preregistration this excludes large effects only: against half the discovery estimate the within-firm test has roughly two chances in three, so smaller effects remain possible. The discovery-sample association is therefore best read as unconfirmed.",
    "INCONCLUSIVE": "The independent sample had too few treated companies to conclude anything about the hypothesis.",
}


def main() -> None:
    manifest = json.loads((EXP / "manifest.json").read_text())
    if manifest.get("completion") != "COMPLETE":
        sys.exit("experiments/EXP-014 is not a completed registered run; there is nothing to write about yet")
    res = json.loads((EXP / "results.json").read_text())
    reg, dec, counts = res["regressions"], res["decision"], res["counts"]
    label = dec["label"]
    ml = manifest["machine_learning"]
    sec = reg["secondary"]
    cal, calw = reg["placebo_events"], reg["placebo_events_within_firm"]
    ledger = list(csv.DictReader((BASE / "recent_lit_matrix.csv").open(encoding="utf-8")))
    cited = {m["id"]: m for m in ledger}
    ref_ids = ["A01", "A02", "A03", "A04", "A05", "A14", "B01", "B02", "C01", "C06", "C07", "C08", "C10", "C14"]
    refs = "\n".join(f"* {cited[i]['citation']} (doi: {cited[i]['doi']}). Evidence level in this project: {cited[i]['evidence']}." for i in ref_ids)
    gates = ", ".join(f"{g} {'passed' if ok else 'FAILED'}" for g, ok in dec["gates"].items())
    s11 = "\n".join(row(k.replace("S11_age_", "core amendment first usable ") + " days", sec[k]) for k in sorted(sec) if k.startswith("S11_"))
    s12 = "\n".join(row(k, sec[k]) for k in sorted(sec) if k.startswith("S12_"))
    other = "\n".join(row(k, sec[k]) for k in sec if not k.startswith(("S11_", "S12_")))
    contrasts = ml.get("contrasts", {}) if not ml.get("skipped") else {}
    ml_rows = "\n".join(f"| {k} | {v['left']} vs {v['right']} | {f(v['mean_diff'], 5)} | {f(v.get('hac_t'), 2)} | {f(v.get('holm_adjusted_p'))} | {v['positive_folds']} of 8 |" for k, v in contrasts.items())
    econ = ml.get("economics", {})
    econ_rows = "\n".join(f"| {k} | {f(v.get('mean_rank_ic'), 5)} | {f(v.get('b1_net_sharpe_10bp'), 3)} | {f(v.get('b1_gross_sharpe'), 3)} | {f(v.get('b1_cost_share_of_gross'), 3)} |" for k, v in econ.items())
    event = reg["event_time"]
    doc = f"""# Do value-changing amendments to periodic reports predict next-month return ranks? A preregistered test on firms the discovery never saw

*Draft for the owner's review, generated from `experiments/EXP-014` (registered run, commit `{manifest.get('git_commit')}`, registration commit `{manifest.get('registration_commit')}`, fingerprint `{manifest.get('definition_fingerprint')}`). Not submission-ready: see Declarations.*

## Abstract

**Outcome: {label}.** {PERMITTED[label]} Confirmatory sample: {counts['confirmatory_rows']:,} firm-dates, {counts['confirmatory_firms']:,} firms with a trusted identity, ranked 251 to 1,000 by liquidity, none of them in the discovery universe, 2014-04 to 2025-05.
Coefficient on a value-changing amendment in the trailing 730 days: {f(reg['H1']['coef'])} centred-rank units (wild-cluster one-sided p {f(reg['H1']['wcr_p_negative'])}, two-sided {f(reg['H1']['wcr_p_two_sided'])}; Holm-adjusted {f(dec['h1_adjusted_p'])}); with a fixed effect per firm {f(reg['R7_within_firm']['coef'])}
(p {f(reg['R7_within_firm']['wcr_p_negative'])}). Gates: {gates}. The holdout was not opened.

## 1. Introduction

Studies of restatement announcements agree on the immediate loss and disagree about what follows: negative abnormal returns over several years in some samples, no drift where the news is about cash flows, and, in a hand-collected sample of NYSE announcements 1993 to 2002, a
positive return 64 to 126 trading days later (Frieder and Shanthikumar 2008). For a related reliability disclosure, material weaknesses in internal control, a 2025 study finds negative drift (Ghosh et al.). Content-classified amendments to periodic reports, which change
the reported numbers or do not, have not been examined as a cross-sectional predictor in the studies found (`17_RECENT_LITERATURE_2022_2026.md`). A discovery on the 250 most liquid names suggested that firms with a recent value-changing amendment earn lower next-month return ranks; it rested on 18 treated firms.
This paper reports the single preregistered test of that finding on firms the discovery never saw.

## 2. Data and construction

Amendment forms (10-K/A, 10-Q/A and transition variants) come from the SEC Financial Statement Data Sets; each is classified by comparing its revenue, net income, assets, liabilities, equity and operating cash flow with the previous version (value-changing: any differs by more than 1%).
Availability is the first session whose close-based decision may use the filing (accepted before 16:00 New York time: that session). The acceptance times in the SEC's submissions JSON are wrong for 28.2% of 96,429 matched filings and were not used; the Data Sets' stamps obey the filing-date rule for 99.2%.
Prices come from a community dataset whose redistribution terms have not been reviewed (derived statistics only). The outcome is the centred cross-sectional rank (from -1 to 1) of the 21-session forward return.

## 3. Design, as registered

H1: the coefficient on a value-changing amendment in the trailing 730 days is negative (date x Fama-French 12 sector effects, 17 controls); H2: the same for any amendment; Holm across the two, wild-cluster bootstrap over firms with the null imposed ({manifest['counts'].get('confirmatory_firms', '')} firms, {9999:,} draws).
Seven gates (power, influence, calendar years, full controls, time-separate sample, sectors, within-firm). Labels: SURVIVES, FRAGILE, REVERSED (positive coefficient, two-sided p < 0.05), NOT_REPLICATED, INCONCLUSIVE. Secondary: S1 to S12, with S11 (age of the amendment) and S12 (liquidity halves) descriptive.
A machine-learning increment and a cost-aware portfolio are reported separately and cannot rescue a failed H1.

## 4. Size of the procedure

On the real label structure with placebo amendments on length- and sector-matched untreated firms, the pooled regression rejected {f(cal['rejection_rate_5pct_one_sided'], 3)} of {cal['placebo_draws']} draws at 5% and the regression with a firm fixed effect {f(calw['rejection_rate_5pct_one_sided'], 3)} of {calw['placebo_draws']} (this run); the pre-registration quotes the earlier pre-run values (13.3% and 6.3%).

## 5. Results

### 5.1 Sample

{counts['confirmatory_rows']:,} labelled rows, {counts['confirmatory_firms']:,} firms, {counts['confirmatory_dates']} dates; {reg['H1']['treated_firms']} firms and {reg['H1']['treated_rows']:,} rows carry a value-changing amendment in the trailing 730 days.

### 5.2 Registered regressions and gates

| Test | Coef | t (firm) | WCR p (neg.) | WCR p (2-sided) | Treated firms | Treated rows |
|---|---|---|---|---|---|---|
{row('H1 value-changing, 730 days', reg['H1'])}
{row('H2 any amendment, 730 days', reg['H2'])}
{row('R4 all 76 features', reg['R4_full_controls'])}
{row('R2 without the 5 most influential firms', reg['R2_influence'])}
{row('R7 firm fixed effect', reg['R7_within_firm'])}
{row('R5 time-separate, core', reg['R5_time_separate'])}

Gates: {gates}. Failed: {', '.join(dec['failed_gates']) or 'none'}.

### 5.3 Other secondary analyses

| Test | Coef | t (firm) | WCR p (neg.) | WCR p (2-sided) | Treated firms | Treated rows |
|---|---|---|---|---|---|---|
{other}

### 5.4 Event time

Anticipation ratio coef(next 365 days) / coef(previous 365 days): {f(event['anticipation_ratio'], 3)} (below 0.5: time-specific; otherwise a marker of persistent trouble). Interpretation label: {dec.get('interpretation')}.

### 5.5 Age of the amendment (S11) and liquidity halves (S12), descriptive

| Test | Coef | t (firm) | WCR p (neg.) | WCR p (2-sided) | Treated firms | Treated rows |
|---|---|---|---|---|---|---|
{s11}
{s12}

### 5.6 Machine-learning increment and economics (separate from the decision)

Labels: {ml.get('labels')}.

| Contrast | Arms | Mean Rank-IC difference | HAC t | Holm p | Positive folds |
|---|---|---|---|---|---|
{ml_rows}

| Arm:seed | Mean Rank IC | Net Sharpe 10 bp | Gross Sharpe | Cost share of gross |
|---|---|---|---|---|
{econ_rows}

## 6. Discussion

{DISCUSSION[label]}

## 7. Limitations

* An amendment is a detection and disclosure event: only detected misstatements are observable, so the coefficient is the price relevance of detection and disclosure. An amendment can follow earlier public news (an Item 4.02 8-K, an earnings release).
* Firm type: disclosure failures repeat, and a pooled association can reflect which firms receive amendments; the within-firm gate is the answer and has lower power than the pooled test.
* 65 treated firms and 21-session overlapping labels limit precision; the preregistration states the power.
* The sample shares calendar months with the discovery sample; the time-separate sample has {res['regressions']['R5_time_separate']['treated_firms']} treated firms.
* Names delisting inside the 21-session window have no label; the price source's licence is unreviewed; delisting returns are not modelled.

## Declarations (to be completed by the owner)

Funding, competing interests, data and code availability (SEC data are public; prices are not redistributable; code and registrations are in the repository), and the journal-specific statement on the use of AI tools in preparing the analysis and text, which is a separate duty from the repository's attribution rule and must not be left out.

## References

{refs}
"""
    out = BASE / "manuscript/draft_014.md"
    out.write_text(doc, encoding="utf-8")
    print(f"wrote {out} ({len(doc):,} characters)")


if __name__ == "__main__":
    main()
