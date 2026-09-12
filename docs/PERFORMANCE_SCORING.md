# Performance scoring

> What a security actually did, risk-adjusted. **Not** what the model thinks of
> it, and not a forecast.

## Why it is a separate concept

Performance Leaders is deliberately not a view of Top Ranked Ideas. A security
can have compounded beautifully and still carry a HOLD because it is expensive
today. Merging the two would quietly turn the product into a momentum chaser
wearing a model's name, and a reader would have no way to see it happen.

The two lists disagree regularly. That disagreement is information, and it only
survives if they are computed separately and presented separately.

## The composite

| Component | Weight | What it is |
|---|---|---|
| `excess_3m` | 0.30 | 63-session return minus the benchmark's |
| `excess_6m` | 0.30 | 126-session return minus the benchmark's |
| `sharpe` | 0.175 | Annualised, excess-of-zero |
| `sortino` | 0.1125 | Downside-only counterpart |
| `inverse_drawdown` | 0.1125 | Deepest peak-to-trough, inverted |

Each component is converted to a **cross-sectional percentile before**
weighting, so the terms combine like-for-like. A Sharpe of 1.2 and a drawdown
of −18% are not on the same scale and weighting them directly would be
arithmetic on incompatible units.

Windows are in **sessions, not calendar days** — 63, 126, 252.

### Missing components renormalise

Absent components are dropped and the surviving weights renormalised. That says
"scored on what we have" rather than "scored zero on what we do not", which is
the difference between a security with a short history and a security that
performed badly.

### `excess_return_12m` is not in the weights

It was measured at 0 of 43 securities available in the live universe, so it was
removed from the declared weights rather than left in to contribute nothing.
A weight that never applies is a claim about a computation that is not
happening.

## Excess, not raw

`excess_return` returns `None` when either side is unavailable, and **never
substitutes the security's own return for the excess**. +20% in a +25% market
and +20% in a +2% market are different facts, and reporting the first as though
it were the second is the mistake the function exists to prevent.

## The awkward honesty

**Sharpe subtracts no risk-free rate.** It is excess-of-zero and the name still
says Sharpe, because that is what the rest of the codebase already reports. The
omission is documented rather than hidden, and it is constant across the
universe, so the cross-sectional ranking is unaffected by it. A reader
comparing these figures to a published Sharpe should know this.

**Sortino returns `None`, not infinity, when nothing fell.** A security with no
down days has undefined downside deviation, and an infinite Sortino sorts
straight to the top of a leaderboard on the strength of a division by zero.

## Grades

| Score | Grade |
|---|---|
| ≥ 80 | Exceptional |
| ≥ 60 | Strong |
| ≥ 40 | Moderate |
| ≥ 0 | Weak |
| `None` | **`None`** |

An unscored security gets no grade. It does not get "Weak". A grade is a
statement about a measurement, and defaulting to the bottom one describes a
security that was never measured as one that measured badly.

The same rule runs through the ranking: `percentile_rank` returns `None` for a
missing value rather than 50, because an invented median is precisely how an
unmeasured security climbs past a measured one.

## Where it appears

- **Explore → Performance** — a first-class category, ordered by
  `performance_score` descending, showing the grade beside the score. The
  category registry and the interface that renders it are checked against each
  other by test, so a category cannot silently become a dash column.
- **Performance Leaders** — one of five distinct discovery concepts, separate
  from Top Ranked Ideas, High Conviction, Trending Now and Explore.

Both state that this is history, not a forecast, and not the model's view.
