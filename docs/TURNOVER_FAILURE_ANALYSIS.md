# EXP-006 turnover failure — independent verification and decomposition

Date: 2026-09-19. Baseline commit `176d6b7`. Nothing here refits a model or
touches the sealed holdout. The decomposition in §3 reads **predictions and
held sets only — no forward return** — so it cannot be tuned on outcomes.
Reproduce with `python -m scripts.quant.exp009a diagnose`; the aggregate output
is `experiments/EXP-009A/turnover_diagnostics.json` (no licensed data).

## 1. The 20.15x figure is verified, twice

The frozen 100,246 out-of-sample gradient-boosting predictions
(`experiments/EXP-006/predictions_fwd_rank_21.parquet`, sha256
`d7616f54…a747`) were joined to a returns panel **rebuilt** from the local raw
store with the same `DatasetBuilder` EXP-006 used, capped at the last
prediction date (2025-05-09). Two checks establish the panel is the panel
EXP-006 traded on:

* all 100,246 predictions found a forward return;
* the within-date rank of the rebuilt 21-session return equals the label stored
  with the predictions on every one of 404 dates (mean Spearman 1.0, minimum
  0.9999999999999998). `fwd_ret_21` is used only for this identity check.

The unchanged engine then reproduced EXP-006's recorded gradient-boosting
backtest **exactly** (relative tolerance 1e-9, and in fact equal to every digit
printed):

| Metric | Reproduced | Recorded in EXP-006 |
|---|---:|---:|
| Periods | 403 | 403 |
| Mean one-way turnover per rebalance | 0.399773636501747 | 0.399773636501747 |
| Annualised one-way turnover | **20.14859** | 20.14859 |
| Gross Sharpe | 0.38444 | 0.38444 |
| Net Sharpe, 10 bp half-spread | −0.10218 | −0.10218 |
| Total cost (sum of period costs) | 0.52096 | 0.52096 |
| Cost share of gross | 1.26607 | 1.26607 |
| Net CAGR | −2.21% | −2.21% |

A **second, independent derivation** — exact integer rank cutoffs (no
`pd.qcut`), its own turnover loop, the engine's 10% per-name weight cap —
gives a mean one-way turnover of 0.39977363650174713, a relative difference of
2.2e-16 from the engine. (A first draft of that derivation differed by 0.25%;
the cause was omitting the weight cap on a 14-name date, see §5. That is why
the cap is now in the derivation and a test pins it.)

**What 20.15x means.** One-way turnover is Σ|Δw|/2 per rebalance, ×50.4
rebalances a year. 0.3998 per rebalance is 0.7995 of gross traded round-trip
each week, i.e. **40.3x annualised round-trip, 3.37 round-trip turns of the
book per month**. In each leg about 40% of the names are replaced every week
(long 41.0%, short 38.5%; 60.3% retained). Measured as the share of a leg
replaced, that is roughly 170% of a leg per month; Novy-Marx & Velikov
(NBER w20721) find that of the anomalies they study only two with more than 50%
one-sided monthly turnover have significant net spreads even when built to
minimise costs — EXP-006 is more than three times that line, in the
equal-weight configuration that paper identifies as the most expensive.
(Their turnover convention was not re-derived here; the comparison is order of
magnitude.)

*Metric-definition note.* The engine's `gross_total_return` metric is the
arithmetic **sum** of period gross returns (0.41148) because it is the
denominator of `cost_share_of_gross`; the **compounded** gross return is
0.40778, which is the figure in EXP-006's saved metrics file. Both are
correct for their purposes; the cost share of 1.2661 uses the sum. New
outputs report the two under separate names.

## 2. Gross, net, and the cost sweep

Gross: CAGR 4.37%, volatility 13.39%, Sharpe 0.384, max drawdown −16.5%.
Net at 10 bp: CAGR −2.21%, Sharpe −0.102, max drawdown −28.8%, compounded total
return −16.4%. Costs total 52.1% of capital-return versus 41.1% gross earned.

| Half-spread | Net Sharpe | Net CAGR | Cost share of gross | Total cost | Net max DD |
|---:|---:|---:|---:|---:|---:|
| 1 bp | +0.169 | +1.40% | 56.1% | 0.231 | −18.6% |
| 3 bp | +0.108 | +0.58% | 71.8% | 0.295 | −20.9% |
| 5 bp | +0.048 | −0.22% | 87.5% | 0.360 | −23.2% |
| **10 bp** | **−0.102** | **−2.21%** | **126.6%** | **0.521** | **−28.8%** |
| 20 bp | −0.403 | −6.08% | 204.9% | 0.843 | −45.2% |

* **Break-even half-spread: 6.6 bp.** Below it the mean net return is positive
  (impact held at its 10 bp value); above it, negative. The sign flips inside
  the plausible range for large caps, which is why the result is fragile as
  well as weak.
* **Composition of cost at 10 bp:** spread 61.9%, market impact 32.0%,
  commission 6.2%. Impact is not negligible at $1M capital because the book
  trades ~0.8 of gross every week.
* **Gross edge per unit traded:** 10.2 bp of gross return per period against
  0.7995 of round-trip turnover — **12.8 bp of gross per unit of round-trip
  traded**, versus an all-in cost of 16.2 bp per unit at 10 bp. Cost per unit
  traded exceeds gross edge per unit traded; that inequality *is* the failure.

## 3. Where the turnover comes from

Share of total one-way turnover by cause (402 consecutive tradable rebalances;
exits and entries each carry about half of the traded notional):

| Source | Exits | Entries |
|---|---:|---:|
| **Adjacent band** — name moved one quintile across the cutoff (Q5↔Q4, Q1↔Q2) | **24.5%** | **24.5%** |
| Mid drift — two quintiles | 10.9% | 10.9% |
| Deep drift — three quintiles | 6.1% | 6.0% |
| **Full reversal** — jumped to the opposite extreme quintile | 4.4% | 4.3% |
| Universe exit / new to cross-section | 3.3% | 3.8% |
| No price row (delisting / missing price) | 0.5% | — |
| Missing observation (in universe, no prediction) | 0.02% | — |
| **Re-weighting of retained names** (leg size changes) | 0.8% | |

* **Nearly half of all turnover (48.9%) is one-quintile boundary movement.**
  Of the exit turnover from names still ranked in the cross-section, 19.8% is
  within 5 percentile points of the cutoff, 33.6% within 10, 53.4% within 20
  and 67.2% within 30.
* **Full reversal — the case that only a better signal can fix — is 8.7%** of
  turnover. **Forced exits and entries (universe reconstitution, missing
  prices) are about 8%** and no portfolio rule can avoid them.
* **Missing observations are not the problem** (0.02%). Data gaps are not what
  drives turnover.
* **The predictions are stable week to week only moderately.** Consecutive
  rebalances' predictions have a mean cross-sectional Spearman of **0.68**
  (worst date −0.26); the mean absolute move in percentile rank is 15.7 points
  (SD 23.0); 33% of names move less than 5 points, 51% less than 10, but **16.7%
  move more than 30 points in a single week**.

## 4. Can turnover fall while the gross information is kept?

Two things are true at once, and the second is the more important.

**Plausible.** The largest single source — one-quintile boundary movement,
48.9% of turnover — is the source a hold-close-substitutes rule removes:
a name ranked 78th percentile one week and 82nd the next is an example of a
name a hard cutoff sells and then buys back. The literature mechanism
(Novy-Marx & Velikov's buy/hold spread; Qlib's bounded-replacement top-k) is
built for exactly this and reports slightly lower gross return for a large
turnover cut. There is therefore a real, identified reason to expect a
turnover reduction of the order of 35–50% from a modest buffer.

**Bounded.** This is an accounting ceiling, not an outcome estimate:
* even a rule that removed *every* adjacent-band exit and entry would leave
  turnover near **10.3x** annualised (51% of 20.15x). At the observed gross
  edge, cost share at 10 bp would still be about **65% of gross**;
* the gross edge itself is small: Sharpe 0.38, CAGR 4.4%, EXP-006's Rank IC
  0.029, factor-alpha t-statistic 0.047. A buffer changes the cost of holding
  a weak signal; it does not make the signal stronger;
* retained names are, by construction, lower-ranked than the entrants they
  replace, so some gross return is given up. How much is the empirical question
  EXP-009A tests, and this document does not answer it because it reads no
  return.

## 5. Data notes found while verifying

* **Two thin rebalance dates.** 2019-09-17 has 174 usable names and
  **2020-02-17 has 14** (all other dates have 247–250). On 2020-02-17 each leg
  has 3 names; equal weight would be 0.167, so the engine's 10% cap binds and
  gross exposure that period is 0.6, not 1.0. Both dates are traded as-is by
  every cell of EXP-009A; they are two of 403 periods.
* **Weight-cap sensitivity of the independent check** — see §1.
* **The one-way convention.** Every "turnover" in the repository is one-way
  (Σ|Δw|/2); the cost model charges the round-trip notional. Reconciliation:
  `cost_return = 2 × turnover × (commission + half-spread) / 10⁴` plus a
  non-linear impact term.

## 6. Root-cause attribution (what this analysis supports)

| Component | Evidence | Weight in the failure |
|---|---|---|
| **Weak information** | Gross Sharpe 0.384, gross CAGR 4.4%, Rank IC 0.029 (detectable, NW t 2.66), alpha t 0.047 after six factors | Primary. Even at zero spread the strategy would be a low-Sharpe book. |
| **Trading intensity** | 20.15x one-way, 40% of a leg replaced weekly; cost per unit traded (16.2 bp) > gross edge per unit traded (12.8 bp); break-even spread 6.6 bp | Decisive for the *sign* of net return. ~49% of it is boundary movement, the addressable part. |
| **Feature/data quality** | Weekly rank stability 0.68; 16.7% of names move >30 points in a week; missing observations only 0.02% of turnover; two thin dates | Secondary. The instability looks like fast-moving inputs in the 27-feature price/volume set, not data gaps. **Not tested here**; it is the reason EXP-009A holds the model fixed. |

Story for the research record: *EXP-006 is a weak but statistically detectable
cross-sectional ranking signal that fails economically because of weak
information combined with extreme turnover.* EXP-009A tests whether the
turnover half can be cut without destroying the information half; it does not
test whether the information is strong enough to matter.
