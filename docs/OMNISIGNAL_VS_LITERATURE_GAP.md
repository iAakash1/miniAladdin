# OmniSignal versus the literature

## Feature and method map

| Literature capability | Local data | Feature/pipeline status | EXP-006 status | EXP-009 candidacy |
|---|---|---|---|---|
| Price/momentum/reversal | Strong PIT OHLCV | Implemented | Used | Keep as control |
| Liquidity/volatility | EOD volume; no equity quotes | Implemented | Used | Keep; cost model still assumed |
| Fundamental quality/accruals/growth | Local statements | Implemented behind announcement gate; restatements unknown | Not used; EXP-005 arm hurt IC | Conditional only after SEC vintaging |
| Analyst EPS/sales revision momentum | 7.06m weekly PIT consensus rows each | 4/13-week revision, dispersion, coverage implemented | Not used; EXP-005 estimate arm IC 0.0229 | High-feasibility focused revisit, not broad re-add |
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
| Rank-aware loss | Target is rank, estimator loss is point regression | Absent | Absent | High method candidate, separate EXP-009 |
| Target ordinalization/residualization | Raw CS rank only | Alternatives documented, not run | Raw `fwd_rank_21` | High, but each target is a trial |
| Turnover-aware construction | Portfolio optimizer exists | Frozen backtest uses immediate quantile replacement | 20.15x turnover | Highest economic priority; fixed buffer/no-trade candidate |
| Prediction uncertainty/abstention | Confidence exists in product, not research policy | No OOS selective portfolio | Absent | Medium after calibrated OOS uncertainty design |
| Graph relations | Sector only in product payload; no PIT research graph | Absent | Absent | Low until relationship data exists |
| Multimodal text+numeric | No licensed PIT text archive | Absent | Absent | Defer; avoid confounding initial EXP-009 |

## What the gap is—and is not

The selected model underuses the available feature store, but EXP-005 already
showed that naive additive arms reduced IC. The evidence therefore does not
support “turn on all 57 features.” It supports a smaller question: can one
PIT-clean family with plausible incremental information survive an isolated
ablation under an objective and portfolio rule aligned to selection economics?

The largest missing prerequisite is a PIT security master with sector, size,
beta inputs and reliable delistings. The largest model gap is objective
alignment. The largest measured economic gap is turnover. The best new-data
opportunity is not another vendor bundle; it is improving provenance of data
already stored and adding timestamped SEC events.

## Candidate sequence

1. Complete the frozen EXP-008 as registered.
2. Establish a PIT security master and remove only the exact duplicate feature.
3. Preregister EXP-009 as a small staged study, not one giant stack: objective
   alignment first, turnover rule second, then one isolated data-family arm.
4. Treat analyst revisions as the first local-data arm; earnings as second only
   if its short coverage meets fold minimums; options last.
5. Do not combine LTR + three new families + neutralization + buffer into one
   result, because success or failure would be scientifically uninterpretable.
