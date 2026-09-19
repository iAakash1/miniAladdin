# OmniSignal versus the literature

## Feature and method map

| Literature capability | Local data | Feature/pipeline status | EXP-006 status | Post-EXP-009 evidence / decision |
|---|---|---|---|---|
| Price/momentum/reversal | Strong PIT OHLCV | Implemented | Used | Keep as control |
| Liquidity/volatility | EOD volume; no equity quotes | Implemented | Used | Keep; cost model still assumed |
| Fundamental quality/accruals/growth | Local statements | Implemented behind announcement gate; restatements unknown | Not used; EXP-005 arm hurt IC | Conditional only after SEC vintaging |
| Analyst EPS/sales revision momentum | 7.06m weekly PIT consensus rows each | 4/13-week revision, dispersion, coverage implemented and PIT-tested | Not used; EXP-005 estimate arm IC 0.0229 | **Tested, null:** EXP-009C ΔIC −0.0099 on evaluable folds; do not carry forward |
| Analyst-level stickiness/recommendations/targets | Not present | Not computable | Not used | Deferred pending licensed individual forecasts |
| Earnings surprise/SUE/PEAD | Actual/estimate + calendar since 2020 | Surprise, SUE, sign, days-since implemented with session alignment | Not used; EXP-005 fundamental arm IC 0.0124 | Medium; short coverage and event ablation only |
| Guidance | No structured PIT archive | Missing | Not used | SEC 8-K future acquisition |
| Option IV/rank/skew/term | Aggregate local history since 2019 | Eight features implemented | Not used; EXP-005 options arm IC 0.0275 | Low priority after negative incrementality/mixed literature |
| Put/call volume, OI, dealer positioning | Absent from local schema | Not computable | Not used | Requires paid contract data; defer |
| Insider purchases | Not normalized | Missing | Not used | Feasible SEC Form 4 later |
| 13F institutional changes | Not normalized | Missing | Not used | Feasible but 45-day lag and quarterly cadence lower priority |
| Short interest/borrow cost | Missing | Missing | Not modeled | Borrow/cost data valuable but commercial |
| Filing text/change | Live filings exist; no research corpus | Missing from frozen research | Not used | Medium after timestamped 8-K/10-Q/K corpus |
| Sector/size/beta neutralization | PIT sector/size master absent | Not implemented in frozen model | Absent | High research value, data prerequisite |
| Rank-aware loss | Target is rank, estimator loss is point regression | Implemented as two controlled rankers | Absent | **Tested, null:** LambdaMART and pairwise failed ordering criteria; no ranker retained |
| Target ordinalization/residualization | Raw CS rank only | Alternatives documented, not run | Raw `fwd_rank_21` | High, but each target is a trial |
| Turnover-aware construction | Portfolio optimizer exists | Top-k dropout, hysteresis and minimum-hold rules tested | 20.15x turnover | **Confirmed:** 10% top-k dropout cut turnover 66% to 6.90x and net Sharpe rose to +0.390 at 10 bp; freeze as portfolio layer |
| Prediction uncertainty/abstention | Confidence exists in product, not research policy | No OOS selective portfolio | Absent | Medium after calibrated OOS uncertainty design |
| Graph relations | Sector only in product payload; no PIT research graph | Absent | Absent | Low until relationship data exists |
| Multimodal text+numeric | No licensed PIT text archive | Absent | Absent | Defer; avoid confounding initial EXP-009 |

## What the gap is—and is not

The selected model underuses the available feature store, but EXP-005 already
showed that naive additive arms reduced IC. The evidence therefore does not
support “turn on all 57 features.” It supports a smaller question: can one
PIT-clean family with plausible incremental information survive an isolated
ablation under an objective and portfolio rule aligned to selection economics?

The largest missing prerequisite is a PIT security master with stable identity,
industry, size and reliable exits. Objective alignment is **not** the largest
model gap anymore: EXP-009B rejected the tested ranking losses. Turnover was the
largest measured economic gap and top-k dropout addressed it, but the remaining
information content is weak. The best new-data opportunity is an SEC
as-reported characteristic panel, not another model on the current 26 features.

## Candidate sequence

1. Preserve EXP-008 and EXP-009 exactly as registered/executed; do not rewrite
   them after observing results.
2. Preregister **EXP-010A**, ten seeds of the frozen 26-feature tree + top-k
   dropout, to measure the noise floor.
3. Preregister **EXP-010B**, 5d versus 21d cadence on frozen predictions, after
   EXP-010A is complete.
4. Build the PIT security master and SEC as-reported numeric facts as data
   products, with no performance selection during construction.
5. Run **EXP-011** as base versus base+PIT-data ablations with regularized
   linear and conservative boosted-tree models. Hold portfolio construction
   fixed. Add neural/text/options work only through later, separately registered
   studies if the richer data first demonstrates stable signal.
