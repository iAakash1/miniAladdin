# Simulated peer-review panel

**What this is.** A structured self-critique in the form of three referee reports and an editor's letter, written after the registered study (EXP-012) returned, to find the weaknesses a real panel would find
before one does. It is not an independent review and carries no evidential weight: the "referees" are perspectives adopted by the author of the package, they share its information, and they were written knowing the
design and the result. Real referees will see things these miss. Each concern is answered with what the package already contains, what it concedes, or what would have to be done.

**Object under review.** The research package in this folder and the registered study EXP-012: a literature review with a stated coverage; a novelty audit; a point-in-time construction of four disclosure-process
variables from the SEC filing registry; and a preregistered, placebo-controlled test. Result in one line: T1 SUPPORTED (+0.00515 Rank IC, Holm p 0.011, 6 of 8 folds, negative in the last two), T2 and T3 NOT_SUPPORTED
(`docs/EXP_012_RESULTS.md`).

---

## Referee 1 - empirical asset pricing

**Summary.** The paper asks whether the reliability of the filings behind fundamentals signals matters for the cross-section. The design is careful, but the question is old, the new variables are close to
constant, the universe is 250 liquid names, and the one supported test is small and fades at the end of the sample.

**Major concerns**

1. *Novelty.* Reporting lag and return predictability are published (Bannouh et al. 2019; Brooks et al. 2023); information uncertainty as a moderator is twenty years old (Zhang 2006; Francis et al. 2007).
   **Answer:** conceded in the registration and in the audit (novelty low to medium). The package claims a construction and a test, not an idea.
2. *Out-of-sample stability.* The T1 gain is negative in the last two validation years (-0.0121, -0.0007) and the rule's six-of-eight requirement is met exactly. A signal that fades at the edge of the sample is the
   signal most likely to be gone. **Answer:** reported prominently; no claim of persistence is made. The sealed holdout is the right place to look and was deliberately not used.
3. *Multiple looks.* Eight folds used by six earlier experiments and 1,029 trials on the ledger; Holm adjusts for three tests only. **Answer:** the study is labelled exploratory, and the results document says "a lead,
   not a finding". An adjustment for the program's whole history is not computable.
4. *Economic significance.* A gain of 0.005 Rank IC does not reach the frozen portfolio (A5 -0.49 net Sharpe at 10 bp against A1 -0.34; the unfitted 12-1 momentum rank +0.39). **Answer:** reported; economics are
   exploratory by design. The honest reading is that Rank IC differences of this size are not tradeable in this portfolio.
5. *The strongest model does not need it.* Boosting gains nothing (+0.0015, t 0.77) and is far stronger in level (0.033 against 0.020). **Answer:** conceded; the result concerns the linear model only.
6. *Odd ordering.* The baseline plus the block (A4, 0.0222) beats the rich set plus the block (A5, 0.0200), and the block alone adds more to the baseline (+0.0168) than the 50 SEC characteristics do (+0.0096).
   **Answer:** not explained by this design. It suggests ridge gains little from the 50 characteristics, and that part of the block's value is a re-expression of information already in the features (it contains the
   existing lag and staleness variables). The attribution check (EXP-013) has since shown that the composite adds nothing and the amendment-based ranks carry the gain, which explains part of the pattern
   (the composite is where the re-expressed information sat) but not why the baseline plus the block beats the rich set plus the block; that remains unexplained.

## Referee 2 - accounting and disclosure

**Summary.** The disclosure variables are interesting but crude. An amendment in the Financial Statement Data Sets is a re-filed financial report; the interesting events (non-reliance 8-Ks, late-filing notices,
restatement taxonomy) are absent. Three of the four variables are almost constant.

**Major concerns**

1. *Measurement validity.* `amended_730` is non-zero in 3.5% of rows and `latest_report_amended` in 0.2%; many amendments are Part III or exhibit-only and are not in the data; "big R" and "little r" restatements are not
   distinguished. **Answer:** conceded in the data quality report; the registration does not claim to measure restatement severity. The result therefore says little about amendments themselves.
2. *What carries the effect.* In the final A5 model the composite and lag deterioration have the largest coefficients of the block (3rd and 4th of 82 in absolute size); the amendment variables rank 18th
   (`amended_730`) and 47th (`latest_report_amended`). **Answer:** that reading was wrong. EXP-013 (same folds, separately registered) found that the four filing-process ranks carry the gain, chiefly the amendment count (alone
   +0.0024, t 2.50), while the composite adds nothing; the registered prior expectation was the opposite. Coefficients of a collinear ridge model are not a guide to out-of-sample contribution.
3. *Confounding.* Late filers are small, distressed or recently restating; reliability may proxy size and distress, which the panel handles only through liquidity and volatility features (size and industry controls were
   withheld because the security master is not point in time). **Answer:** a real limitation, stated; the permutation placebo shows the link to the firm matters, not that it is *reliability*.
4. *Timing versus trait.* A one-year shift keeps about half of the gain. **Answer:** reported (C2: +0.0024, t 1.28). The variables are slow-moving, so the shifted placebo is a demanding control and also a weak test of
   timing; the honest conclusion is that a persistent firm profile probably carries much of the effect.

## Referee 3 - statistics and machine learning

**Summary.** The pipeline is leakage-aware, multiplicity is limited, the noise floor is measured. But the decision rule is lenient, and the registered sensitivity statement was wrong in an instructive way.

**Major concerns**

1. *The decision rule is lenient.* SUPPORTED requires only that each mapped placebo has a *positive* mean difference, not a significant one. The shifted-placebo margin here is +0.0024 with t 1.28. A stricter rule (a
   significant margin) would have returned FRAGILE or NOT_SUPPORTED. **Answer:** the rule was registered and is applied as registered; the results document says plainly that the time-varying part is not shown to be significant.
   A stricter rule should be used in any confirmatory follow-up.
2. *Sensitivity miscalibrated.* The registration derived standard errors from a label-shuffled rehearsal; with the real label they were 1.9 times larger for T1 and 8 times for T3. The T1 effect therefore sits near the smallest
   detectable one, where estimates are inflated (winner's curse). **Answer:** disclosed in section 7 of the results document; the registered verdicts are unchanged, the interpretation is.
3. *Reuse of folds and of the holdout question.* **Answer:** as above; the holdout is untouched, and opening it would be an owner decision for one frozen design.
4. *Inference with overlapping labels.* A 21-session label on a 5-session grid. **Answer:** Newey-West (4 lags) and a moving-block bootstrap with block 6, as in the earlier experiments; both agree on T1 (interval
   [+0.0012, +0.0091]).
5. *Placebo design.* Permutation across firms destroys the cross-sectional link but keeps each date's marginal distribution; the shift keeps firm persistence and breaks timing. They answer different questions, and the
   results differ accordingly (C1 strongly significant, C2 not). **Answer:** both were registered; reading them together is what the results document does.
6. *Moderation and model class.* Ridge with 48 interaction terms is a crude test of moderation (T2 -0.0036, 1 of 8 folds), and low power (smallest detectable effect about 0.006 to 0.007) makes it weak evidence. **Answer:**
   conceded.
7. *Reproducibility.* The price data cannot be redistributed. **Answer:** conceded; the SEC-derived part is reproducible by anyone.

8. *Rare events and clustering (raised by EXP-013).* The amendment count is non-zero in 2.6% of validation rows, from 60 firms, about 6 names per date; the ten most frequent symbols hold 39% of flagged rows. The date-level
   Newey-West statistic ignores clustering by firm, and each amendment is visible for 730 days, so the number of independent episodes is a few dozen. **Answer:** reported prominently; no firm-level inference has been done. This is the
   first thing a real referee would ask for, and the next study should be built around it (leave-one-firm-out, firm-clustered errors, event windows).

## Editor's letter

The question is incremental and the design is more careful than the question deserves. The single supported test is small, fades at the end of the sample, holds for the linear model only, and rests on a lenient
decision rule; the registered power statement was optimistic. The package is honest about all of this. Conditions for a revision to be considered: (i) a separately registered event-level analysis of the amendment effect (firms, episodes, clustering), with a stricter placebo criterion; (ii) novelty claimed modestly and the closest works read in full; (iii) one frozen look at data not used in the design, if the owner is willing to open it;
(iv) the scope statement (liquid US names; filings with financial statements only; community price data) in the abstract. Decision on the package as it stands: **major revision before any submission**; as a
preregistered internal study: **accept**, with the limitations above stated in any report of the result.
