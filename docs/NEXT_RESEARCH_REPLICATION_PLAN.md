# Next research and replication plan

Date: 2026-09-19. This plan starts **after** EXP-009D. It does not amend,
reinterpret, or rerun EXP-008 or EXP-009, and it does not authorize sealed
holdout access. New tests receive new experiment identifiers and are committed
before execution.

## Evidence-based conclusion

The literature and local results reject a model-first response. Published
ranking gains are gross, narrow, or against weak baselines; OmniSignal's two
rankers did not improve ordering. The analyst-revision family is real in the
literature only with richer analyst-level histories, while the eight local PIT
consensus features failed. Deep distribution, graph and economic-policy models
require licensed inputs or compute beyond both available environments.

The untested opportunity is **information**: as-reported fundamentals and a
broad characteristic panel, joined through a PIT identity/industry/size master.
Before building it, the existing stochastic noise and horizon/cadence mismatch
must be quantified so the next data experiment has a credible hurdle.

## Ordered program

### 1. EXP-010A — multi-seed noise floor (immediate next experiment)

Preregister a diagnostic study using the frozen EXP-009D data, 26-feature
deduplicated feature list, eight folds, sklearn gradient boosting and top-k
dropout. Run exactly ten seeds, including seeds 0 and 1. No hyperparameter or
portfolio search.

Report per seed and across seeds: mean daily Rank IC, HAC t, ICIR, net Sharpe at
1/3/5/10/20 bp, one-way turnover, maximum drawdown, fold signs, prediction-rank
correlation and dispersion. The primary outputs are the standard deviation and
90% range of Rank IC and net Sharpe. The existing observed reseed movement
(~0.0031 IC and ~0.067 net Sharpe) is a reference, not a pass threshold.

**Environment:** MacBook. **Purpose:** set the minimum effect size for every
later comparison. **What it does not do:** select a new model or consume the
sealed holdout.

### 2. EXP-010B — registered 5-session versus 21-session cadence

Only after EXP-010A is frozen, compare rebalance schedules using the same
predictions, same top-k dropout rule, same universe and same cost model. Use
5-session cadence as the control and 21-session cadence as the single arm. The
21-session arm aligns decision frequency with the 21-session prediction target;
both arms must use non-overlapping implementation rules defined in advance.

Primary economic estimands: paired net return difference, turnover ratio, gross
return retention and block-bootstrap net-Sharpe difference. Treat lower turnover
without retained gross return as a failure. Do not retrain and do not vary drop
rate, minimum hold, costs or cadence after results.

**Environment:** MacBook. **Purpose:** remove a known design mismatch cheaply.

### 3. Build, do not experiment — PIT identity and SEC facts

Implement the security-master and as-reported-fundamental plans as versioned
data products with tests. Required outputs:

1. CIK-centered identifier intervals with ticker/exchange/name and dated SIC.
2. PIT shares and market cap with provenance and availability timestamp.
3. SEC quarterly bulk `sub`/`num`/`tag`/`pre` ingest retaining accession,
   accepted time, form and amendments.
4. First-reported and as-of vintages; no restatement value may appear early.
5. Coverage, unmapped-tag, duplicate-context and identity-break reports.
6. Immutable Parquet shards plus manifest/hash and truncation-invariance tests.

This phase is successful when the dataset is auditable, not when a backtest is
attractive.

### 4. Construct a broad, literature-grounded characteristic panel

Start with features whose economic date and formula can be made exact:

- price/momentum: 1/3/6/12-month momentum excluding the most recent month,
  short reversal, 52-week proximity, idiosyncratic/realized volatility;
- liquidity: dollar volume, turnover, Amihud illiquidity, zero-return share;
- value: book-to-market, earnings yield, cash-flow yield;
- quality/profitability: gross profitability, operating profitability, ROA,
  ROE, margins and accruals;
- investment/growth: asset growth, capex/investment, issuance, sales and
  earnings growth;
- balance-sheet risk: leverage, cash ratio and working-capital measures;
- controls: PIT log market cap, SIC/FF-industry, exchange and market beta.

Cross-sectionally winsorize and rank/z-score inside each date using training
rules only. Preserve missingness indicators; do not forward-fill through filing
or identity boundaries. Sector/size residualization must be fit separately per
date and must be an explicit experiment arm, not an invisible preprocessing
change.

### 5. EXP-011 — first new-information model study

Preregister three models on one frozen rich panel:

1. regularized linear model (required interpretability baseline),
2. the existing sklearn gradient-boosting model (continuity baseline),
3. LightGBM/XGBoost point regression if dependency and determinism gates pass.

Use the same 21-session cross-sectional rank target, eight walk-forward folds,
ten fixed seeds for stochastic models and the already selected top-k dropout
portfolio. Compare **base 26 features** versus **base + SEC PIT panel** within
each model. This is a data ablation first and a model comparison second.

Primary claim requires an effect larger than the EXP-010A noise distribution,
positive paired HAC evidence, at least six of eight folds improving, and net
survival under the frozen cost grid. Do not add neural models during this
study. If linear/tree models cannot extract stable signal, complexity is not
the next remedy.

**Environment:** start on Mac. Move only the boosting ten-seed workload to two
independent Kaggle workers if a measured Mac pilot exceeds two hours.

### 6. Conditional follow-ons

- **EXP-012 small MLP:** only if EXP-011 proves that the new data has signal and
  nonlinear boosting materially beats linear. Run on Kaggle; same data/folds/
  seeds/portfolio, no architecture sweep.
- **SEC event text:** build accepted-at 8-K/earnings-release or 10-K novelty
  features, then use frozen embeddings. It must beat numeric surprise and
  filing-change baselines. Kaggle is appropriate for embedding generation.
- **Analyst-level revisions:** only after legally acquiring analyst identity,
  recommendation/target history and exact timestamps. Aggregate consensus data
  should not be retested after EXP-009C without a genuinely new mechanism.
- **Options:** last. Require contract-level synchronized history, volume/OI and
  liquidity filters. The current aggregate panel cannot replicate surface or
  higher-moment papers.

## Replication shortlist

| Priority | Paper / method | Action | Why |
|---:|---|---|---|
| 1 | GKX broad characteristics | **ADAPT** | Most direct information-content upgrade; tree and linear baselines; PIT lags are explicit. |
| 2 | Regularized Fama–MacBeth / economic restrictions | **ADAPT** | Interpretable, cheap baseline and natural size/industry controls. |
| 3 | Novy-Marx–Velikov + Qlib turnover layer | **KEEP ADAPTATION** | Mechanism already confirmed by EXP-009A; freeze it while testing information. |
| 4 | SEC cyber/earnings text studies | **ADAPT LATER** | Shows a lawful, timestamped text path, but event text should follow numeric PIT data. |
| 5 | JKMP implementable frontier | **ADAPT PRINCIPLE ONLY** | Net objective is right; exact pipeline needs HPC/licensed data and cannot isolate attribution cheaply. |
| 6 | Barunik quantile networks | **DEFER** | Distributional target is interesting but full compute >2 months and the paper omits costs/turnover. |
| 7 | Poh/ListFold ranking | **REJECT NEXT CYCLE** | EXP-009B null; published evidence does not establish net gain against strong trees. |
| 8 | Analyst stickiness | **DEFER** | Good peer-reviewed mechanism, wrong local data granularity. |

## Promotion and holdout boundary

None of EXP-010A/B, the data builds, or exploratory EXP-011 development may
touch the sealed 2025-08-26/28 onward window. A candidate can be nominated for
one final holdout evaluation only after its exact data version, features, model,
seed aggregation, portfolio rule, cost assumptions and thresholds are committed
and separately authorized. A successful holdout would still require an
operational execution review; it would not retroactively validate the 166 prior
evaluations.

## If there is only one more serious cycle

**Data:** SEC as-reported numeric fundamentals plus a CIK-centered PIT security
master, merged with existing price/volume/macro features and PIT size/industry
controls.

**Model:** regularized linear baseline and one conservative boosted-tree model
on the same 21-session rank target; keep top-k dropout fixed. The scientific
candidate is the data ablation, not the algorithm.

**Compute:** build and validate on the MacBook; run EXP-010A/B there. Start the
rich-panel models on the Mac and use Kaggle's two T4s only as independent seed
workers if actual boosting runtime justifies transfer. Do not start with a deep
model merely because a GPU exists.

## Status update — 2026-09-20

Done since this plan: multi-seed noise floor (EXP-010A), one preregistered 21-session cadence test (EXP-010B), SEC as-reported facts and a graded PIT security master, and a rich characteristic panel. Next, in order: (1) the owner runs EXP-011 (rich data vs baseline, Ridge and boosting); (2) only if EXP-011 shows a detectable, fold-robust ordering gain, consider one preregistered follow-up on the *features* (never the cadence, dropout or costs); (3) close the security-master gap (20-F/IFRS tag map for foreign issuers; vendor-independent delisted-name evidence) so size and industry controls can be evaluated; (4) ALFRED macro vintages once a FRED key exists. The sealed holdout is opened only for one frozen candidate and on explicit user authorisation.
