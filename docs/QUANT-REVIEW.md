# OmniSignal Quantitative Methodology Review

*Written as an external referee report on the v2 engine (docs/SCORING.md).
Engineering is assumed correct; only the statistics are on trial. Every
recommendation preserves explainability — nothing here requires a black box.*

---

## Section 1 — The current factor universe, challenged

**r21 (21-day return). Keep, but demote.** One-month momentum is the *weakest*
horizon in the momentum literature — at 1 month, returns exhibit *reversal*
in the cross-section (Jegadeesh 1990), and 21d overlaps mechanically with the
21d forward horizon used in validation, flattering IC. The canonical spec is
**12-1** (twelve months excluding the most recent month; Jegadeesh–Titman
1993, Fama–French UMD). Verdict: keep r21 as a *timing* input, add 12-1 as
the primary momentum anchor (Section 2), shift intra-family emphasis to it.

**r63 (63-day return). Keep.** Quarterly momentum sits inside the well-
documented 3–12m continuation band. Should decay: signal content is stale
when the most recent month contradicts it — interact with r21 sign
(agreement → full weight; disagreement → half). Cheap, explainable
interaction with literature support (echoes the 12-1 skip logic).

**RSI-dev (contrarian). Remove or merge.** RSI is a bounded transform of
recent returns — it is r5/r14 information wearing a costume. Its z vs own
median correlates ≈ −0.7+ with rev5 by construction. Two contrarian entries
in one equal-weighted family double-count reversal and dilute trend. Verdict:
fold RSI-dev and rev5 into **one reversal sleeve** (Section 4), retain RSI in
the UI as a descriptive statistic, not a scored factor.

**rev5 (5-day reversal). Keep, but regime-gate it.** Short-term reversal is
real but is substantially a liquidity-provision premium: it *strengthens* in
high-volatility, dealer-constrained markets (Nagel 2012) and has decayed in
calm, liquid large-caps post-2000 (Avramov, Chordia, Goyal 2006). Currently
it drags the momentum family toward zero IC in trends — my own synthetic
walk-forward shows exactly this dilution. Verdict: reversal sleeve active
only in the high-volatility regime (where its evidence lives), weight ≈ 0
otherwise.

**MACD histogram. Weaken.** MACD is EMA(12)−EMA(26) smoothing — collinear
with r21/r63 (same trend PC). It adds no orthogonal information, only a lag
structure. Keep for explainability continuity at half its implicit weight, or
residualize against r21/r63 (Section 4) so only its *incremental* signal
scores.

**Volume confirmation. Keep, refine.** Volume-conditioned momentum has
support (Lee–Swaminathan 2000: high-volume winners continue harder). Current
sign(r21)×volume-ratio is crude but honest. Improvement: use it as an
*interaction multiplier on the trend cluster* (0.75–1.25×) rather than an
additive factor — that is what the literature actually documents.

**52-week-high proximity. Keep.** George–Hwang (2004) show it subsumes much
of plain momentum with slower decay; anchoring-based, robust. It is,
however, in the same trend cluster (Section 4) — one more reason to weight
clusters, not raw factors.

**rel21 vs SPY. Keep, extend window.** Relative strength strips market beta
from momentum — correct instinct, wrong horizon. 21d relative is noisy;
126d idiosyncratic momentum (residual return, Blitz–Huij–Martens 2011) is
more stable and less crowded than raw momentum. Extend, keep both briefly,
retire 21d if the panel IC (Section 10) confirms.

**Analyst target upside. Replace the level with the revision.** Post-Reg-FD,
consensus *levels* are systematically optimistic (mean implied upside ≈
+15%, Brav–Lehavy 2003) and near-zero alpha; what predicts is the **change**
— revision momentum and drift (Womack 1996; Gleason–Lee 2003). The current
shrinkage-toward-zero treats the symptom. Verdict: keep the shrunken level
at reduced weight *until* target/estimate snapshots accumulate (we must
start storing them — Section 8), then switch to Δtarget.

**Earnings yield & PE gap. Keep, lengthen the clock.** Value works on
multi-quarter horizons; at 21 days it is nearly noise (Asness et al. "Value
and Momentum Everywhere" — monthly at best). They belong in the composite
for regime balance, not for 1-month timing. Their weight should *rise* as
the stated horizon lengthens; at the current horizon their IR² allocation
(0.30 family) is generous — earned only if panel validation confirms.

**News sentiment. Keep; fix its physics.** The empirical Bayes shrinkage
n/(n+6) is sound. What is missing is *time*: news alpha decays in days
(Tetlock 2007; Chan 2003), and stale, repeated news carries no alpha
(Tetlock 2011). Currently a 6-day-old headline weighs like this morning's.
Section 7.

**Macro SRM gate. Keep the asymmetry, upgrade the inputs.** Direction is
right (momentum crashes cluster in stressed rebounds — Daniel–Moskowitz
2016). Problems: inputs are slow (monthly CPI), thresholds are step
functions of three series, and the gate ignores *market-priced* stress.
Section 9.

---

## Section 2 — New factors worth adding (free-data feasible first)

| Factor | Rationale | Pred. power | Stability | Free data | Complexity | Explainability |
|---|---|---|---|---|---|---|
| **12-1 momentum** | Jegadeesh–Titman 1993; the single most replicated anomaly; skip-month avoids reversal contamination | High (cross-sectionally) | High (decades, global) | ✅ already fetch 1y; needs 13m | Trivial | "Up 34% over the past year excl. last month" |
| **PEAD / earnings surprise** | Bernard–Thomas 1989; drift persists 60+ days post-announcement; among the most robust anomalies | High | High | ✅ yfinance earnings dates + surprise % | Low | "Beat by 8%, drift historically continues" |
| **Net share issuance / buybacks** | Pontiff–Woodgate 2008; Ikenberry 1995 — issuance predicts negative, buybacks positive returns; slow-moving, uncrowded | Medium-high | Very high | ✅ shares outstanding (FMP/yfinance) | Low | "Share count −3% y/y: management is buying" |
| **Gross profitability (GP/A)** | Novy-Marx 2013 — "the other side of value"; quality sleeve with value-like premia, negative correlation to value | Medium-high | High | ✅ FMP income statement/balance sheet | Medium | "Gross profits 41% of assets vs sector 18%" |
| **Asset growth (negative)** | Cooper–Gulen–Schill 2008; aggressive balance-sheet expansion predicts underperformance | Medium | High | ✅ FMP balance sheets | Medium | "Assets grew 45% y/y — historically a drag" |
| **Idiosyncratic momentum (126d residual)** | Blitz–Huij–Martens 2011; momentum net of beta is more stable, smaller crashes | Medium-high | High | ✅ have stock+SPY series | Low | "Beat the market by 12% over six months" |
| **Idiosyncratic volatility (negative)** | Ang–Hodrick–Xing–Zhang 2006; high idio-vol → low subsequent returns | Medium | Medium (debated) | ✅ residual vol from existing series | Low | "Stock-specific noise in the 95th pct" |
| **Short interest** | Rapach–Ringgenberg–Zhou 2016; high SI predicts underperformance | Medium | Medium (squeeze tail!) | ✅ yfinance shortPercentOfFloat (bi-weekly, lagged) | Low | "18% of float short" — plus squeeze flag |
| **IV skew / put-call from options** | Xing–Zhang–Zhao 2010: steep put skew predicts underperformance ~1m | Medium | Medium | ✅ yfinance option chains (quality varies) | High | "Options market paying up for crash protection" |
| **Credit spread (BAA-10Y) + NFCI** | Gilchrist–Zakrajšek 2012 (EBP); NFCI is a weekly financial-conditions nowcast | High (as regime) | High | ✅ FRED, weekly | Trivial | Macro engine inputs, Section 9 |
| **Analyst revision momentum** | Womack 1996; Gleason–Lee 2003 | High | High | ⚠️ needs snapshot accumulation (start now) | Medium | "Targets raised 3× in 6 weeks" |
| Seasonality (turn-of-month etc.) | Real but tiny, capacity-constrained, invites data mining | Low | Low | ✅ | Trivial | Skip — not worth a weight |

Deliberately excluded: 13F institutional positioning (45-day lag kills the
free version), ETF flows (no reliable free source), FX/commodity cross-asset
(second-order for single US names vs added complexity).

---

## Section 3 — Weighting, redesigned

Current: static Grinold–Kahn IR² priors with regime multipliers. Honest, but
it never learns. The upgrade path, in order of statistical safety:

1. **Shrinkage IC weighting (do first).** Posterior IR per cluster =
   κ·IR_prior + (1−κ)·IC_realized, with κ = τ²/(τ² + σ²_IC/n) — i.e. trust
   realized rolling IC in proportion to its sample size, anchored to the
   literature prior. Weight ∝ posterior². This is empirical-Bayes / James–
   Stein logic: it cannot be worse than the prior asymptotically, and every
   weight remains a two-term sum a PM can read.
2. **EWMA online IC (cheap adaptivity).** IC_t = λ·IC_{t−1} + (1−λ)·ic_t with
   λ ≈ 0.97 weekly (~6-month half-life). Feeds (1). No optimizer, no
   overfitting surface, fully auditable.
3. **Regime switching, formalized.** Replace ad-hoc multipliers with weights
   *conditioned on regime state* estimated per regime from the walk-forward:
   w_f|regime ∝ posterior IR²_f|regime. Same math, partitioned samples. The
   current 0.5× momentum-in-high-vol becomes an estimated, not asserted,
   quantity (Daniel–Moskowitz gives the prior).
4. **Orthogonal cluster weighting (with Section 4).** Weight *clusters*
   (trend, reversal, quality, value, sentiment) whose members are averaged
   internally — the current family idea, done at the right granularity.
   Grinold–Kahn assumes independence; clusters restore it approximately.
5. **Reliability multiplier.** Scale each cluster by its calibration ratio
   (realized hit rate ÷ implied hit rate, capped [0.7, 1.3]) — factors that
   systematically overpromise get taxed.
6. **What NOT to do:** full Bayesian model averaging over factor subsets,
   mean-variance optimized weights, or any gradient-fit — with one name and
   weekly samples these are overfitting machines wearing lab coats.

---

## Section 4 — Multicollinearity

The trend cluster is one factor in five costumes: r21, r63, MACD-hist,
52w-prox, rel21 share a dominant PC (pairwise |ρ| plausibly 0.5–0.85; VIFs
well above 5 for MACD given r21+r63). The contrarian pair (RSI-dev, rev5) is
a second cluster (ρ ≈ 0.7 by construction). Equal-weighting *within* a
family already mitigates double-counting, but the family map should match
the correlation map:

- **Correlation clustering (do this, not PCA):** hierarchical clustering on
  the rolling factor-score correlation matrix → sleeves: TREND {12-1, r63,
  52w-prox, MACD-resid}, TIMING/REVERSAL {rev5 ⊕ RSI-dev merged},
  PARTICIPATION {volume interaction}, RELATIVE {idio-mom}, VALUE {e-yield,
  PE-gap}, QUALITY {GP/A, issuance, asset growth}, SENTIMENT {news},
  ANALYST {revisions}. Weight sleeves; average inside.
- **Residualization where one factor claims increment:** MACD-hist ←
  residual of regression on (r21, r63); analyst revisions ← residual on
  price momentum (revisions partly chase price — Womack). Keeps each
  sleeve's *stated meaning* intact.
- **PCA: rejected.** PC2 of a momentum block has no name; a PM cannot
  challenge "eigenvector 2 disagrees". Explainability is a hard constraint.
- **VIF as monitoring, not modeling:** publish rolling VIFs per factor in
  validation; alert > 10.

---

## Section 5 — Confidence, formalized

Keep the multiplicative-doubt architecture (independent failure modes
compound); expand the term set and ground two terms in realized data:

**C = 100 · (1 − u_disp) · (1 − u_data) · (1 − u_fresh) · (1 − u_event) ·
(1 − u_macro) · (1 − u_model) · (1 − u_stab) · (1 − C_conflict/2), clipped [5, 95]**

- u_disp — weighted dispersion of sleeve scores (existing).
- u_data — 1 − completeness × provider confidence (existing).
- u_fresh — staleness: Σ_k w_k · min(1, age_k/τ_k) with τ = data-type
  half-life (prices 1d, news 2d, fundamentals 90d, macro 35d). *New.*
- u_event — earnings/FOMC floors (existing), plus realized-vol-spike flag.
- u_macro — g(SRM, NFCI z, credit-spread z): uncertainty, not direction —
  wide macro dispersion lowers confidence even when the gate is open. *New.*
- u_model — 1 − max(0, IC_ewma)/IC_ref (IC_ref ≈ 0.05): if the engine has
  not been working recently *on this name*, it must say so. The backtest
  infrastructure already computes the input. *New — highest value.*
- u_stab — verdict flip rate over the last 6 signals (3+ flips → 0.3):
  a signal that cannot make up its mind deserves no conviction. *New.*
- C_conflict — existing conflict index, unchanged.

Every u is a named, bounded, individually reportable number — the confidence
decomposition table stays exact.

---

## Section 6 — Risk, upgraded to a composite that would survive a risk desk

**R = 100 · Σ w_i · pct_i**, percentiles vs own 3y history where available:

| Component | w | Measure | Why |
|---|---|---|---|
| Downside deviation | 0.20 | semi-dev of daily returns (21d) pct | Investors price downside, not variance (Sortino logic) |
| Tail risk | 0.15 | CVaR₉₅ of daily returns (250d) pct | Mean of worst 5% — the number a risk desk quotes |
| Drawdown state | 0.12 | current DD depth × recovery time pct | Path risk; distinct from vol |
| Vol regime | 0.13 | 21d vol pct **and** vol-of-vol trend | Rising short vol > high stable vol |
| Beta level + stability | 0.10 | β and rolling-β std (126d) | Unstable beta = unhedgeable beta |
| Idiosyncratic share | 0.10 | 1 − R² vs SPY (126d) | Name-specific blowup capacity |
| Liquidity | 0.08 | Amihud |r|/$vol pct | Exit cost under stress; free from OHLCV |
| Macro | 0.07 | SRM/NFCI/credit-z blend | Systematic backdrop |
| Sector concentration | 0.03 | sector ETF vol pct | Sector crash channel |
| Event proximity | 0.02→floor | earnings/FOMC window | Behaves as a floor-raiser, not weight |

Weights ordered by directness of loss measurement; each row renders as
"component → percentile → contribution", same explainability contract as the
alpha side. Factor-risk decomposition proper (Barra-style) is a Section 12
long-term item — it needs a cross-sectional universe.

---

## Section 7 — News methodology

- **Decay:** weight_i = s_i · 0.5^(age_h/60h). News alpha lives in days
  (Chan 2003); a week-old headline is context, not signal.
- **Novelty (stale-news filter):** cosine/Jaccard similarity vs trailing 7-day
  headline set; repeated stories get novelty < 1 multiplier (Tetlock 2011 —
  stale news moves prices *less and reverses more*).
- **Cross-source confirmation:** same event from k independent tier-1/2
  domains → confirmation multiplier 1 + min(0.5, 0.2(k−1)); single-source
  from tier-3 → 0.6. Source tiers already exist in the evidence pipeline —
  reuse them in sentiment.
- **Event typing:** small keyword taxonomy {earnings, guidance, M&A,
  litigation/regulatory, product, analyst action, macro-passthrough} with
  type-priors on magnitude and half-life (M&A: large, slow; analyst action:
  medium, fast). Explainable as "guidance cut (high-impact class)".
- **Clustering = dedupe done right:** cluster by (type, entities, 48h
  window); score clusters, not headlines — kills double-counting a story
  arc, enables narrative labeling ("3 stories this week about supply
  constraints").
- **False-positive filter:** ticker-symbol collisions (e.g. "A", "ALL") —
  require company-name co-mention for ≤2-letter symbols; drop headlines
  where the ticker appears only in a list of 5+ symbols.
- **News confidence:** n_eff = Σ novelty_i·decay_i replaces raw n in the
  n/(n+6) shrinkage — the same formula, but counting *effective* evidence.

---

## Section 8 — Analyst modeling

The consensus *level* is the least informative analyst statistic. Ranked by
evidence: (1) **revision momentum** — direction and count of target/EPS
changes over 4–13 weeks (Womack 1996; drift persists weeks-to-months);
(2) **estimate dispersion** — high dispersion predicts *underperformance*
(Diether–Malloy–Scherbina 2002) and should also feed u_disp in confidence;
(3) **recency-weighted consensus** — half-life ~60d on individual estimates
rather than the flat mean; (4) **consensus drift** — the sign of Δconsensus
over 3m as a slow confirmation factor. Broker quality and per-analyst
accuracy require attribution data that is not free — acknowledge, skip.
Action item now: begin persisting daily consensus snapshots (target, EPS
estimates, count) server-side; every one of these factors is a derivative of
that history, and the history cannot be bought later.

---

## Section 9 — The macro engine, challenged

**Should it be multiplicative?** For a *single-name, long-only-verdict*
product: the multiplicative gate on positive scores is equivalent to
raising the Buy thresholds — and the threshold framing is *more* honest
("the bar is higher in this regime") with identical ordering. Recommended
reframe: publish the gate as an explicit threshold shift: CUT_ACTION' =
CUT_ACTION / g(SRM). Same math, better narrative.

**Additive?** No — an additive macro penalty would flip weak-positive names
to Sell on macro alone, converting a *selection* engine into a *timing*
engine without timing evidence. Macro should modulate conviction, not
fabricate direction.

**Probabilistic — yes.** Replace step penalties with a recession/stress
probability: p = logistic(a + b·term_spread + c·NFCI + d·credit_spread_z),
coefficients from Estrella–Mishkin (1998) as priors. Then g = 1 − λ·p.
Continuous, literature-anchored, and the response can *say* "stress
probability 34%".

**Volatility-dependent — yes:** add realized SPY vol and VIX percentile to
the regime state; the high-vol regime currently triggers off single-name vol
only, missing systemic spikes.

**Differential effects — yes, and the literature is specific:** momentum is
the crash-prone factor in stress (dampen hard — already done); **value and
quality should NOT be gated** — quality/low-vol are the defensive premia
that *work* in drawdowns (Asness–Frazzini–Pedersen QMJ); analyst factors
should be *frozen* (staleness spikes around macro shocks) rather than
dampened; news weight can *rise* modestly in stress (information flow
matters more when priors break). Apply g to the trend sleeve only; leave
value/quality ungated; freeze analyst inputs older than τ during FOMC/CPI
windows.

---

## Section 10 — The validation framework this engine deserves

1. **Panel (cross-sectional) validation — the single most important gap.**
   Time-series IC on one name conflates selection skill with market timing.
   Run the engine nightly over a fixed universe (e.g., S&P 100 — free
   data), compute **daily cross-sectional Rank IC** between scores and
   forward 21d returns. That is the institutional IC. Everything else
   inherits from this panel.
2. **Purged, embargoed walk-forward** (López de Prado 2018): 21d overlapping
   labels are serially correlated; purge training/eval overlap and embargo
   5 days to stop leakage that inflates IC.
3. **Metrics per period and cumulative:** Rank IC (mean, t-stat via
   Newey–West for overlap), IC decay curve by horizon (5/10/21/63d),
   precision/recall per verdict class, top-minus-bottom quintile spread,
   Sharpe/Sortino/Calmar with **Deflated Sharpe** (Bailey–López de Prado)
   against the number of variants ever tried, profit factor, turnover
   (signal changes × assumed spread), capacity note (Amihud-weighted).
4. **Calibration as a first-class output:** reliability curve + Brier score
   for the implied hit probability; recalibrate confidence mapping annually
   on the panel, never on the display path.
5. **Stability & drift:** rolling factor weights, factor IC half-lives,
   score-distribution PSI (population stability index) vs trailing year —
   alert on PSI > 0.25; prediction-flip rate per name.
6. **Baselines or it doesn't count:** naive 12-1 momentum and buy-and-hold
   as reference strategies in every report; the engine must beat the naive
   factor it is built from, or the extra machinery is decoration.
7. **Overfitting control:** CSCV/PBO (probability of backtest overfitting)
   whenever weights are re-estimated; log every experiment — the deflation
   denominator is the count of things tried, including the discarded ones.

---

## Section 11 — Where OmniSignal fails, and how it should know

| Scenario | Failure mechanism | Detection | Mitigation |
|---|---|---|---|
| **Momentum crash / junk rally** (2009-Q2 type) | Trend sleeve max-short the rebound; reversal sleeve underweighted | SPY drawdown > 20% AND 21d SPY vol pct > 90 AND breadth thrust (sectors-above-50d jumps > 40pp in 2w) | Regime flag "post-panic rebound": trend sleeve → 0.25×, reversal sleeve activated, confidence cap 60 |
| **Bubble melt-up** (1999, AI-mania) | Every trend factor saturates max-bullish exactly at the top; value factor's warning is outvoted | e-yield z < −2 while trend sleeve > +0.8 and 52w-prox ≈ 1.0 for > 6m | Valuation brake: Strong Buy requires value sleeve > −1.5σ; else cap at Buy with "valuation-capped" note |
| **Panic / COVID gap** | All price-derived factors instantly stale; macro monthly data blind for weeks | 1d SPY move > 4σ or single-name vol > 99th pct | Circuit state: force Hold + confidence floor 20 for 5 sessions; NFCI (weekly) partially covers macro blindness |
| **Rate shock** (2022) | Monthly CPI/Fed inputs lag the repricing; duration-heavy names mis-scored | 2Y yield 21d change pct > 95 | Rate-shock regime: raise u_macro, gate applies to long-duration sectors' rel-strength comparisons |
| **Meme / short squeeze** | Price momentum reads mania as signal; fundamentals disconnect | volume ratio > 5× AND rel21 > +3σ AND (if available) short interest > 15% | "Unmodeled dynamics" flag: confidence cap 40, verdict capped at Hold, explicit banner — this is honesty, not alpha |
| **Illiquid names** | Reversal/vol factors dominated by microstructure noise | Amihud pct > 95 or dollar vol < $1M/day | Widen u_data, suppress reversal sleeve, disclose "signal reliability limited by liquidity" |
| **Sector crash contagion** | Single-name view misses sector factor risk | Sector ETF drawdown > 15% in 21d | Sector-stress term raises risk score + caps sleeve weights toward defensive |

The unifying principle: **the model must detect when it is outside its
training distribution and respond by lowering conviction — not by guessing
with confidence.** Every detector above is a threshold on data already
flowing.

---

## Section 12 — Roadmap, ranked

*(Pred = expected predictive improvement; Int = interpretability retained)*

**Immediate (days, free data, low risk)**
1. 12-1 momentum + skip-month; demote r21 — Pred ★★★★, complexity ★, Int ★★★★★
2. News decay + novelty + n_eff shrinkage — Pred ★★★, ★, ★★★★★
3. NFCI + credit spread into a probabilistic gate (trend-sleeve-only) — Pred ★★★, ★, ★★★★★
4. Reversal sleeve regime-gating; merge RSI-dev into it — Pred ★★★, ★, ★★★★★
5. Risk composite v2 (CVaR, semi-dev, idio share, Amihud, β-stability) — Pred ★★ (risk quality), ★★, ★★★★★
6. u_model + u_stab confidence terms from existing backtest plumbing — Pred ★★★ (trust quality), ★★, ★★★★★
7. Begin persisting analyst-consensus snapshots (data asset, zero model change) — Pred ★★★★ (future), ★, n/a

**High impact (weeks)**
8. PEAD/earnings-surprise factor — Pred ★★★★, ★★, ★★★★★
9. Net issuance + GP/A + asset-growth quality sleeve — Pred ★★★★, ★★★, ★★★★
10. Panel validation on S&P 100 with purged/embargoed CV, Newey–West IC t-stats, baselines — Pred ★★★★★ (truth quality), ★★★, ★★★★★
11. Shrinkage/EWMA-IC adaptive sleeve weights — Pred ★★★, ★★, ★★★★
12. Failure-mode detectors + circuit states (Section 11 table) — Pred ★★★ (tail protection), ★★, ★★★★★

**Research queue**
13. Analyst revision momentum + dispersion (once snapshots accrue ≥ 2 quarters) — Pred ★★★★, ★★, ★★★★
14. IV skew / put-call from free option chains — Pred ★★★, ★★★★, ★★★
15. Short interest + squeeze flag — Pred ★★, ★★, ★★★★
16. News event-type taxonomy + clustering — Pred ★★★, ★★★, ★★★★★

**Long-term institutional**
17. Cross-sectional universe product (score all names daily; relative ranks are where factor investing actually lives) — Pred ★★★★★, ★★★★★, ★★★★
18. Barra-lite factor risk decomposition on that universe — ★★★, ★★★★, ★★★★
19. Deflated-Sharpe / PBO experiment registry as governance — truth infrastructure, ★★, ★★★★★

**Rejected on principle:** deep learning (uninspectable at this data scale),
intraday signals from free feeds (garbage in), fitted per-name weights
(n≈250 weekly points cannot support them), seasonality dummies (data-mining
bait with negligible capacity).
