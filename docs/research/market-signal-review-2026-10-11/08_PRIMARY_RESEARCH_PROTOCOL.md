# Primary research protocol (pointer and summary)

The binding text is **`docs/EXP_012_PREREGISTRATION.md`**. This page summarises it for a reader of the review and records the two protocols kept on file. If the two ever disagree, the preregistration
governs; it embeds a content fingerprint of the definition and of twelve method files, and the run refuses to start if either has changed since the commit that registered it.

## Question and hypotheses

*Does the reliability of the filings behind a fundamentals-based signal carry information about cross-sectional returns, directly or as a moderator, once the information set is otherwise held fixed?*

| Test | Contrast (mean Rank IC difference, paired by date) | Falsified when |
|---|---|---|
| T1 | A5 - A1: the new reliability block added to the rich set | the difference is not positive after Holm adjustment, in fewer than 6 of 8 folds, or either placebo matches it |
| T2 | A6 - A5: fundamentals x unreliability interactions added to the main effects | same |
| T3 | A1 - A2: the two reliability variables already in the rich set (`filing_lag_days`, `days_since_report`) | same |

Five controls (permuted-across-firms and shifted-by-252-sessions placebos built from the same variables) bound the three tests; three secondary contrasts are descriptive and carry no claim.

## Design in one view

- Fixed from earlier registered work: panel `ds-richpit-ff3d3f556488b7da` (139,292 name-dates, 2014-04-03 to 2025-05-09), label `fwd_rank_21`, the eight recorded folds, ridge alpha 10, boosted settings frozen in EXP-010A, the 21-session portfolio at 10 bp.
  Nothing is tuned.
- New: four disclosure-process variables built point in time from the SEC filing registry, their cross-sectional ranks, a composite `rel_u`, and 48 interactions. Fourteen arms, 30 fits (24 ridge, 17 of them placebo, and 6 boosted).
- Inference: Newey-West (4 lags) one-sided p on the paired mean difference, Holm across T1 to T3, moving-block bootstrap interval (block 6, 4,000 draws, seed 20261012), fold signs, a mapped placebo for each test.
- Gates before any contrast is computed: A0 and A1 reproduce EXP-011's E0 and E1 to 1e-9; all predictions finite; no date after 2025-05-09; the reliability table matches its manifest; parent artifacts and holdout guard verified.
- Protected: EXP-006 and EXP-007 results, artifacts, cost assumptions, folds, holdout, selection contract and promotion status are untouched. The holdout is sealed and is not opened.
- Output: `experiments/EXP-012/` with a manifest, per-arm and paired tables, and two reloadable research artifacts (A1 and A5) marked as not for production.

## What the design can and cannot say

It can say whether these four variables add measurable ordering information on about 250 liquid US names over 404 dates, with a noise floor measured in a no-signal rehearsal. It cannot say anything about smaller firms (where
amendments and late filing are commoner), other markets, the holdout, or trading profit after costs (economics are reported as exploratory). Its sensitivity is stated in section 8 of the preregistration, and the expected outcome
(most likely NOT_SUPPORTED on T1 and T2) is declared there before the run.

## Protocols on file, not registered

**C. Revision look-ahead audit (first alternative).** Question: how much of a machine-learning ranker's measured edge disappears when every fundamental is the value as originally reported rather than as later
restated? Design: two otherwise identical pipelines on the same folds, one trained and scored on as-originally-reported values, one on latest-vintage values; the quantity of interest is the IC gap and its dependence on
restatement frequency. Needs original-versus-latest values per (firm, period, tag); the curated SEC facts appear to hold them but this has not been verified. Not started.

**P. Prospective provider-health log.** Question: does disagreement between vendors, or staleness of a vendor field, carry information about the reliability of a score? No history exists, so the only honest route is
to log (timestamp, provider, field, value, hash) from now on, define the analysis and a minimum sample before looking, and test after enough months have accrued. It changes production (a logging path), so it needs the owner's
decision and a review of each provider's licence. Not started.

## Status

Registration commit, branch and remote verification: `RESEARCH_STATE.md` and the final report. The study is run once, in full, after the registration is pushed; there is no optional stopping.
