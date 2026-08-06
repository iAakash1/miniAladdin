# Factor Lab

> A factor does not claim NVDA will rise. It claims the names it ranks highly
> will outperform the names it ranks poorly. Every other view in OmniSignal
> examines one stock, and that shape cannot tell a working factor from a
> market that went up.

`/terminal/factors` · `GET /api/factors`

---

## 1. Why it exists

The point-in-time panel was justified in `docs/PANEL.md` by a sentence about
layout: *"cross-sectional ranking reads one factor column across all symbols
on a date."* Nothing did that. The panel had been built, vectorized to 31×,
tested against the engine to 1e-12 — and had no consumer that used it the way
its design assumed.

This is that consumer, and it answers a question the product could not
previously ask.

## 2. What it measures

**Rank IC** — Spearman correlation, on each observation date, between a
factor's cross-sectional ranking and the *subsequent* forward return. One
number per date; a factor that works has a positive mean.

Rank rather than Pearson: factor scores are already `tanh`-squashed and
returns are fat-tailed, so a linear correlation measures the tails while the
claim is about ordering.

**Quantile spread** — mean forward return of the top bucket minus the bottom.
The IC says ordering carries information; the spread says how much. They can
disagree, and the disagreement is a finding, not an error.

**Saturation** — share of scores sitting exactly on the winsorization bound
(`tanh(WINSOR_Z / SQUASH_SCALE)`). See §5.

## 3. The statistic that matters most

A 21-day forward return sampled every 5 days means consecutive observations
share 16 of their 21 days. They are not independent, and the naive
`mean / (std / √n)` assumes they are.

Every t-statistic here is **Newey–West corrected** with a Bartlett kernel over
`ceil(horizon / step) − 1` lags. Measured on the mega-cap universe, the naive
statistic was inflated **1.20×–1.58×** depending on the factor.

The UI shows both, always. Showing only the corrected number would be honest;
showing both teaches why the correction exists and makes the gap impossible
to miss.

The empirical case is a test, not a claim:
`test_correction_controls_the_false_positive_rate` generates pure noise with
zero true mean, and measures how often each statistic declares significance.
The naive one rejects far above its nominal 5%; the corrected one does not.

## 4. What it found

Mega-cap 30, ~2.5 years, 21-day horizon, weekly observations, 3,068 evaluable
cells across 133 dates:

| Factor | Mean IC | Naive t | **Newey–West t** | Inflation | Top−bottom | Significant |
| --- | --- | --- | --- | --- | --- | --- |
| vol_confirm | +0.0213 | 1.08 | **0.83** | 1.30× | +1.04% | no |
| r12_1 | +0.0369 | 1.23 | **0.77** | 1.58× | +2.19% | no |
| rel21_vs_spy | +0.0295 | 1.07 | **0.74** | 1.45× | +1.29% | no |
| high52_prox | +0.0254 | 1.03 | **0.72** | 1.42× | +1.29% | no |
| r21 | +0.0165 | 0.72 | **0.52** | 1.40× | +1.03% | no |
| reversal | −0.0088 | −0.36 | **−0.30** | 1.20× | −0.35% | no |
| r63 | +0.0091 | 0.38 | **0.26** | 1.50× | +0.32% | no |

**No factor in the scoring engine is statistically significant on this
sample.** Mean ICs are positive and directionally sensible — momentum
strongest, reversal negative — but none survives the overlap correction.

That is the honest result, and the page states it in its header rather than
burying it. A research tool whose UI only looks good when the answer is
favourable is a marketing tool.

## 5. The finding this view produced on its own

`r12_1` clips **24% of the mega-cap universe** at the winsorization bound —
six of twenty-five names carrying an identical score of `tanh(1.5) = 0.9051`.
Every other price factor clips under 5%.

Those six names are not ranked relative to each other. The factor has
discarded ordering information at exactly the end a long/short reading
depends on, which caps the IC it can achieve no matter how good the
underlying signal is.

No single-ticker view could surface that. It is only visible when you read
one factor column across a whole universe on one date, which is precisely
what the panel's layout was designed for.

## 6. What it would have done to money

IC says a factor orders names correctly. It does not say you would have made
money, because it does not compound, does not account for the trading a
rebalance implies, and does not show the path.

Each rebalance date the simulator ranks the universe, goes equal-weight long
the top quintile and short the bottom, holds one week, repeats. **The holding
period equals the rebalance interval, so periods never overlap** — which is
why the Sharpe ratio here needs no Newey-West correction, unlike the IC above.
The overlap is designed out rather than corrected for.

| Factor | Total | Sharpe | Max DD | Turnover | Universe (EW) | Beat it |
| --- | --- | --- | --- | --- | --- | --- |
| r12_1 | +48.4% | 0.52 | −24.9% | 15% | +64.8% | **no** |
| reversal | +9.8% | 0.13 | −34.3% | 66% | +65.9% | **no** |
| high52_prox | +8.2% | 0.09 | −29.6% | 24% | +63.1% | **no** |
| vol_confirm | +4.0% | 0.07 | −24.1% | 49% | +65.0% | **no** |
| rel21_vs_spy | −7.4% | −0.12 | −28.0% | 41% | +43.0% | **no** |
| r21 | −8.2% | −0.11 | −31.2% | 65.9% | +65.9% | **no** |
| r63 | −12.6% | −0.17 | −41.3% | 23% | +66.0% | **no** |

**Not one factor beat holding the universe equally weighted.** Three lost
money. Every one carried a drawdown between 24% and 41%.

And costs are not modelled. `reversal` turns over 66% of its book every week;
at any realistic cost assumption its +9.8% is comfortably negative. Turnover
is reported per factor precisely so a reader can apply their own assumption
rather than inherit one invented here.

The long and short legs are reported separately, because a long/short curve
that merely tracks the market is a directional bet wearing a factor's name.

## 7. The screen — and where the factors disagree

The composite ranks every name by the mean of its factor percentiles, computed
*within the date* so the output is explicitly relative.

Its most useful column is not the rank. It is **conviction**: two names can
carry an identical composite while one has every factor agreeing and the other
is split down the middle. The mean cannot separate them; agreement can.

```
screen 2026-08-05   spread=43pts   mean agreement=0.49

 #  SYM   COMP  AGREE  CONVICTION   STRONGEST      WEAKEST
 1  MRK     71   0.64  mixed        r12_1          r21
 2  KO      70   0.67  mixed        high52_prox    vol_confirm
 3  JPM     67   0.60  mixed        high52_prox    reversal
 4  ABBV    67   0.36  conflicted   vol_confirm    rel21_vs_spy
 5  CSCO    64   0.24  conflicted   r63            vol_confirm

conviction mix: 13 mixed, 12 conflicted, 0 aligned
```

**Not one name in the mega-cap universe has its factors aligned today.** ABBV
and CSCO rank 4th and 5th on the composite while being the two most
internally contradictory names in the top ten — a distinction the rank alone
actively hides.

**Equal weights, on purpose.** The obvious refinement is to weight each factor
by its measured IC. It is rejected because §4 showed no factor is
statistically significant, so IC-weighting would fit weights to noise and
present the result as though it were informed. A weaker claim is the correct
claim when the evidence is weak.

`dispersion` reports when the universe is barely differentiated at all — a day
where the engine has no opinion, which is more useful to say than to present a
ranking that is noise ordered by luck.

## 8. Did it work *recently*?

A mean IC over 2.5 years is one number covering 130 observations. It cannot
tell a factor that worked steadily from one that worked in 2024 and has been
dead since — and those are entirely different propositions for someone
deciding whether to use it now.

| Factor | First half | Second half | Sign flips | Verdict |
| --- | --- | --- | --- | --- |
| rel21_vs_spy | +0.0638 | **−0.0047** | 6 | **worked earlier and stopped** |
| reversal | +0.0268 | **−0.0443** | 5 | **worked earlier and stopped** |
| r12_1 | +0.0637 | +0.0102 | 8 | weakened 6× |
| r21 | −0.0388 | +0.0717 | 7 | improved (was negative) |
| r63 | −0.0391 | +0.0573 | 5 | improved (was negative) |
| vol_confirm | +0.0015 | +0.0409 | 6 | improved |
| high52_prox | +0.0170 | +0.0336 | 7 | stable |

**The two strongest factors in the first half are the two that stopped
working.** `r12_1`, the best-performing factor in every pooled statistic on
this page, decayed six-fold. Meanwhile `r21` and `r63` were actively *negative*
early and turned positive later.

Every factor crossed zero between five and eight times. Nothing here is
stable, and the pooled mean IC in §4 conceals all of it.

`concentration` measures the share of total IC contributed by the single best
window. Above 60% the verdict says so plainly: an edge living in one stretch
is an anecdote, not a factor.

None of this is a forecast. Every statistic is descriptive — this is what the
factor did, split by time, with no claim that any of it persists.

## 9. Seven factors, or three?

The screen (§7) averages every factor equally, which assumes each contributes
something new. That assumption is testable, and it does not hold.

```
7 factors behave like 3.2 independent ones — heavily overlapping

         r12_1    r63    r21  vol_c  high52  rel21  revers
r12_1    +1.00  +0.40  +0.05  -0.03   +0.49  +0.05   -0.03
r63      +0.40  +1.00  +0.55  +0.13   +0.69  +0.56   -0.35
r21      +0.05  +0.55  +1.00  +0.19   +0.53  +0.97   -0.64
vol_c    -0.03  +0.13  +0.19  +1.00   +0.05  +0.22   -0.07
high52   +0.49  +0.69  +0.53  +0.05   +1.00  +0.51   -0.41
rel21    +0.05  +0.56  +0.97  +0.51   +0.51  +1.00   -0.63
revers   -0.03  -0.35  -0.64  -0.07   -0.41  -0.63   +1.00
```

**`r21` and `rel21_vs_spy` correlate at 0.967.** They are the same signal: a
21-day return, and a 21-day return measured against SPY. Over a mega-cap
universe whose names largely *are* the index, subtracting the benchmark
removes almost nothing.

`reversal` is strongly *negative* against the momentum family (−0.64 vs
`r21`), which is expected — it is contrarian by construction — but it means it
is not an independent seventh opinion either; it is momentum with the sign
flipped and noise added.

The participation ratio of the correlation matrix's eigenvalues,
`N_eff = (Σλ)² / Σλ²`, puts the effective count at **3.2**. Equal weighting
therefore gives the momentum family roughly triple the vote it should have,
which is a direct criticism of §7's composite and is stated there rather than
buried here.

Unmeasured pairs are treated as uncorrelated when computing eigenvalues — the
assumption that *understates* redundancy, chosen because the conservative
direction for a claim about independence is to under-claim it.

## 10. How much do the factors explain?

Each date's cross-section of returns is regressed on that date's factor
exposures, one date at a time, and the coefficients averaged — the
Fama–MacBeth arrangement. Per date rather than pooled, because pooling would
let a day when everything rose masquerade as a factor return.
`test_market_wide_moves_are_absorbed_by_the_intercept` pins that.

```
raw R²  0.475      adjusted  0.196      overfit gap  0.280

FACTOR          RETURN PER 1σ        t
r63                    +0.864%    1.78
vol_confirm            +0.451%    1.41
reversal               −0.442%   −0.75
```

**Raw R² would have overstated the model by more than double.** Seven
predictors on ~25 names produces roughly 0.28 of fit from chance alone, so the
adjusted figure is what the page reports and the raw one appears only as a
footnote. Presenting 47% would have been the single most misleading number in
this product.

The honest reading: **the factors explain about 20% of cross-sectional return
variance, and no factor's return is significant at |t| > 2.** Most of what
moves these names is not in the model.

Exposures are z-scored within each date, so a coefficient is the return to a
one-standard-deviation tilt — comparable across factors with different
cross-sectional dispersion. Standard errors come from the time-series
variation of the per-date coefficients, which is what Fama–MacBeth is for.

## 11. A new factor, and how it failed

`asset_growth` is the first factor built on point-in-time SEC XBRL rather than
price data: total assets year-over-year, sign-inverted after Cooper, Gulen and
Schill (2008), where firms expanding their balance sheet fastest subsequently
underperform. Every figure is dated by its filing, so a restatement enters the
history exactly when it was published (`src/panel/fundamentals.py`).

It was put through the same panels as everything else. It did not survive:

| | Value |
| --- | --- |
| Mean rank IC | **−0.0091** |
| Newey–West t | **−0.23** |
| Long/short total | **−27.0%** |
| Sharpe | **−0.44** |
| Turnover | 2% |

The worst performer of the eight, on every measure. The inverted sign is the
tell: the long side (slow asset growth) *underperformed*. Over 2024–2026 the
mega-cap universe is dominated by firms expanding aggressively into AI capex,
and the anomaly — documented on broad universes including small caps — points
the wrong way on thirty of the largest companies in the world.

Turnover of 2% is the second tell. Annual filings barely move, so this is a
nearly static long/short book, which makes −27% a sustained directional bet
rather than a factor effect.

### The rule this establishes

**The panel is where factors are tested. The engine is where survivors go.**

`asset_growth` stays in the research panel, because its failure is evidence
and deleting it would hide a result this tool exists to show. It does **not**
enter `src/scoring/engine.py`, because nothing has demonstrated it should.

A factor earns a place in the production engine by surviving validation, not
by being plausible, well-cited, or already implemented.

## 12. Caveats ship inside the payload

Not in documentation nobody reads — `_caveats()` returns them with every
response and the page renders them open by default:

- **Multiple comparisons.** Seven factors were tested. Even with no real
  predictive power, the chance at least one looks significant at 5% is ~30%.
  Judge the set, not the best member.
- **Overlapping windows.** Corrected, with the uncorrected value shown beside
  it.
- **Survivorship bias.** Membership is current, not historical.
- **Price factors only.** Fundamental, quality and news sleeves need
  point-in-time filing dates that are not wired; absent, not approximated.
- **Sample size.** ~2 years of free-tier history. Suggestive at best.

## 13. Cost

Cold: ~29 s for 30 names over 2.5 years — dominated by fetching price history
through the bounded fan-out, not by computation. Warm: milliseconds, with a
1-hour TTL, because factor evidence over years does not change between two
page loads.

A universe below `MIN_NAMES_PER_DATE` (10) returns an explanation rather than
an empty page: a rank correlation over five names is noise, not a ranking.

## 14. Two joins, deliberately different

`evaluable` is an **inner** join of panel and forward returns: measuring a
factor requires knowing what happened next, so open windows cannot contribute
an IC.

`rankable` is a **left** join: the engine's ranking *today* is knowable today
and is the most useful row on the page. The first version of this service
used the inner join for both, which silently hid the current cross-section —
found by running it, not by a test.
