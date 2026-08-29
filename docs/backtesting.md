# Backtesting and Attribution

A model with 55% directional accuracy can still lose money. This document
describes what stands between an information coefficient and a claim about
returns.

---

## 1. Only out-of-sample predictions reach this layer

`run_backtest` consumes the prediction frame produced by the walk-forward
driver — predictions made by a model fitted on data strictly before the fold it
predicted. There is no code path in `src/quant/backtest/` that can reach a
fitted model or an in-sample prediction. That is what makes the equity curve
mean anything.

---

## 2. Construction

At each rebalance date, names are ranked by prediction; the top quintile is held
long and the bottom quintile short, equal-weighted within each leg, gross
exposure 1.0 split 0.5/0.5 so the book is dollar-neutral.

**Equal weight, not prediction-weighted.** Prediction magnitude at this
signal-to-noise ratio is mostly noise, and weighting by it concentrates the book
in whichever names the model was most extreme about. Equal weight makes a weaker
claim, which is the correct claim.

**Positions formed at `t` earn the return from `t` to the next rebalance.**
Never `t`'s own return. That off-by-one is the most common backtest error there
is, and it manufactures performance exactly proportional to how good the signal
is. `tests/quant/test_backtest.py` asserts a pure-noise signal produces no
systematic profit across twelve independent seeds — a single seed can be
positive by chance, and asserting on one would make the test pass for the wrong
reason.

---

## 3. Costs are charged per rebalance

Not deducted annually at the end. The two give different answers and the naive
one always flatters, because costs interact with turnover, turnover varies with
signal volatility, and a strategy trades hardest exactly when it is most
confident.

| Component | Model | Status |
|---|---|---|
| Commission | `commission_bps` on traded notional | assumption, small and certain |
| Spread | `half_spread_bps` on traded notional | **ASSUMED** — the dataset has no bid/ask |
| Impact | `coefficient · sqrt(traded / daily dollar volume)` | square-root law |

A name held unchanged across a rebalance costs nothing, which is what makes
low-turnover strategies correctly cheaper rather than nominally cheaper.

### The spread is the largest uncertainty, so it is swept

Measured at \$1M capital on a liquid universe:

| Capital | Traded notional | Commission | Spread | Impact | Total |
|---|---|---|---|---|---|
| \$1M | \$100,000 | \$10 | \$50 | \$27 | **8.7 bp** |
| \$500M | \$50,000,000 | \$5,000 | \$25,000 | \$303,988 | **66.8 bp** |

Impact is negligible at small capital and dominant at large — which is the
square-root law behaving correctly, and the reason a strategy's capacity is a
separate question from its Sharpe.

Because the half-spread is assumed, a single net figure is a claim about the
assumption as much as about the strategy. Every backtest is therefore reported
across **1, 5, 10 and 20 bp**, and the UI shows the sweep rather than one
convenient value. Where a result stops surviving is usually the most useful line
in the table.

### What this is not

Not a fill model. No queue position, no partial fill, no intraday path. Every
trade executes at the rebalance date's close, at that close plus costs. This is
stated in `SimpleCostModel.assumptions()["execution"]` and rendered in the UI,
because a reader who believes these are simulated fills would over-trust the
result.

---

## 4. Metrics

Gross and net, reported side by side, both computed from the same period-return
series:

CAGR, total return, annualised volatility, Sharpe, Sortino, maximum drawdown,
Calmar, hit rate, profit factor, best and worst period, downside deviation,
mean and annualised turnover, total cost drag, mean cost in bps per period, and
**cost share of gross return**.

Nothing is emitted unless it is correctly computable. A Sharpe on eight
observations is a number, not a statistic, so `_series_metrics` returns `None`
below the minimum rather than a figure that reads as one.

**On the risk-free rate.** For a dollar-neutral long/short book, short proceeds
fund the long leg, so the return is already an excess return and no cash
deduction is applied. For a long-only run the Sharpe is a raw-return Sharpe and
is labelled as such. Deducting cash twice, or not at all, is a silent
half-point of Sharpe in a decade of rates like the last one.

---

## 5. Attribution — the only place "alpha" appears

This repository already holds the line. `src/services/backtest_service.py`
declines to call a benchmark difference alpha; `src/research/portfolio.py`
reports a spread and does not name it. This layer extends the same discipline
by actually computing the quantity:

```
r_t − rf_t = a + b₁·MktRF + b₂·SMB + b₃·HML + b₄·RMW + b₅·CMA + b₆·MOM + e_t
```

`a` is alpha. Its t-statistic is Newey-West corrected because a strategy
sampled weekly with a monthly holding period has autocorrelated residuals and
the naive standard error is too small.

**Daily factors are compounded geometrically to the strategy's own rebalance
boundaries** before the regression. Regressing weekly strategy returns on daily
factor returns would compare different quantities; summing rather than
compounding would drift over years.

### Why the answer is usually "no alpha"

Most cross-sectional equity signals are momentum, value or low-volatility in
disguise. A signal loading 0.8 on MOM with an intercept indistinguishable from
zero has not found anything new. `AttributionResult.verdict()` says so
explicitly:

> Intercept is not distinguishable from zero (t = −0.64). The return series is
> explained by its factor exposures — largest loading mom at +0.80. **This is a
> return difference, not alpha.**

Validated against a constructed strategy that *is* 0.9 × momentum: the
regression recovers `mom` beta 0.796–0.9 with `R² = 0.99` and an alpha
t-statistic of −0.64. And against a constructed strategy with a real 40 bp
weekly intercept, which is correctly detected.

### Revised data, and why it is admissible here

The French library is rebuilt when CRSP is revised, so it is catalogued
`PUBLICATION_LAGGED` and **barred from features**. It is admissible for
attribution because attribution is explicitly retrospective: it asks what a
realised return series was exposed to, not what a model should have known.
Revision moves the benchmark's history, not the strategy's returns.

---

## 6. Significance

| Test | Question | Implemented |
|---|---|---|
| Newey-West t on IC | is the mean IC distinguishable from zero given overlap? | yes |
| Blocked bootstrap | interval on IC allowing for dependence | yes |
| Deflated Sharpe | does it beat the best of N zero-skill runs? | yes |
| Minimum Track Record Length | how long until this Sharpe separates from zero? | yes |
| Probability of Backtest Overfitting | does in-sample selection predict out-of-sample rank? | yes |
| White's Reality Check / Hansen SPA | — | **no**, see below |

The bootstrap uses a **moving-block** resample when observations overlap. An
i.i.d. bootstrap on dependent observations produces an interval far too narrow —
understating uncertainty in exactly the direction that flatters a result.

PBO returns `None` for a single configuration rather than a number. Overfitting
is a property of a *selection process*; with one candidate there was no
selection, and inventing a value there would be inventing a result.

White's Reality Check and Hansen's SPA are absent. Both need a stationary
bootstrap with a correctly chosen block length; getting it wrong silently
changes the answer, and a misimplemented significance test is worse than none
because it launders the same bias through a formula that looks rigorous.

---

## 7. Regime robustness

Performance is broken out by regime under two labellers:

* **Rule-based** — volatility percentile crossed with trailing market return,
  plus an explicit stress state at 15% drawdown. Boundaries are fixed constants,
  so they cannot have been chosen to suit a result.
* **K-means, expanding-window** — refitted every 63 sessions on data strictly
  before each labelled block. Fitting once over the full history would let
  2020's centroids define what "high volatility" meant in 2014.

**Both are reported.** Choosing whichever made a model look better would be
regime selection after seeing results, which the brief names explicitly. Where
they disagree, the disagreement is the output, and agreement is measured by
mutual information rather than label matching — cluster identities are arbitrary
integers.

A regime with fewer than 200 observations reports its count and **no metric**. A
rank IC on 40 rows has a standard error wide enough to cover any conclusion, and
printing it invites exactly the story it cannot support.

---

## 8. Running one

```bash
python -m scripts.quant.study --all-labels --out data/research/reports
```

Every model, every label, every fold, every cost assumption, every regime — one
JSON, no filtering. Rendered at `/terminal/models`.
