# Deep method reconstruction

Review date: 2026-09-19. Baseline commit: `e8cd91f`. This document replaces the
survey's summary-level claims with what was read in the primary source. It is a
verification record, not another bibliography: every study answers *what
exactly worked, why, on what data, with what target / loss / portfolio /
turnover / costs, and what OmniSignal can and cannot reproduce*.

## Evidence-status legend

| Tag | Meaning |
|---|---|
| **FULL-TEXT** | The paper (PDF) was downloaded and the passages cited were read directly, including the tables cited. |
| **CODE** | Official source code / config / license file was read directly from the official repository. |
| **ABSTRACT-ONLY** | Only the publisher/preprint abstract or a search snippet of it was reachable (SSRN and the OUP full text returned HTTP 403). Nothing beyond the abstract is asserted. |
| **UNVERIFIED** | No primary source could be read. The value is carried from the earlier survey, if at all, and is **not** relied on. |

Where a field below says `NR`, the primary text read does not state it. `NR` is
not a negative claim.

Primary sources reached in this pass: arXiv (2012.07149, 2104.12484, 2009.11189,
2408.07497), NBER (w25398, w20721), the authors' site for Gu-Kelly-Xiu
(`dachxiu.chicagobooth.edu`, which serves the RFS-typeset PDF), and
`raw.githubusercontent.com` / the GitHub API for Qlib, ListFold, GKX and the
quantile-network package.

---

## S1. Gu, Kelly & Xiu — *Empirical Asset Pricing via Machine Learning* (RFS 33(5), 2020) — FULL-TEXT

| Field | Verified content |
|---|---|
| Citation / DOI | Review of Financial Studies 33(5):2223-2273; DOI 10.1093/rfs/hhaa009. Read the RFS-typeset PDF (authors' site) and NBER w25398. |
| Dataset | CRSP monthly returns, NYSE/AMEX/NASDAQ, March 1957 – December 2016; nearly 30,000 stocks, more than 6,200 per month on average. |
| Universe filters | None beyond listing on the three exchanges; bottom-1,000 / top-1,000 subsamples are reported separately. Microcaps are **included** in the headline results; one robustness result excludes stocks below the 20th NYSE size percentile (NN4 long-short Sharpe 1.69). |
| Target | Monthly individual-stock **excess return** (over the T-bill rate) — a raw return, **not** a rank. |
| Inputs | 94 stock characteristics (61 updated annually, 13 quarterly, 20 monthly), 8 aggregate macro variables interacted with each characteristic, 74 two-digit SIC dummies: >900 baseline signals. |
| Publication lags | Monthly characteristics lagged at most 1 month, quarterly at least 4 months, annual at least 6 months. Missing characteristics → cross-sectional median each month. |
| Models / loss | OLS, OLS-3 (size, B/M, momentum), PLS, PCR, elastic net, group-lasso GLM, random forest, GBRT, NN1-NN5; "+H" variants use Huber loss, otherwise l2 (MSE). All regress returns; none is trained on ranks. |
| Validation | 18 years train (1957-74), 12 years validation (1975-86), 30 years OOS test (1987-2016). Refit once a year, training window expanding, validation window rolling forward by 12 months. No cross-validation, "to maintain temporal ordering". |
| Portfolio | Value-weighted and equal-weighted long-short **deciles** sorted on predicted return, rebalanced monthly. |
| Reported results | NN long-short decile Sharpe **1.35 value-weighted, 2.45 equal-weighted**; the OLS-3 benchmark 0.61 / 0.83. A market-timing strategy on NN forecasts: Sharpe 0.77 vs 0.51 buy-and-hold. |
| Turnover (Table 8) | Monthly, defined as the mean of Σ\|w(t+1) − w(t)(1+r)/(1+Σ w r)\|. NN1-NN5 121-127% per month (value-weighted), 112-114% (equal-weighted) — the text says "consistently between 110% and 130%"; OLS-3 58%; a short-term-reversal decile spread 172.6%; a size decile spread 22.9%. |
| Costs | **None are charged.** The word "transaction" does not appear in the RFS text; turnover is reported and discussed as a diagnostic only. |
| Most important predictors | Price-trend (momentum, industry momentum, short-term reversal), liquidity (market equity, dollar volume, bid-ask spread), volatility. Reported as consistent across all methods. |
| Robustness | Subsample by size; Internet appendix (`ML_supp.pdf`, not read). |
| Code / data | The authors' page links a GitHub repository (`xiubooth/ML_Codes`; contents: `README.md`, `Simu_Matlab` — simulation code only; no license file; last push 2019) and a public **characteristic dataset** (`datashare.zip`, 1.56 GB, "updated June 2021") plus SAS/Python code to construct the characteristics (Feng's `EquityCharacteristics` site, not read). The full empirical pipeline is not in the repository. Redistribution terms of the dataset were not verified. |
| Reproducibility | Feasible for the *methodology*; not for the headline numbers without the 1957-2016 panel. |

**Why it worked.** Nonlinear models (trees, NNs) extract interactions among
momentum/liquidity/volatility that linear models miss; the paper attributes the
gain to "allowing nonlinear predictor interactions". The gain is measured
gross of trading costs in a sample that is dominated by small stocks in the
early decades.

**OmniSignal mapping.** OmniSignal's `C_base` family is the same three
families GKX find dominant (price trend, liquidity, volatility) plus rates/
macro — but on a 250-name liquid universe (no microcaps), a 21-session target
ranked cross-sectionally, and 8 folds instead of 30 years. The fair reading
of EXP-006's Rank IC 0.029 is not "GKX failed to replicate"; the universe that
removes microcaps also removes most of the return dispersion GKX exploit.
**GKX's ML portfolios turn over about 1.2x per month (Σ|Δw|, monthly
cadence, weights normalised as in the paper — the gross normalisation of the
long-short book is not stated in the passages read). EXP-006's round-trip
Σ|Δw| is about 3.4x per month per unit of gross exposure (40.3x annualised,
weekly cadence; see `docs/TURNOVER_FAILURE_ANALYSIS.md`), so the two are not
identically defined but EXP-006 trades roughly two to three times as fast.**
GKX never had to pay for turnover.

---

## S2. Poh, Lim, Zohren & Roberts — *Building Cross-Sectional Systematic Strategies By Learning to Rank* (arXiv 2012.07149 v1, Dec 2020) — FULL-TEXT

| Field | Verified content |
|---|---|
| Status | arXiv preprint (v1 read). A journal version is not verified here. |
| Dataset | CRSP; **NYSE** firms with share codes 10/11, **1980-2019**; price > $1; valid prices and active over the previous year. Monthly rebalancing on the last trading day. |
| Target | Return **21 trading days ahead** ("instead of the next month"), volatility-normalised. |
| Inputs | **Only price-derived momentum predictors**: 3/6/12-month raw returns, volatility-normalised returns, and MACD-based indicators (16 features in that group). |
| Models | Baselines: random, Jegadeesh-Titman raw-return rank, Baz et al. vol-normalised MACD rank, an MLP "regress-then-rank". LTR: RankNet, LambdaMART, ListNet, ListMLE. |
| Training | Models re-tuned at 5-year intervals, then frozen for the next 5-year OOS window; 90/10 train/validation split; hyper-parameters tuned by 50 HyperOpt iterations; early stopping for NNs. |
| Portfolio | **100 stocks long and 100 short** at all times (~10% of tradeable stocks), equal weight scaled by ex-ante volatility, whole portfolio rescaled to **15% target volatility**. |
| Ranking metrics | Kendall's τ and NDCG@k with k = 100 (= portfolio size). Kendall τ: JT 0.016, Baz 0.013, MLP 0.008, LambdaMART 0.032, ListNet 0.033. NDCG@100 (longs): 0.549-0.578. |
| Reported results (Exhibit 2, vol-scaled) | Sharpe: Random 0.155; JT 0.551; Baz 0.696; MLP 0.265; RankNet 1.502; **LambdaMART 2.156**; ListNet 1.970; ListMLE 1.611. Max drawdown 23-29% for rankers vs 33-64% for benchmarks. |
| The "threefold" claim | 2.156 / 0.696 ≈ 3.1x versus the best heuristic, 3.9x versus JT, ≈8x versus the MLP. **The abstract's claim is accurate for this table and only for this table.** |
| Costs | **"All returns in this section are computed without transaction costs to focus on the raw predictive ability."** The introduction says monthly rebalancing is used to avoid excessive costs; no net figure is reported. |
| Code | No code released in the paper text read; license NR. |
| Limitations the paper itself gives | Small, noisy data; listwise not clearly better than pairwise; the MLP baseline is weak (Sharpe 0.265). |

**Why it worked (paper's account).** The ranking loss learns pairwise/listwise
structure of a cross-section, so training signal concentrates on ordering
rather than on the magnitude of returns; LambdaMART additionally optimises a
top-weighted metric (NDCG).

**Correction to the survey.** The survey and `docs/replications/poh_ltr.md`
state the threefold Sharpe improvement without its qualifiers. It is
**gross of costs**, monthly cadence, NYSE-only, momentum-only predictors,
volatility-scaled to 15%, and measured against heuristic and MLP baselines —
not against a tuned gradient-boosted regression, which is the appropriate
OmniSignal control. The improvement in ranking metrics themselves is small
(τ 0.013→0.032, NDCG@100 0.562→0.576).

**OmniSignal mapping.** Reproducible in *structure*: dates as queries,
stocks as items, LambdaMART on tree ensembles. Not reproducible in
*magnitude*: different market, features, cadence and no cost treatment.
Consequently EXP-009B must compare against the existing gradient-boosting
regression baseline on identical folds, not against a weak MLP.

---

## S3. Zhang, Wu & Chen — *Constructing long-short stock portfolio with a new listwise learn-to-rank algorithm* (arXiv 2104.12484 v1) — FULL-TEXT + CODE

| Field | Verified content |
|---|---|
| Title correction | The survey lists this as "Listwise Learning-to-Rank for Long-Short Portfolios". The arXiv title is the one above (ListFold loss). |
| Status | arXiv preprint (dated Dec 2020, posted Apr 2021). |
| Dataset | China A-share market, weekly observations 2006-12-29 to 2019-04-19 (631 weeks), 3,712 stocks initially, **filtered to 80 stocks** by requiring <0.1% missing values ("mostly listed in the HS300 index and highly liquid"); 68 factors. |
| Target | Cross-sectional rank of returns. Loss: a new listwise "ListFold" loss emphasising both tails, a shift-invariant generalisation of ListMLE. |
| Model | Same 4-layer MLP scoring function for MLP, ListMLE, List2MLE and ListFold. |
| Validation | Rolling: 300 weeks train, next 16 weeks test; 320 OOS weeks (≈6 years, from 2012). |
| Portfolio | Fixed nominal $1 per week; long-short. |
| Costs | Table 2 includes **30 bp per trade** ("tax, spread crossing and getting short") and a 3% risk-free rate. |
| Results (Table 2) | ListFold-exp: μ−rf 0.38, σ 0.19, **Sharpe 2.01**, MDD 0.14, turnover 0.48; MLP: μ−rf 0.16, Sharpe 0.72, turnover 0.39; ListMLE 0.91; List2MLE 1.29. |
| Inference | ListFold-exp vs List2MLE weekly-difference t-stat 1.45 (not significant). |
| Turnover (their TRV) | The non-overlapping stock ratio between consecutive weeks: 0.39-0.48. **Comparable to EXP-006's ≈0.40 one-way per leg per rebalance.** They note turnover "would increase significantly" for larger pools. |
| Code / data | The paper states data and code are open on GitHub (`TCtobychen/ListFold`). GitHub API: the repository exists (9 files, last push 2021-03-14), **no license**. |

**Corrections to the survey.** (1) The repository named in the survey,
`TCtobychen/ListFoldofficialpytorch`, returns **404**; the paper's own
repository is `TCtobychen/ListFold`. (2) "Dataset availability NR" is wrong:
the paper states the data are open. (3) The survey omits the most important
limitation — the **80-stock survivorship-filtered universe** (names with
almost no missing data over 13 years are, by construction, survivors). (4) The
survey lists "38% annual return, Sharpe 2" without noting it is an *excess*
return after a 30 bp cost assumption on 80 stocks; that is favourable evidence
for cost handling but weak evidence for a 250-name US universe. (5) No license
means the code is reference-only; OmniSignal will not copy it.

**Why it matters for turnover.** ListFold's own turnover (0.45-0.48 weekly,
no better than the regression baseline's 0.39) shows that a ranking objective
**does not by itself reduce turnover**. This directly supports the design
principle that ranking loss and turnover control are separate levers and must
not be combined in one experiment.

---

## S4. Microsoft Qlib — Yang et al., arXiv 2009.11189, plus official repository — FULL-TEXT + CODE

| Field | Verified content |
|---|---|
| Nature | An engineering platform paper (8 pages). It contains no TopkDropout description, no IC benchmark and no turnover discussion; those live only in the repository. |
| License | **MIT** (LICENSE read; Microsoft). |
| Benchmark config read | `examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml`: CSI300, `Alpha158` features, train 2008-14, valid 2015-16, test 2017 – Aug 2020; LightGBM with `loss: mse`; `TopkDropoutStrategy` with **`topk: 50, n_drop: 5`**; `deal_price: close`, `open_cost: 0.0005`, `close_cost: 0.0015`, `min_cost: 5`; `limit_threshold: 0.095`. |
| Target | `Ref($close,-2)/Ref($close,-1)-1` — the **next-day** return with an explicit one-day execution lag — then cross-sectional z-score (`CSZScoreNorm`, learn stage) with `DropnaLabel`. Inference stage: `ProcessInf`, `ZScoreNorm`, **`Fillna`**. |
| Cadence | Daily signal and daily portfolio update. |
| TopkDropout algorithm (source read) | Hold `topk` names. Each step: sort holdings by score; candidates `today` = the top-scoring non-held names, `n_drop + topk − len(holdings)` of them; combine and sort; **sell** the holdings in the bottom `n_drop` of the combined list, subject to a minimum hold (`hold_thresh=1`); **buy** the best candidates to refill to `topk`. Equal weight. **Long-only.** |
| Benchmark table (README, CSI300 Alpha158, mean of 20 seeds) | Rank IC / IR: **DoubleEnsemble 0.0502 / 1.343**; LightGBM 0.0469 / 1.016; MLP 0.0429 / 1.141; XGBoost 0.0505 / 0.907; CatBoost 0.0454 / 0.803; **Linear 0.0472 / 0.921**; TRA 0.0540 / 1.084; Transformer 0.0407 / 0.397; TabNet 0.0333 / 0.368; GRU (20 feat) 0.0428 / 0.516; LSTM 0.0435 / 0.556; TFT 0.0116 / 0.813. On Alpha360: Transformer IR −0.34, TabNet −0.39, LightGBM 0.76, TCN 0.83. |
| Reproducibility | Code MIT; the China data are community/Yahoo-derived. Not a US point-in-time source. |

**What "worked" and why.** The strategy layer, not the model, is what limits
turnover: with `topk=50, n_drop=5`, at most 10% of the book can change each
day. The published table shows the plain **linear** model with IR 0.92 ahead
of TabNet, Transformer, GRU, LSTM and the CatBoost/XGBoost rows on the same
strategy, i.e. the portfolio rule and data dominate model family.

**Claim audit — "neural nets dominate".** Not supported. In Qlib's own
20-seed benchmark the best row is a **gradient-boosting ensemble**
(DoubleEnsemble); every pure sequence NN (TabNet, Transformer, GRU, LSTM)
sits below a linear regression on information ratio on Alpha158, and several
NNs are negative on Alpha360. The survey's Qlib statement ("LightGBM is
competitive with or better than several deeper models") is accurate and is
retained.

**What OmniSignal borrows — and does not.** Only the *idea* (hold incumbents,
replace a bounded number). The algorithm is re-implemented independently inside
`src/quant/backtest/rules.py`; **no Qlib import, no copied code**. Deliberate
deviations: (a) OmniSignal's book is long/short, so the rule runs per leg;
(b) forced exits (a name leaving the eligible set) are mandatory and are not
counted against the drop budget; (c) the cost model, timing and label are
OmniSignal's, not Qlib's; (d) `Fillna` is **not** adopted — missing stays
missing.

---

## S5. Novy-Marx & Velikov — *A Taxonomy of Anomalies and Their Trading Costs* (NBER w20721, Dec 2014; RFS 29(1), 2016) — FULL-TEXT (working paper)

| Field | Verified content |
|---|---|
| Venue | NBER working paper 20721 read. (Its RFS 2016 publication is recalled, not verified in this pass; the working-paper text is what is cited.) |
| Question | Which cross-sectional anomalies survive transaction costs, and which cheap mitigation techniques work? |
| Mitigation techniques | (1) restrict to low-cost stocks; (2) reduce rebalancing frequency; (3) **a buy/hold spread**. |
| Buy/hold spread ("sS rule") | A stock is held (short position maintained) while its sort variable stays in the extreme *s*%, and bought (shorted) only when it enters the most extreme *S*%. Example: "a 10%/20% buy/hold rule implies that we only buy (sell short) stocks when they get into the top (bottom) 10%, and hold them by restricting sales for stocks that leave the top (bottom) 20%." Mid-turnover strategies use 10%/20%; high-turnover strategies use 10%/50%. |
| Rationale in the paper | "There is not much of a difference in expected returns between stocks in the 75-80% range of the distribution of a given return predictor and those in the 80-85% range" — the rule holds close substitutes rather than selling and re-buying them. |
| Result | The buy/hold spread is "the single most effective simple cost mitigation strategy". Across the 23 mid-turnover anomalies the sS rule cut turnover by an average of **41%** and transaction costs by **42%**; gross returns fell "slightly". Only two strategies with more than 50% one-sided monthly turnover have significant net spreads even when cost-mitigated. |
| Costs | Effective-spread based model; round-trip cost for typical value-weighted strategies averages more than 50 bp; equal-weighted strategies cost two to three times as much and "equal-weighting often results in a deterioration of net performance". |
| Theory cited | Arrow-Harris-Marschak (1951) sS inventory rule; Davis & Norman (1990); Abel & Eberly (1996): the inaction region is proportional to the cube root of the price wedge. |

**Why it matters.** This is the literature anchor for EXP-009A's hysteresis
cell: a buy/hold spread is an established, model-free technique whose
mechanism (hold close substitutes) is exactly what EXP-006's boundary
turnover suggests. It also warns OmniSignal that **its book is equal-weighted
with a 40%-per-leg weekly replacement**, the cost-worst configuration in this
literature.

**Anchor used in the preregistration.** The 10%/20% decile rule generalises
to a quintile book as **enter top 20% / retain until the name leaves the top
40%** (same 2:1 ratio). The brief's 80/70 example is a milder 3:2 ratio and
is retained as a labelled dose-response companion (see
`docs/EXP_009A_TURNOVER_PREREGISTRATION.md`).

---

## S6. Jensen, Kelly, Malamud & Pedersen — *Machine Learning and the Implementable Efficient Frontier* — ABSTRACT-ONLY (+ repo README)

| Field | Verified content |
|---|---|
| Status | Published in the **Review of Financial Studies (2026)** per the search result and the SFS forthcoming-paper page; the survey lists it as a 2024 SFI working paper (out of date). Full text: SSRN returned 403 — UNVERIFIED beyond the abstract. |
| Abstract (as retrieved) | Strategies should be evaluated on **net-of-trading-cost return for each level of risk** — the "implementable efficient frontier". ML return forecasts that are agnostic to trading costs lead to "excessive reliance on fleeting small-scale characteristics, resulting in poor net returns". The paper integrates trading-cost-aware portfolio optimisation with ML and learns portfolio weights directly with an economic objective; it also yields an "economic feature importance" measure. |
| Code | `theisij/ml-and-the-implementable-efficient-frontier` exists; **no license** (GitHub API 404 for a license, README states none). It requires WRDS data from the JKP "Replication Crisis" project (or data requested from the authors) and Markit short-selling fees. |
| Reproducible here? | **No.** The data are licensed (WRDS/Markit) and the objective is end-to-end. |

**Use.** It supports the *framing* (evaluate net, not gross; fleeting
characteristics are expensive) and motivates a post-model trading rule as the
cheapest identified substitute. No result from it is quoted as an expected
OmniSignal outcome.

---

## S7-S12. Abstract-level or unverified items

| Study | Status | What is supported | What is not |
|---|---|---|---|
| Cakici & Zaremba, *Getting the Target Right in Return Prediction* (SSRN 6615698, 2026) | ABSTRACT-ONLY (SSRN 403; a search summary and QuantPedia agree) | 35 markets, 1994-2024. Moving from a raw target to a standardised or rank-based target "nearly triples predictive accuracy and doubles portfolio returns"; rank targets perform best on average, but discard magnitude and underperform when dispersion/skewness is high, especially micro-caps; standardised targets win in emerging markets. | The specific model set, cost treatment and whether returns are gross were not read. **Relevance:** OmniSignal's `fwd_rank_21` already *is* a rank target, so this paper argues the current target is not the problem. |
| Azevedo, Hoegner & Velikov, *The Expected Returns on Machine-Learning Strategies* (SSRN 4702406) | ABSTRACT-ONLY | The paper accounts for transaction costs, post-publication decay and the post-decimalisation era, and reports that sophisticated ML strategies **remain profitable net**: net out-of-sample monthly returns up to 1.42% despite turnover above 50%; an LSTM combination has a six-factor generalised (net) alpha of 1.20% (t 3.46). | **The survey's "57% combined reduction" figure is UNVERIFIED** and its framing ("costs and decay reduce performance") omits the paper's headline that the strategies survive. Note the co-author, Velikov, is the sS-rule author (S5): net survival there is achieved with cost mitigation. |
| Honarvar & Howard, *Better Opt Out?* (SSRN 4766424; J. Portfolio Management 52(1), 2025) | ABSTRACT-ONLY | Options-implied signals predict robustly 1996-2008 with a marked decline afterwards; options prices recorded up to ~10 minutes after the stock close create look-ahead; lagging options data "substantially reduces" the earlier performance. | Nothing about the value of options data *for OmniSignal's local aggregates*. |
| Cao, Tao, Wang & Yin, *Analyst stickiness and stock return predictability* (Review of Finance 2026, rfag022) | ABSTRACT-ONLY (publisher page) | Analyst-level "stickiness" is estimated; consensus revisions from sticky analysts predict returns more strongly than traditional consensus measures, more so in high forecast-difficulty settings. | Data source and sample period are not on the page. It says nothing about plain consensus revisions outperforming; and it needs **analyst-level** history OmniSignal does not hold. |
| Barunik, Hronec & Tobek, *Forecasting stock return distributions* (arXiv 2408.07497 v2, Aug 2025) | FULL-TEXT skim | Quantile neural network + spline CDFs; derived mean/variance forecasts improve OOS performance; US and international. The text contains **no transaction-cost or turnover analysis** (zero mentions). Replication package `ondrejtobek/quantile-neural-networks` is **MIT**. | Not evidence about net portfolio economics. |
| Chen, Hanauer & Kalsbach (SSRN 5031755); Bianchi & Zheng (SSRN 6359140); Brownlees & Souza (SSRN 5352643) | **UNVERIFIED** (SSRN 403; searches did not surface Bianchi & Zheng at all) | Nothing is relied on. In particular the survey's "24-45% turnover reduction with little performance change" (Bianchi & Zheng) and "59% non-standard error" (Chen et al.) are **not confirmed** and must not be cited as fact. | — |

---

## Cross-study reconstruction

| Question | What the read sources establish |
|---|---|
| Target | GKX: raw excess return (MSE/Huber). Poh: 21-day vol-normalised return, learned as ranks. ListFold: cross-sectional rank. Qlib: next-day return, cross-sectionally z-scored. OmniSignal EXP-006: signed cross-sectional rank of the 21-session return, regressed by MSE. So rank *targets* are already in use; what differs is the *loss*. |
| Loss | Only Poh and ListFold optimise ranking losses; both against weak MLP baselines. No paper read compares LambdaMART with a tuned gradient-boosted regression net of costs. |
| Portfolio | GKX: value- and equal-weighted deciles, monthly. Poh: 100/100 equal-weight, monthly, vol-targeted. ListFold: weekly, 80 stocks. Qlib: long-only top-50, daily, 10% drop. NMV: sS buy/hold spread on deciles, monthly. OmniSignal: equal-weight quintile long/short, **weekly**, immediate replacement. |
| Turnover | GKX ML models ≈110-130% of gross per month; ListFold 0.39-0.48 per week; Qlib bounded by 10% per day by construction; NMV: sS cuts turnover 41% on average. EXP-006: 20.15x annualised one-way (≈1.7 one-way, ≈3.4 round-trip turns per month per unit of gross). |
| Costs | GKX: none. Poh: none. ListFold: 30 bp per trade. Qlib: 5 bp open / 15 bp close (China, includes stamp duty). NMV: effective-spread model. Azevedo et al.: costs charged, strategies survive. |
| What worked | Nonlinear interactions on price/liquidity/volatility features (GKX); rank-aware loss on a *gross* basis (Poh, ListFold); a hold-close-substitutes rule that cuts turnover ≈40% with slightly lower gross return (NMV); a bounded-replacement portfolio layer (Qlib). |
| What none of them shows | A ranking loss that lowers turnover; a net-of-cost ranking-loss improvement against a tuned tree regression; any of the above for a **liquid-250 US universe at weekly cadence**. |

## What OmniSignal can and cannot reproduce

| Element | Can reproduce | Cannot reproduce |
|---|---|---|
| sS buy/hold rule (NMV) | Exactly, on frozen predictions and the existing cost model. | Their CRSP-wide universe or their effective-spread model. |
| Top-k dropout (Qlib) | The logic, independently, per leg. | China data, close-price fills, long-only construction. |
| LTR structure (Poh) | Date-grouped LambdaMART/pairwise on the existing folds. | Their CRSP-NYSE monthly momentum panel, vol-targeting, their MLP baseline. |
| ListFold loss | Not attempted (no license; NN). | — |
| GKX magnitudes | Feature families and split logic. | 30-year CRSP panel including microcaps; annual refits over 60 years. |
| JKMP end-to-end objective | Not attempted. | Licensed characteristics/short-fee data; unlicensed code. |
| Analyst stickiness | Nothing (no analyst identity in local data). | Analyst-level revision history. |

## Audit of earlier claims

| Claim (source) | Verdict | Correction |
|---|---|---|
| "Threefold Sharpe improvement" (survey; `replications/poh_ltr.md`) | **Accurate but incomplete** | Gross of costs, monthly, NYSE 1980-2019, momentum-only, vol-scaled, vs heuristic/MLP baselines. ≈3.1x vs the best heuristic, ≈8x vs MLP. Not a net or US-liquid result. |
| ListFold repo `TCtobychen/ListFoldofficialpytorch`; "dataset availability NR" (survey) | **Wrong** | Repo is `TCtobychen/ListFold`; the paper states data and code are open; no license. Universe is 80 survivor-filtered stocks; costs were included (30 bp). |
| GKX "No official code verified" (survey code table) | **Partly wrong** | Authors link a GitHub repo (simulation Matlab only, no license) and a public characteristic dataset; the full empirical pipeline is not public. |
| JKMP "2024 SFI working paper", code "NR" | **Out of date** | RFS 2026; a code repository exists (no license; needs WRDS/Markit data). |
| Azevedo et al. "57% combined reduction" and "makes net-first gates mandatory" | **Unverified figure; framing incomplete** | The abstract reports ML strategies remain profitable net (up to 1.42%/month). The net-first gate is still correct as a principle, but not because of this paper's headline. |
| Bianchi & Zheng "24-45% turnover reduction" | **UNVERIFIED** | Not found; not to be cited. |
| "Options improve prediction" (implicit in options-family rationale) | **Not supported** | The one options paper read (Honarvar & Howard) reports post-2008 decay and look-ahead correction shrinking the earlier effect. The survey already prioritises options last; that stands and is strengthened. |
| "Analyst revisions outperform" | **Not established** | The verified paper concerns *sticky-analyst* revisions needing analyst-level data; OmniSignal's own EXP-005 ablation was negative. Treated as an untested hypothesis with a low prior. |
| "Neural networks dominate" | **Not supported** | Qlib's own benchmark: a linear model beats TabNet/Transformer/GRU/LSTM on IR; the top row is a GBDT ensemble. GKX find NNs and trees best on R²oos/Sharpe but gross of costs. |
| "Ranking loss lowers turnover" (implicit in LTR motivation) | **Not supported** | ListFold's ranking loss has *higher* turnover (0.48) than its MLP baseline (0.39). |

## Consequences for the EXP-009 design (frozen in the preregistrations)

1. **A (turnover)** is the most identified lever: NMV supplies a mechanism, a
   magnitude (≈40% turnover cut, slightly lower gross) and a rule shape; Qlib
   supplies a second rule shape with published parameters (`topk=50, n_drop=5`).
   Neither literature result is treated as an expected OmniSignal outcome.
2. **B (ranking loss)** must be compared against the existing tuned
   gradient-boosting regression on identical folds and the same portfolio rule,
   with turnover reported *separately* because ranking loss is not a
   turnover control (ListFold).
3. **C (analyst)** is a low-prior hypothesis; it runs only if a point-in-time
   audit passes, on a single BASE vs BASE+analyst arm.
4. Nothing here changes EXP-008.

---

## S13. Barunik, Hronec & Tobek — return-distribution networks — FULL-TEXT + CODE

| Field | Verified content |
|---|---|
| Data | US CRSP/Compustat/IBES plus LSEG international inputs. The network uses 176 stock characteristics and 18 market/volatility inputs, **194 total**. Accounting data are lagged; the authors state features use information available at prediction time. |
| Target | **37 conditional quantiles** of next 22-day return. A standardized-return subnetwork and market-volatility subnetwork reconstruct raw-return quantiles and moments. |
| Validation | Initial US train/validation through 1994, annual expanding retraining, 1995–2018 OOS; separate full/liquid and regional samples. Monthly equal-weight decile portfolios. |
| Costs | The PDF contains no transaction-cost or turnover analysis. This is gross distribution-forecast evidence, not net implementation evidence. |
| Reported compute | Official MIT repository: Ubuntu, 16 CPU cores, RTX 4090 24 GB, 128 GB RAM. Full scripts >2 months; data ~2 weeks, tuning ~3, all NNs ~2, GARCH ~1, simulations ~2; minimum notebook ~4 days. |
| Reproducibility | Code is strong, but full licensed WRDS/LSEG inputs are omitted. Exact replication fits neither the M4/24 GB nor Kaggle T4x2/29 GB-session environment. |
| Decision | DEFER. A reduced quantile study is warranted only after a rich PIT numeric panel demonstrates stable mean/rank signal net of costs. |

## S14. Chen, Pelger & Zhu — deep SDF — FULL-TEXT + CODE

| Field | Verified content |
|---|---|
| Data | All CRSP securities, roughly 31,000 over 1967–2016, with **46 firm characteristics** and **178 macro time series** (including FRED-MD and cross-sectional characteristic aggregates). |
| Split | 1967–1986 training, 1987–1991 validation, 1992–2016 test. |
| Model / target | Feed-forward SDF weights, LSTM macro state, and adversarial conditional-moment network; nine-fit ensembles. The objective is an SDF/no-arbitrage moment condition, not stock rank. |
| Costs | The paper analyzes turnover/liquidity cutoffs but is not a retail net-cost stock-selection replication. Hardware/runtime are not reported. |
| Reproducibility | Official author repository exists at reviewed commit `c25b1e7`, but no license is present and CRSP/Compustat inputs are licensed. |
| Decision | REJECT for the next cycle. Economic restrictions are useful; exact adversarial SDF complexity is not. |

## S15. Qian et al. MDGNN — FULL-TEXT

| Field | Verified content |
|---|---|
| Data | CSI100/CSI300; 42 node features: 25 market, 12 valuation, 4 categorical and 1 institutional-consensus feature. Graphs contain 100/300 stocks, 196/202 banks, 97/191 industries and **18,950,706 / 62,500,988 edges**. |
| Target / validation | Daily probability of positive return. Seven six-month training cycles from 2020 to 2023, final month validation, next six months prediction. |
| Model / compute | Multi-relational graph attention plus temporal transformer; hidden size 128, two layers, window 10, 500 epochs; **Nvidia V100**. Runtime/VRAM not reported. |
| Portfolio/costs | Reports IC, IR, cumulative return and precision@30; CSI300 IC 0.0322/IR 0.2488. No transaction costs or turnover. |
| Decision | REJECT now. Relation provenance and data are absent, and the China movement benchmark is not a US liquid-250 net ranking test. |

## S16. Celeny et al. — SEC 10-K cyber-risk text — FULL-TEXT

| Field | Verified content |
|---|---|
| Data | 7,059 CRSP/Compustat firms, 60,470 SEC 10-Ks, 2007–2022; most-recent filing score drives 2009–2022 portfolios. |
| Text model | Gensim doc2vec DM/DBOW trained on 2007 filings plus 785 MITRE ATT&CK descriptions, >1.7 million training paragraphs; 2008 documents validate the specification. |
| Portfolio | Quarterly rebalanced, value-weighted cyber-risk quintiles; most recent 10-K is the signal. Positive high-minus-low excess returns/alphas are reported. |
| Costs / compute | No transaction-cost or turnover analysis found; hardware/runtime not reported. |
| Reproducibility | SEC/MITRE text is open, but exact CRSP/Compustat returns/controls are licensed. Filing timestamps support a lawful PIT adaptation once CIK identity exists. |
| Decision | ADAPT LATER as a filing-text precedent, after numeric XBRL facts and the security master. |

## Compute and replication correction

The original S6 description understated JKMP's public reproducibility evidence:
the official repository gives exact Slurm job requirements even though the
paper text was inaccessible. Twelve model jobs used about 75 GB RAM each and up
to five hours; downstream jobs used roughly 25–70 GB and up to 2 days 16 hours.
That makes the exact feasibility verdict observable: **neither** the 24 GB Mac
nor Kaggle's ~29 GB host can run individual jobs as reported. The correct
adaptation is the already isolated turnover layer, not an undersized claim of
replication.

## Post-EXP-009 empirical update

The preregistered tests have now resolved three survey hypotheses locally:

- top-k dropout confirmed the turnover mechanism (20.15x → 6.90x; net Sharpe
  −0.102 → +0.390 at 10 bp), though not a stronger signal;
- LambdaMART and pairwise ranking failed to improve ordering; and
- eight PIT aggregate analyst features failed on their evaluable folds.

These results elevate the **data** gap over the model gap. The next defensible
replication is a broad SEC-as-reported characteristic panel with regularized
linear and boosted-tree baselines—not a third ranking loss, a graph, or a deep
distributional model.
