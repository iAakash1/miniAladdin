# EXP-009 final analysis — what fixed EXP-006, what did not, and what mattered

Date: 2026-09-19. Everything here is **EXPERIMENTAL — PROMOTION NOT ASSESSED**. The sealed holdout
(recorded 2025-08-28 → 2026-08-28 in the contract; 2025-08-26 → 2026-08-26 in EXP-006's own plan, so the
program sealed the widest window) was **never read, scored or used for any decision**; every manifest records
`holdout.touched: false` with 0 firewall breaches. Nothing is promoted; production models remain zero. Per-study
detail is in `docs/EXP_009_RESULTS.md`; the verification of the literature is in
`docs/DEEP_METHOD_RECONSTRUCTION.md`; the data audits are in the five `*_FORENSICS` / `*_PLAN` documents.

## 1. The research story, stated once

**EXP-006 found a weak but statistically detectable cross-sectional ranking signal — mean Rank IC 0.029, Newey-West
t 2.66 — that failed economically.** Gross Sharpe 0.384 became **net −0.102** at a 10 bp half-spread, because the
book traded **20.15x a year one-way** (about 40% of each leg replaced every week; 3.4 round-trip turns a month), cost
**126.6% of the gross return**, and the gross edge per unit traded (12.8 bp) was below the cost per unit traded (16.2 bp).
The six-factor alpha t-statistic was 0.047. **The failure had two ingredients — weak information and extreme
turnover — and EXP-009 tested the two separately**: A cuts turnover without touching the model; B changes the
model's objective without touching the portfolio rule; C adds information without touching either.

## 2. The decomposition

```
EXP-006     baseline predictor + immediate replacement
            gross Sharpe 0.384 | net -0.102 | turnover 20.15x | cost share 127% | break-even spread 6.6 bp
   │
   ▼  EXP-009A   the SAME predictions; only the portfolio construction changed
   │            Effect: TURNOVER / COST
   │            top-k dropout (10%): turnover 6.90x (-66%) | net Sharpe +0.390 (paired Δ +0.49, 95% CI +0.21…+0.84)
   │            cost share 28% | break-even 50 bp | max DD -14.3%
   │            → MECHANISM_CONFIRMED (the only cell of four to meet all criteria)
   ▼
   ▼  EXP-009B   the SAME data, folds, features and portfolio rule; only the model OBJECTIVE changed
   │            Effect: MODEL OBJECTIVE
   │            LambdaMART  ΔIC -0.0139 (t -1.1)  net Sharpe -0.32 (control +0.46) → NO_ORDERING_GAIN
   │            pairwise    ΔIC +0.0001 (t +0.03) net Sharpe +0.30 (control +0.46) → NO_ORDERING_GAIN
   │            → no ranker retained; BASE stays the sklearn point-regression baseline
   ▼
   ▼  EXP-009C   the frozen method; only the INFORMATION changed (8 PIT analyst features)
   │            Effect: INFORMATION / DATA
   │            evaluable folds 3-7: ΔIC -0.0099 (t -0.75); 2/5 folds better; net Sharpe -0.23 (CI -1.31…+0.33)
   │            → ANALYST_NO_RELIABLE_VALUE
   ▼
   ▼  EXP-009D   hygiene: remove the exact duplicate feature axis  →  EQUIVALENT (within reseed noise)
   ▼
   FROZEN OUTCOME   sklearn gradient boosting + 27 features + top-k dropout: net Sharpe +0.390 at 10 bp,
                    with a deflated-Sharpe probability of 0.24 and a factor-alpha t of 1.34
```

| Step | What changed | Net Sharpe at 10 bp (top-k dropout unless stated) | Effect established? |
|---|---|---:|---|
| EXP-006 | baseline, immediate replacement | −0.102 | — |
| **EXP-009A** | portfolio rule | **+0.390** (vs −0.102) | **Yes, for cost**: turnover −66%, cost share 127% → 28%. The gross effect (+5 bp/period, HAC t 0.89) is **not** significant |
| EXP-009B | ranking objective (two rankers vs matched control) | +0.295 (pairwise) / −0.324 (LambdaMART) vs control +0.457 | **No**: no ordering gain; the control itself moves +0.067 Sharpe and +0.003 IC from a reseed |
| EXP-009C | analyst information | 0.335 vs 0.390 (full sample); −0.23 on the evaluable folds | **No** |
| EXP-009D | duplicate axis (27 → 26 features) | +0.406 (vs +0.390; a reseed gives +0.338) | **None**: `EQUIVALENT`; ΔIC +0.0014 (t 1.15), inside a reseed's own movement. The 26-feature set is safe to use |

## 3. Which mattered most?

**A. Portfolio implementation mattered most — and it is the only one of the three that mattered at all.** Cutting turnover
by two thirds took the strategy from cost-dominated (break-even spread 6.6 bp, cost 127% of gross) to comfortably cost-
survivable (break-even 50 bp; net Sharpe positive at 20 bp). The mechanism is rank-buffered replacement — hold the
incumbent unless a better candidate exists — which the literature anchors (Novy-Marx & Velikov's sS rule; the public Qlib
top-k idea). Notably the **literature-anchored 20/40 buffer failed** (it cost about 30% of the gross edge); the bounded-
replacement rule and a horizon-matched minimum hold did not.

**B. A better ranking objective did nothing useful.** Neither ranking loss improved the ordering, and neither lowered
turnover. The published "threefold Sharpe" evidence is gross of costs, monthly, momentum-only and against weak baselines
(`DEEP_METHOD_RECONSTRUCTION.md`); on a matched, net-of-cost comparison it did not reproduce.

**C. Better data did nothing useful either.** The data passed every point-in-time audit, including a cross-table timing test
that the vintages line up with announcement dates, and still added no reliable information.

**The honest answer is therefore: portfolio implementation — and it fixed the *cost* problem, not the *information* problem.**
The signal's strength is unchanged: Rank IC is still ≈ 0.03, the gross Sharpe of the final book (0.54) is a point estimate
whose gain over 0.38 is not statistically significant and depends on one fold, and the cost fix, however large, cannot make a
weak signal strong. If the question is "what would you need to believe to run this book?", the answer is *that a 0.03 IC on
a 250-name liquid-US universe is real, persistent and tradable* — and the program has produced no new evidence for it.

## 4. Why the surviving result should be read cautiously

* **It rests on one period.** Fold 5 (2022-05 → 2023-05) supplies 54% of the top-k dropout gain (EXP-009A) and dominates the
  control's own net return (+56.7 bp/period) in EXP-009B. Excluding it, the controlled book's net Sharpe falls from 0.39 to 0.21
  (EXP-009A, exploratory).
* **The noise floor is comparable to most of the differences measured.** Changing only the bagging implementation moved mean
  Rank IC by 0.0031 and net Sharpe under top-k dropout by 0.067 (EXP-009B, R1 vs R0). Any single-fit comparison in the
  program carries that much noise; the frozen criteria (HAC, six-of-eight folds, block bootstrap) exist to stop it being read
  as signal, and are why the ranker and analyst results are nulls rather than "promising".
* **Multiple testing is real.** The cumulative count is 166 evaluations. The deflated-Sharpe probability of the best book
  is 0.24 (not significant); its six-factor alpha t-statistic is 1.34; four of eight folds are non-positive.
* **The cost model is an assumption.** Half-spread is assumed, impact is a square-root proxy, there is no borrow or
  short-availability cost, and every trade is at the rebalance close. The break-even spread of 50 bp is a statement about
  *these* assumptions.
* **One frozen prediction set, one universe, one sample.** The predictions were produced under EXP-006's specification;
  the improvements in EXP-009A came from a rule tried on the same data on which its parameters were *anchored* (from the
  literature, not fitted) but on which four cells were evaluated.

## 5. What failed, what is still open, and what to do next

**Failed / not supported:** the ranking objective (both cells); the analyst-revision features; the literature-anchored
hysteresis buffer; a claim that a stronger *model* is the missing ingredient.

**Not tried and not ruled out:** LightGBM/XGBoost implementations of lambdarank; a two-sided (both-tail) ranking
objective; more rounds for LambdaMART (it underfit under the frozen 200-round configuration: train IC 0.065); other
horizons or rebalance cadences (the label is 21 sessions but the book rebalances every 5 — a monthly cadence is the most
natural unexplored lever); earnings-event features (admissible from 2020 with the conservative timing rule; open
calendar-snapshot risk); sector/industry/size neutralisation (blocked by the missing point-in-time security master);
as-reported fundamentals (blocked until an SEC EDGAR vintage dataset exists); options (deprioritised on the evidence).

**The next research step, in order of expected value:**

1. **Do not promote anything on this evidence.** The final result is a cost-survivable version of a weak signal.
2. **Quantify the noise before comparing anything else:** repeat the frozen book over several seeds and report the
   distribution of net Sharpe; the +0.067 reseed shift is the scale to beat.
3. **Test the cadence lever once, preregistered:** rebalance every 21 sessions (the label horizon) under the same
   top-k rule; it attacks turnover from the other side and uses no new data.
4. **Build the PIT security master and the SEC as-reported fundamentals dataset** (`PIT_SECURITY_MASTER_PLAN.md`,
   `FUNDAMENTAL_PIT_REMEDIATION.md`) — data-engineering projects that must precede neutralisation or fundamentals
   experiments, and the only route to information that is not already exhausted by the price features.
5. **Reserve the sealed holdout for one frozen candidate** — a single definition (model, features, rule, cost
   assumptions), registered before it is opened, on explicit authorisation. It has not been opened here and this
   program has not selected such a candidate.

## 6. Governance record

| Item | State |
|---|---|
| Holdout | never read; `touched: false` in every manifest; firewall engaged, contract NOT ARMED |
| Promotion | none; EXP-006 remains not promotable; production models 0 |
| Preregistration before execution | EXP-009A `155e976`, EXP-009B `d633b1b`, EXP-009C `47d6f67`, EXP-009D `f5feb0e` — each pushed to `origin/main` before its run, each enforced by a gate that refuses to execute otherwise (tested against a real git repository) |
| Frozen after results | no threshold, hyper-parameter, relevance bin, portfolio rule, statistic or criterion was changed after any result; amendments: none |
| Trials | 166 cumulative evaluations counted for deflation |
| Literature | claims audited against primary sources; corrections recorded (`DEEP_METHOD_RECONSTRUCTION.md`); unverifiable items marked UNVERIFIED |
| Reproducibility | dataset `ds-491d761b9f2a6fc4`; the sklearn refit reproduces EXP-006's frozen predictions with max absolute difference **0.0** (checked in EXP-009B, -C and -D). Per-row predictions are gitignored by repository policy and regenerable from the recorded seed, dataset hash and commit; their sha256 are in each manifest |

### Notes on things found on the way

* The sealed-window dates differ by two sessions between `docs/HOLDOUT_CONTRACT.md` and `metrics.json`
  (2025-08-28) and EXP-006's recorded plan (2025-08-26). Every EXP-009B/C/D run sealed the earlier start; the
  last training-side date (2025-05-09) is 111 sessions before either, so no result is affected. The contract is hashed by the
  preflight and was not edited.
* The engine's `gross_total_return` metric is the arithmetic sum of period returns (the denominator of the cost share);
  EXP-006's saved figure is the compounded 0.4078 (the sum is 0.4115). New outputs name the two separately.
* Two rebalance dates have unusually thin cross-sections (2019-09-17: 174 names; 2020-02-17: 14 names, so the 10% weight
  cap bound and gross exposure was 0.6); every cell trades them as-is.
* The earnings calendar is a current snapshot that may store the *scheduled* rather than the *actual* announcement date;
  any earnings-event result must carry that caveat.
