# Semantic correctness audit

Scope: hunt for results that are plausible, internally consistent, and wrong —
with attention to errors that bias in a flattering direction. Not a style
review, not a feature pass. No experiment was run, no model trained, no
backtest executed, the holdout was not touched, and no recorded artifact was
modified.

The test for whether something belongs here: **would a competent reader,
looking at the output, have any reason to doubt it?** A number that is wrong
and obviously wrong is a bug. A number that is wrong and looks right is this
document.

---

## Defects found and fixed

### 1. Path-dependent metrics silently changed with input order

`max_drawdown`, `ulcer_index`, `average_drawdown`, `calmar`,
`drawdown_at_risk`, `conditional_drawdown_at_risk`,
`ulcer_performance_index`, `drawdown_series` and `drawdown_profile` all walk a
series with `cumprod`/`cummax`. On a date-indexed series that was not sorted,
they walked the wrong path and returned a different plausible number.

Measured on 200 observations, shuffling the rows moved maximum drawdown from
−0.0959 to −0.1185, the ulcer index from 0.0462 to 0.0509, and Calmar from 1.75
to 1.42. `drawdown_profile` reported a trough *date*, which on a shuffled
series is meaningless.

Nothing raised, and the whole suite passed, because every fixture in it is
built sorted.

**Fix.** The nine metrics refuse a date-indexed series that is not
monotonically increasing (`UnorderedSeries`). A positional index is left alone:
there, row order *is* the intended order and there is nothing to contradict.
Order-independent metrics — volatility, Sharpe, MAD, VaR, worst realization —
are untouched and tested to prove it. This follows
`pit.calendar.require_chronological`, whose docstring already made the case:
relying on every caller to remember is the arrangement that produced the
`merge_asof` defect.

### 2. `cost_share_of_gross` reported a share of a loss

The denominator was an absolute value. A strategy that lost 10% before costs
and paid 5% in friction reported **0.50** — the identical number to one that
turned +10% into +5%. Read on its own, which is how a leaderboard column is
read, it says friction ate half the edge. There was no edge.

The ratio also moved the wrong way: the more a strategy lost gross, the
*smaller* its reported cost share, because only the denominator grew. Losing
money bought a better cost profile.

That number is a promotion threshold, capped at 0.75 to catch strategies that
are really transaction-cost bets. A gross-losing candidate could clear the
ceiling while being the exact thing it screens for.

Across the recorded experiments **52 rows** had a gross loss and a positive
cost share; **20 sat under the ceiling**. EXP-006's `baseline_historical_mean`
on `fwd_rank_21` recorded 0.197 next to a gross Sharpe of **−6.13**.

**Fix.** Defined only when there is gross profit to take a share of, `None`
otherwise. `thresholds_not_met` already counts a missing value as unmet, so it
fails closed. `gross_total_return` is reported alongside so the sign is visible
rather than inferred.

**Not fixed, deliberately:** the recorded artifacts. EXP-004 through EXP-007
keep the numbers they were computed with. No registry entry carried this
metric — all 103 have it absent — so no promotion decision consumed a corrupted
value.

### 3. Newey-West lag counts taken from a constant, not the label

`performance_by_regime` accepted `label` as an argument and then passed
`horizon_sessions=21, step_sessions=5` to `ic_summary` regardless. Four of the
five labels in the repository are not 21 sessions; `fwd_ret_63` needs 12 lags
where the constant supplied 4.

Under-correction does not look like a bug. The t-statistic stays plausible and
sits beside a `newey_west_lags` field that makes it look accounted for. Only
the size is wrong, and it is wrong upward.

On 300 pure-noise draws carrying the dependence a 63-session label sampled
every 5 sessions imposes, 4 lags inflated |t| by a median of **1.39×**, and
**13% of those draws cleared the |t| ≥ 2.0 significance gate** that the correct
lag count fails.

Two more sites had the same shape:

- `run.py` derived attribution's `holding_periods` with `horizon // step`.
  Floor leaves one overlapping observation uncorrected, so a 21/5 label got 3
  lags where `ic_summary`, on identical geometry, uses 4. **The two paths
  disagreed with each other.** Now uses `LabelGeometry.block_length`.
- `attribute_returns` kept `holding_periods: int = 4` one line below the
  comment explaining why `periods_per_year` had been made required. Same file,
  same class of default. Now required.

### 4. An invalid covariance rendered as a book with no risk

`risk_contributions` computed volatility as `sqrt(max(variance, 0.0))`. A
negative variance is not a small number to be clamped — it is proof the matrix
is not a covariance matrix. The clamp turned that proof into zero, the zero
fell through the `portfolio_vol <= 0` branch, and the function returned a table
where **every position contributes 0.0 risk with a 0.0 share**.

The identity assertion guarding that table passed, because zero sums to zero.

The matrices are not hypothetical. `covariance()` calls pandas `.cov()`, which
estimates each entry on whichever rows that pair happens to share. On fifteen
names loading on a common factor with staggered listing dates — an ordinary
universe — the most negative eigenvalue is **−1.6e−04 against a ridge of
1e−08**, some 16,000× too small to repair it, and real weight vectors produce
`w'Cw < 0`. Names whose histories never overlap give NaN entries, which reached
the same silent zero (20 of 36 entries in one test).

**Fix.** Negative variance beyond float noise, and non-finite entries, raise
`NotPositiveSemiDefinite`. A genuinely riskless book and an empty book still
report zero, because there zero is true — the two cases were previously
indistinguishable in the output. `quant_portfolio_service` catches it and
reports `risk_contributions_unavailable` with the reason; each position's
`risk_share` already fell back to `None`, so the table degrades to an em dash
per row rather than to a confident zero.

**Not fixed, deliberately:** the covariance estimator. Its docstring argues that
changing it silently would move every historical risk number, and that applies
to a minimum-overlap floor as much as to the Ledoit-Wolf shrinkage it declines.
The invalid *result* is refused instead.

---

### 5. Reported turnover and the reported cost rate did not reconcile

Costs are charged on the round-trip notional `sum|dw|`, which is right —
replacing a 100%-gross book end to end trades 200% of capital. Turnover was
reported one-way, `sum|dw|/2`, which is also standard. Neither formula is wrong.

The **interface** was. A reader multiplying displayed turnover by the displayed
6 bps got $600 on a full replacement of a $1m book against the $1,200 actually
charged, with nothing on any surface saying the two sat on different bases.

**Fix.** No convention changed and no recorded number moved. `assumptions()` now
declares `charged_on`, the reporting convention, `rate_bps`, `slippage_bps`
(a real parameter that was absent from the published assumptions), and the
reconciling identity. Reports carry `turnover_round_trip` and
`cost_rate_bps_of_traded_notional`, which now equals the declared rate.

### 6. Two more variance clamps, one of them driving leverage

The covariance defect had siblings, each written independently:

| site | clamp | result |
|---|---|---|
| `risk/engine.py` | `sqrt(max(v, 0.0))` | zero risk (fixed earlier) |
| `optimizer.py:544` | `sqrt(max(v, 0.0))` | zero ex-ante volatility |
| `optimizer.py:293` | `sqrt(max(w'Cw, 1e-24))` | divides by 1e-12 |

The ex-ante one is worst because something divides by it. On 20,000 random books
over an indefinite covariance, **1,576 reported an ex-ante volatility of exactly
zero** and 445 a positive but understated one. Volatility targeting scales by
`target/realised`, so a 10% target against an understated 0.012% **levers the
book 832×**. When the value was exactly zero, `realised > 0` skipped the scaling
in silence and nothing said the requested target had not been applied.

The risk-parity floor was self-defeating: 1e-24 passed the `> 0` check
immediately below it.

**Fix.** `portfolio/psd.py` is now the single implementation, with a
**scale-aware** tolerance — an absolute threshold is meaningless when daily
equity variances sit near 1e-4.

### 7. The factor independence verdict was built on a fill

`analyse_redundancy` fills unobserved factor pairs with zero correlation. The
fill is unavoidable. The comment calling it *conservative* was not: understating
redundancy **overstates independence**, which is the direction the verdict
flatters. Six factors correlated 0.9 have 1.19 effective factors; blank twelve of
fifteen pairs and they report **3.31**, rising monotonically with each pair
removed.

**Fix.** The fill stays — nothing honest replaces it — but coverage travels with
the number, and below 75% the verdict is withheld rather than computed from the
fill.

### 8. Session dates were read off UTC

Daily bars arrive as an epoch stamp and their session date was read in UTC. That
is right for a US venue **only because Eastern is behind UTC**. A stamp after
20:00 ET has already crossed midnight UTC (a 20:01 bar on 14 June was dated
15 June), and any venue east of UTC inverts the sign — midnight in Tokyo is
15:00 UTC the previous day.

**Fix.** `pit.calendar` owns `EXCHANGE_TIMEZONE` and `session_date_from_epoch`.
No historical bar moves: Polygon stamps at midnight ET and a test asserts old and
new readings agree across both 2024 DST transitions, with a further test proving
the offset really changes between them.

### 9. Regression residuals used the wrong degrees of freedom

`residual_volatility` used `np.std(residuals, ddof=1)`. A regression residual is
not a sample mean deviation: fitting k coefficients consumes k degrees of
freedom. Dividing by n−1 understates idiosyncratic risk by 1.2% at n=250 against
six factors, **21% at n=20** — and understated residual risk makes a book look
better explained by its factors than it is. Feeds no gate.

The HAC estimator applies no finite-sample `n/(n−k)` correction. Both conventions
exist, so it is **documented rather than changed** — omitting it makes every t
larger by `sqrt(n/(n−k))`, 1.4% at n=250. The classical fallback path *does* use
n−k, so the two paths scale differently.

## False alarms — investigated, correct as they stand

Recorded so the same ground is not re-ploughed.

| Suspect | Why it looked wrong | Why it is right |
|---|---|---|
| `macro.py` drawdown peak uses `rolling(252, min_periods=63)` | A partial window should mean a shallower peak and a flattering drawdown | On early rows a 252-window spans *all history that exists*, so it equals the expanding peak exactly. Measured understatement: **0.0000**. The 63 floor prevents a drawdown computed from 20 days, it does not shorten the lookback. |
| `market_vol_percentile` uses `rolling(504, min_periods=252)` | Same shape | Same reason; a percentile floor, not a truncated window |
| `beta` benchmark alignment | A missing benchmark date becoming zero would bias beta toward 0 | Uses `join="inner"` — intersection only. No fabricated observation. |
| `ddof` across estimators | A mix of 0 and 1 across std/var/cov would make ratios inconsistent | `ddof=1` throughout, including both halves of the beta ratio |
| `calmar` in `backtest/engine.py` uses `abs(drawdown)` | The same sign-loss shape as defect 2 | Correct: the drawdown is negative by convention and the *numerator's* sign is preserved, so a losing strategy still gets a negative Calmar |
| Gate `ic_t_stat` accepts `abs(t) >= 2.0` | Accepts a strongly negative IC | Labelled `">= 2.0 (absolute)"`, and `sign_matches_validation` is a separate gate |
| "the declared 10 bp" vs a 5 bp default half-spread | Looked like a declared/applied mismatch | "10 bp" is the 10 bp **half-spread** row of the cost sweep, a *stricter* assumption than the default. Conservative. |
| Cost model bps conversion | A factor of 100 or 10,000 here is catastrophic | `bps / 10000.0` throughout; the impact path's ×10000 then ÷10000 is a round trip for reporting in bps |
| `cost_fraction = cost.total / capital` | Dividing by capital twice is the classic error | Correct: `traded = Σ|Δw| × capital`, so the fraction is `Σ|Δw| × bps/1e4` |
| Deflated-Sharpe denominator clamp `max(denominator, 1e-12)` | A clamped variance would inflate DSR, and DSR is a promotion gate | Already fails closed: `denominator <= 0` returns `deflated_probability=None` with a note, so the clamped value never reaches a reported number |
| Only one `resample` in the codebase | `mean()` where compounding is intended is the classic error | `(1+r).groupby(period).prod() - 1` — correctly geometric |
| Benchmark-relative metrics (`tracking_error`, `information_ratio`, `capm_alpha`) | A missing benchmark date becoming zero | All use `join="inner"` with `.dropna()`, and each reports the surviving observation count |
| `macro.py` `rolling(504, min_periods=252)` volatility percentile | Partial window presented as full | Same as the drawdown peak: a floor, not a truncated lookback |

---

## Capability added this pass

Gaps against the source corpus that could be closed honestly — every one a
deterministic transformation of data already present, none requiring new data.

| Capability | Why it was missing and what it adds |
|---|---|
| **EVaR / EDaR** | Coherent tail measures. EVaR is the tightest Chernoff bound on VaR and sits above CVaR by construction, so the pair brackets the tail rather than describing it with one average. Minimised in log space, since `exp(L/z)` overflows for the small `z` the optimiser probes and an overflow reads as an unbounded tail. |
| **Gini mean difference** | Dispersion with no distributional assumption, via the O(n log n) rank identity. Verified against the normal and uniform closed forms. |
| **Omega ratio** | Uses the whole distribution, separating series a Sharpe ratio cannot. Returns None when nothing falls below the threshold, rather than a huge number reading as a spectacular result. |
| **Lower partial moments** | Explicit threshold, because "downside" means nothing until someone says below what. |
| **Diversification ratio** | Closed form, correct at both limits (1 for identical names, √k for k independent ones). |
| **Named covariance estimators** | `empirical` (complete-case), `ledoit_wolf`, `exponentially_weighted` — all PSD by construction, which the pairwise default is not. The default is untouched; these are chosen, not substituted. |

## Refused, with the measurement behind the refusal

**Effective number of bets.** The standard principal-axis construction is *not a
function of its inputs*. For k equal-variance uncorrelated names the covariance
is σ²·I and every orthonormal basis is an eigenbasis: ten independent names
return **10.000** under one basis and **3.770** under another, with the
covariance unchanged. Sample noise picks the basis in practice, so ten
independent names measured from 4,000 observations report **6.50**. A number that
moves with an arbitrary rotation can call a concentrated book diversified.
Meucci's minimum-torsion rotation is the fix; it is not implemented from memory.

This was found by testing against a known limit rather than against the
implementation — the only reason it surfaced.

## Semantic invariants now enforced in code

- A path-dependent metric may not be computed on an out-of-order dated series.
- A ratio to gross profit is undefined when there is no gross profit.
- A Newey-West lag count is derived from the label in hand, never from a
  constant, and never with floor division.
- `periods_per_year` and `holding_periods` carry no defaults; a wrong value is
  invisible in the output.
- A covariance that cannot describe a real book is refused, not clamped, by one
  scale-aware implementation rather than three floors.
- Zero risk and unmeasurable risk are distinguishable in the output.
- A cost rate and a turnover figure published together must reconcile.
- A calendar date is resolved in the venue's timezone, never in UTC.
- A regression residual is divided by n−k.
- A claim about independence is withheld when most pairs were never observed.

## Remaining audit surface

Swept and clean: resampling (one site, correctly geometric), index alignment on
the benchmark path (inner joins throughout, observation counts reported),
degrees of freedom (consistent `ddof=1` for sample statistics).

Not yet swept: small-sample behaviour of the PBO/CSCV path; the bootstrap's
block construction under a non-integer horizon/step ratio; provider-level
missingness on the ingestion boundary.

Ranked suspects for the next pass, by flattering-direction risk:

1. `np.log1p(returns).fillna(0.0).cumsum()` in `macro.py` treats a missing
   market day as a flat day. Defensible — NaN would destroy the path — but it
   understates volatility across a gap and is not annotated.
2. Pairwise covariance admits pairs with very short shared history at full
   confidence. Now refused when it produces an invalid matrix, and named
   alternatives exist, but a thin-but-valid pairwise estimate is still reported
   without a coverage figure.
3. Partial first and last buckets in the monthly aggregation are presented
   beside complete months with no marker.
4. The `turnover_tolerable <= 30x` gate reads the one-way figure. Defensible,
   but the gate text does not say which basis, and the study code is under a
   do-not-modify constraint.

---

## Verification

1,639 tests pass. Diff over `experiments/`, `artifacts/`, `data/research/` and
`src/quant/study/heavy.py` is empty. EXP-007 still reads NO PRODUCTION
CANDIDATE, failing `survives_search_size` at t=2.81 against the 3.38 required
for 1,029 cumulative trials. The holdout is untouched, the contract is
NOT_ARMED, production count is 0, and the cost assumption is unchanged.
