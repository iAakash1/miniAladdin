# OmniSignal Quantitative Scoring Framework (v2 + v2.1 amendments)

> **v2.1 amendments (July 2026, from docs/QUANT-REVIEW.md).** Implemented in
> `src/scoring/engine.py` (`scoring-v2.1`):
>
> 1. **Momentum anchor is 12-1** (twelve-month return excluding the most
>    recent month — Jegadeesh–Titman 1993), member weight 2.0. `r21` is
>    demoted to a timing feature (0.5) and MACD to 0.5 (trend-collinear).
> 2. **Return-type factors use t-statistic normalization**: z = r/(σ_MAD·√h)
>    — "how many multiples of its own noise is this move". Self-history
>    z-scores null out on steady trends (a stock down 30% would read
>    'normal for itself'); the t-stat preserves trend sign while staying
>    per-name adaptive and outlier-robust. Oscillators (MACD, volume ratio,
>    RSI) keep distribution-z; 52w-high proximity uses a level prior
>    (center 0.85, σ 0.10 — the George–Hwang effect *is* the level).
> 3. **Reversal is one sleeve** (5d-return t-stat ⊕ RSI z, contrarian),
>    weight 0.05 normally, **0.20 only in high-volatility regimes** funded
>    by the momentum halving (Nagel 2012; Daniel–Moskowitz 2016). RSI is
>    display-only elsewhere.
> 4. **Sleeves & base weights:** momentum 0.40 · fundamental 0.20 (value +
>    analyst + PEAD) · quality 0.15 (GP/A — Novy-Marx; net issuance —
>    Pontiff–Woodgate; asset growth — Cooper et al.; slow, must never
>    dominate momentum) · news 0.20 · reversal 0.05.
> 5. **Macro gate is probabilistic and momentum-only:** p_stress =
>    logistic(−2.0 + 1.07·(−term) + 0.5·NFCI + 0.5·credit_z +
>    0.5·(2·vix_pct−1)); the term coefficient anchors to Estrella–Mishkin
>    (1998); g = 1 − 0.5·p applies to the momentum sleeve's bullish side
>    only — value/quality/news are never macro-suppressed (defensive
>    premia work in drawdowns). SRM curve remains the fallback when fast
>    inputs are missing.
> 6. **News consumes effective evidence** (`src/services/news_scoring.py`):
>    n_eff = Σ reliability·decay(60h half-life)·novelty·confirmation;
>    shrinkage n_eff/(n_eff+6) — stale or repeated stories cannot inflate
>    confidence.
> 7. **PEAD**: earnings-surprise t vs a conservative 5% σ, linearly decayed
>    over the 60-day drift window (Bernard–Thomas 1989); absent data ⇒
>    absent factor.
> 8. **Confidence adds** u_fresh (price/news staleness vs stated τ),
>    u_model (1 − IC_rolling/0.05, capped 0.30; "unmeasured" costs half the
>    cap), u_stab (0.10 per verdict flip in the last six signals, cap
>    0.30), u_macro (peak at p_stress = 0.5 — maximal regime ambiguity).
>    Loss attribution remains exact and itemized.
> 9. **Risk v2** components (weight — measure): downside semi-dev 0.20,
>    tail (rolling VaR₉₅ percentile) 0.15, drawdown state 0.12, vol regime
>    +vol-of-vol 0.13, beta level+stability 0.10, idiosyncratic share
>    (1−R² vs SPY) 0.10, Amihud liquidity 0.08, macro (p_stress) 0.07,
>    sector 0.05, event floor +5. Each row exposes weight × percentile =
>    contribution; the rows sum to the score.

*(The v2 text below remains the base specification; where it conflicts with
the amendments above, v2.1 governs.)*

A transparent, explainable factor model. No deep learning, no black boxes,
no arbitrary thresholds: every transformation has a stated statistical
rationale, every weight derives from a stated assumption you can challenge
and change in one place (`src/scoring/engine.py` mirrors this document
constant-for-constant).

Replaces the v1 five-layer if/else point system. v1 remains in the codebase
solely as a fallback for tickers with insufficient price history (< 60 bars).

---

## 0. Design principles

1. **Standardize before you combine.** Raw indicator values (RSI 68, MACD
   0.4, upside 12%) live on incomparable scales. Everything becomes a
   dimensionless score in [−1, +1] before aggregation.
2. **Self-normalization over universal thresholds.** "RSI > 70 is
   overbought" is folklore; a stock that habitually trades at RSI 65 differs
   from one that lives at 45. Each factor is standardized against *its own
   trailing distribution* (252 trading days) — the security is its own
   control group. This is what removes arbitrary numbers from the system.
3. **Robust statistics.** Financial data has fat tails; means and standard
   deviations are dominated by outliers. We use median/MAD everywhere.
4. **Families, then factors.** Correlated signals (RSI, 21d return, MACD all
   proxy momentum) must not be triple-counted. Factors aggregate into
   families with equal risk inside a family; families carry the weights.
5. **Alpha and regime are separate.** Stock-specific signal (what to think
   about NVDA) and macro regime (whether to trust bullishness at all) are
   computed independently; the regime *gates* the signal — the same
   architecture as v1's SRM dampening, now continuous.
6. **Uncertainty is an output, not an excuse.** Disagreement between
   families, missing data, event proximity and upstream data quality are
   measured and reported, never hidden.

---

## 1. Normalization pipeline

For factor value \(x\) with trailing history \(H = \{x_{t-251},…,x_t\}\):

**Step 1 — robust z-score.**
\[ z = \frac{x - \mathrm{median}(H)}{1.4826 \cdot \mathrm{MAD}(H)} \]
MAD = median absolute deviation. The constant 1.4826 makes MAD a consistent
estimator of σ under normality (standard robust-statistics result), so z is
readable as "sigmas from typical" while ignoring outliers by construction.
If MAD = 0 (degenerate history), the factor is dropped and counted against
data completeness (§5).

**Step 2 — winsorization.** \(z \leftarrow \mathrm{clip}(z, -3, +3)\).
±3σ covers 99.7% of a normal distribution; anything beyond is treated as
"very extreme" rather than "infinitely extreme". This is the outlier fence.

**Step 3 — squashing.** \(s = \tanh(z/2) \in (-1, +1)\).
tanh is monotone and ≈ linear near zero (no information lost for ordinary
readings) and saturates at extremes — encoding diminishing marginal
information: the difference between 2σ and 3σ readings matters less than
between 0 and 1σ. Dividing by 2 places z = ±2 at s ≈ ±0.76, keeping
meaningful resolution across the typical range. This replaces every v1
cliff-edge (`if rsi > 70: score -= 2`).

**Directionality.** Each factor is signed so that positive s = bullish
*by construction*, documented per factor below.

---

## 2. Factor families

### Momentum family (M)

| Factor | Definition | Sign convention | Rationale |
|---|---|---|---|
| r21 | 21-day return, z vs own history | + = bullish | Classic intermediate momentum (Jegadeesh–Titman 1993): 1-month scale continuation |
| r63 | 63-day return, z | + = bullish | Quarterly momentum; slower confirmation of r21 |
| RSI-dev | RSI-14 deviation from its own 252d median, z | **− = bullish** (contrarian) | Wilder's mean-reversion reading, but *relative to the stock's own regime*, not fixed 30/70 |
| MACD-h | MACD histogram ÷ price, z | + = bullish | Trend inflection; price-normalized so it compares across price levels |
| rev5 | 5-day return, z | **− = bullish** (contrarian) | Short-term reversal effect (Jegadeesh 1990; Lehmann 1990): 1-week moves partially revert |
| vol-conf | 21d avg volume ÷ 63d avg volume, z, × sign(r21) | confirms r21 | Volume-confirmed moves persist; unconfirmed moves fade (participation) |
| 52w-prox | price ÷ 52-week high, z | + = bullish | 52-week-high momentum (George–Hwang 2004): proximity to highs predicts continuation |
| rel21 | r21 − SPY r21, z | + = bullish | Relative strength vs market strips beta out of momentum |

Family score: equal-weight mean of available members' s-values. Equal weight
inside the family is deliberate: with ≤ 252 observations, estimating a
stable intra-family covariance matrix is statistically hopeless — equal
weighting is the honest regularization (a diagonal shrinkage taken to its
limit), and it keeps the family fully explainable.

### Fundamental family (F)

| Factor | Definition | Sign | Rationale |
|---|---|---|---|
| target-up | Analyst target upside, shrunk: \(u' = u \cdot \frac{k}{k+σ_u}\) with prior strength from analyst count when available | + = bullish | Consensus targets have weak but positive predictive power (Brav–Lehavy 2003); shrinkage toward 0 tempers stale/extreme targets |
| e-yield | (1/PE) vs its own trailing distribution where history exists, else vs bounded prior | + = bullish (cheap) | Value expressed as yield (bounded, defined for high PE), not raw PE (unbounded) |
| pe-gap | (trailing PE − forward PE) ÷ trailing PE, clipped | + = bullish | Forward < trailing ⇒ expected earnings growth at current price |

### News family (N)

Headline sentiment already lives in [−1, 1]. The family applies **empirical
Bayes shrinkage** for sample size:
\[ N = \bar{s} \cdot \frac{n}{n + n_0}, \quad n_0 = 6 \]
\(\bar s\) = mean headline score, n = headline count. n₀ = 6 is the prior
strength: three headlines move the score to a third of face value; twelve
headlines (our fetch limit) to two-thirds. Justification: single-name news
sentiment from keyword scoring is the noisiest input we have; the shrinkage
prior says "a handful of headlines should not dominate price-derived
signals", and n₀ is set so that the *maximum* news evidence we ever collect
(n = 12) still cannot claim full confidence. The keyword scorer itself is
unchanged (transparent, inspectable).

### Macro regime (G) — a gate, not a factor

SRM ∈ [0.5, 1.6] from FRED (unchanged math) maps to a continuous gate:
\[ g(\mathrm{SRM}) = 1 - \lambda \cdot \max\!\big(0, \tanh\!\tfrac{\mathrm{SRM} - 1.1}{0.15}\big), \quad \lambda = 0.5 \]
Applied **asymmetrically to bullish scores only** (final = A·g when A > 0):
elevated systemic risk historically punishes long positions (drawdown
clustering), while bearish signals in bad regimes are, if anything, more
reliable. Center 1.1 = v1's ELEVATED boundary; scale 0.15 spans the v1
[1.1, 1.4] dampening band smoothly; λ = 0.5 caps the gate at halving a
bullish score in the worst regime — mirroring v1's maximum two-step
demotion (Strong Buy → Hold ≈ halving) so behavior stays anchored to the
system users already understand, now without discontinuities.

---

## 3. Family weights — derived, not asserted

Weights follow **Grinold–Kahn**: for approximately independent signals, the
optimal contribution is proportional to IR² (squared information ratio).
Stated long-run IR assumptions (single-name, monthly-horizon, from the
factor literature; challenge them in one table):

| Family | Assumed IR | Basis | IR² | Normalized weight |
|---|---|---|---|---|
| Momentum | 0.67 | Strongest replicated single-name anomaly family (J–T momentum, 52w-high, reversal) | 0.45 | **0.45** |
| Fundamental | 0.55 | Value/analyst-revision signals: real but weaker at 1-month horizon | 0.30 | **0.30** |
| News | 0.50 | Fast-decaying, noisy at single-name scale with keyword scoring | 0.25 | **0.25** |

\( w_f = IR_f^2 / \sum IR^2 \). These are *priors*, not fitted parameters —
fitting them on our own history would be in-sample theater. The engine
exposes them as named constants with this table cited.

### Regime-conditional weight adjustments

Multiplicative adjustments, then renormalize to Σw = 1. Each multiplier is
anchored to a documented empirical effect, not tuned:

**High-volatility regime** — trigger: realized 21d vol above its own 252d
80th percentile.
Momentum family × **0.5**, and *within* momentum, the contrarian members
(RSI-dev, rev5) double their internal weight. Basis: momentum crashes
concentrate in high-volatility rebound regimes where the momentum premium
roughly halves or inverts (Daniel–Moskowitz 2016); reversal effects
strengthen in panics. 0.5 ≈ the calm/turbulent momentum-IR ratio in that
literature.

**Earnings proximity** — trigger: confirmed earnings date within 5 trading
days (yfinance calendar; skipped silently when unavailable).
target-up × **0.5** (pre-announcement consensus is stalest exactly then),
News family × **1.5** (information flow concentrates in news), and the
uncertainty floor rises (§5) because single-name event risk (implied moves
≈ 2–3× daily vol) dominates any signal.

**Fed event proximity** — trigger: FOMC decision within 3 trading days
(static public schedule, 8/year, in `fomc_calendar.py`).
Gate center shifts 1.1 → **1.05** (macro risk priced sooner) and confidence
× **0.85**. Basis: pre-FOMC drift and elevated macro sensitivity around
announcements (Lucca–Moench 2015); the specific numbers implement "one
notch more cautious" — the smallest interpretable step, applied to the gate
rather than to alpha, keeping stock-specific signal intact.

---

## 4. Composite, conflict, and mapping

**Raw score.** \( A_0 = \sum_f w_f s_f \in (-1, 1) \); macro gate:
\( A = A_0 \cdot g(\mathrm{SRM}) \) if \(A_0 > 0\), else \(A = A_0\).

**Conflict index.** Weighted sign-disagreement between families:
\[ C = \frac{\sum_{i<j} w_i w_j \, \mathbb{1}[s_i s_j < 0] \cdot \min(|s_i|, |s_j|)}{\sum_{i<j} w_i w_j} \in [0, 1) \]
Two strong families pointing opposite ways ⇒ high C; a strong family
against a negligible one ⇒ low C (the `min` term). Conflicting indicators
are thereby *detected and quantified*, not averaged away silently.

**Verdict mapping.** Under the tanh squash, family scores are roughly
centered with dispersion ≈ 0.4; with the weight vector above and average
inter-family correlation ≈ 0.3, the composite's standard deviation is
σ_A ≈ 0.28. Cut points are set in σ_A units — they have distributional
meaning, not vibes:

| Verdict | Condition | Meaning |
|---|---|---|
| Strong Buy / Strong Sell | \| A \| ≥ 0.40 | ≈ 1.4 σ_A — tail conviction (~16% of days) |
| Buy / Sell | \| A \| ≥ 0.15 | ≈ 0.5 σ_A — modest but real tilt |
| Hold | \| A \| < 0.15 | the middle ~60% of the composite's distribution |

---

## 5. Uncertainty and confidence

Three independent doubt sources compose multiplicatively (independent
failure modes: doubt compounds, it doesn't average):

\[ U = 1 - (1 - u_{\text{disp}})(1 - u_{\text{data}})(1 - u_{\text{event}}) \]

- \(u_{\text{disp}}\): weighted dispersion of family scores around A₀,
  normalized by the maximum possible dispersion — high when families
  disagree in magnitude, complements C's sign view.
- \(u_{\text{data}}\) = 1 − (computable factors ÷ total factors), degraded
  further by the provider layer's own confidence (a stale-cache price
  series honestly propagates into signal uncertainty).
- \(u_{\text{event}}\): 0.25 inside an earnings window, 0.15 inside a Fed
  window (event risk floor; both ⇒ compose to 0.36).

**Confidence** \(= 100 \cdot (1 - U)(1 - C/2)\), clipped to **[5, 95]** —
the model is never allowed to claim certainty or total ignorance, an
epistemic-honesty guardrail cheaper than calibration curves.

**Risk score** (0–100, continuous; replaces the LOW/MED/HIGH cliff for the
scorecard while the API keeps the categorical field): weighted blend of
vol percentile (40%), |max drawdown| percentile (25%), beta excess over 1
(20%), SRM position in [0.5, 1.6] (15%) — weights ordered by how directly
each measures realized loss potential for a single name; vol first because
it *is* the loss distribution's scale parameter.

---

## 6. Outputs (the explainability contract)

Every scoring run emits a `ScoreCard`:

```
raw_score (A), gated + ungated · verdict · confidence (5–95)
uncertainty components (dispersion / data / event) · conflict index
momentum_score · fundamental_score · news_score · macro_gate
risk_score (0–100) + its components
weights actually used (post-regime, renormalized) + active regime flags
per-factor rows: value → z → s → family weight → contribution to A
```

The per-factor contribution table is the audit trail: `A` is *exactly* the
sum of its rows. The LLM explanation layer receives the ScoreCard and may
only narrate it — same single-source-of-truth rule as everything else.

---

## 7. Additional free signals

Implemented in v2 (all derivable from data already flowing):
63d momentum · 5d reversal · volume confirmation · 52-week-high proximity ·
relative strength vs SPY · earnings yield · PE gap · vol-percentile regime
flag · earnings/FOMC calendars.

Worth adding next (still free):
- **Amihud illiquidity** (mean |r|/dollar-volume): liquidity premium proxy
  and a risk-score input; computable from the OHLCV we already fetch.
- **Overnight vs intraday return split**: informed flow tends to show up
  overnight; ratio is a sentiment-quality check on price action.
- **Earnings surprise history** (yfinance): post-earnings-announcement
  drift (PEAD) — a documented, slow-decaying anomaly.
- **Realized-vol term structure** (5d vs 21d vs 63d): rising short-vol vs
  long-vol is an early risk flag, sharper than level percentiles.
- **Sector relative strength** (vs sector ETF rather than SPY) once a
  ticker→sector-ETF map is added; removes sector beta from rel21.

Explicitly rejected: fitted factor weights (in-sample overfitting with one
name and 252 points), deep learning (opaque; sample sizes here would
memorize noise), intraday signals (free data too unreliable).
