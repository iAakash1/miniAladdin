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

---

## Semantic invariants now enforced in code

- A path-dependent metric may not be computed on an out-of-order dated series.
- A ratio to gross profit is undefined when there is no gross profit.
- A Newey-West lag count is derived from the label in hand, never from a
  constant, and never with floor division.
- `periods_per_year` and `holding_periods` carry no defaults; a wrong value is
  invisible in the output.
- A covariance that cannot describe a real book is refused, not clamped.
- Zero risk and unmeasurable risk are distinguishable in the output.

## Remaining audit surface

Not yet swept: timezone handling on the ingestion boundary; resampling
semantics (`label`/`closed` on any downsample); small-sample behaviour of the
PBO/CSCV path; the bootstrap's block construction under a non-integer
horizon/step ratio.

Ranked suspects for the next pass, by flattering-direction risk:

1. Turnover is reported one-way (`Σ|Δw| / 2`) while costs are charged on the
   full `Σ|Δw|`. Each convention is defensible alone, but a reader reconciling
   the two reported figures infers a cost rate 2× the real one.
2. `np.log1p(returns).fillna(0.0).cumsum()` in `macro.py` treats a missing
   market day as a flat day. Defensible — NaN would destroy the path — but it
   understates volatility across a gap and is not annotated.
3. Pairwise covariance admits pairs with very short shared history at full
   confidence. Now refused when it produces an invalid matrix, but a thin-but-
   valid estimate is still reported without a coverage figure.

---

## Verification

1472 tests pass. Diff over `experiments/`, `artifacts/`, `data/research/` and
`src/quant/study/heavy.py` is empty. EXP-007 still reads NO PRODUCTION
CANDIDATE, failing `survives_search_size` at t=2.81 against the 3.38 required
for 1,029 cumulative trials. The holdout is untouched, the contract is
NOT_ARMED, production count is 0, and the cost assumption is unchanged.
