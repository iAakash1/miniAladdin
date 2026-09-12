# Claim validation

## Why it is deterministic

The obvious design is a second language model checking the first. That is not
validation: two models can be wrong in the same direction — they were trained
on overlapping text — and their agreement is evidence about that overlap
rather than about the security.

Truth here comes from evidence and arithmetic. The optional critic is a
separate, narrative-quality layer and cannot overrule this one.

## The rules

| # | Rule | The mistake it catches |
|---|---|---|
| 1 | every factual claim cites evidence | a sentence with no source |
| 2 | the evidence it cites exists | a dangling handle |
| 3 | numbers match their evidence | prose drifting from data |
| 4 | units match | a fraction read as a percentage |
| 5 | periods are comparable | TTM against fiscal year |
| 6 | currencies match | two currencies in one total |
| 7 | evidence is fresh enough | last year's price, stated flat |
| 8 | shared upstreams are not independent | one wire story counted twice |
| 9 | missing is not zero | an absence scored as a value |
| 10 | narrative agrees with the signal | text arguing the opposite |
| 11 | risk wording matches the score | "low risk" over an 88 |
| 12 | no injected instructions survive | an article's directive repeated |

## States

`VERIFIED` · `PARTIAL` · `CONFLICTED` · `STALE` · `UNSUPPORTED`

Defined once, in `src/agents/schemas.py`. A status meaning one thing in the
validator and another in the interface is worse than having no status.

## Freshness is capability-specific

| Capability | Window |
|---|---|
| `price_series` | 7 days |
| `news` | 14 days |
| `macro` | 45 days |
| `fundamentals` | 400 days |
| default | 90 days |

A 40-day-old balance sheet is current. A 40-day-old price is not.

## Numeric tolerance

2% relative. Not zero: claims round for display, and 12.34 standing for
12.3416 is presentation rather than drift.

## Shared upstreams

`yfinance`, `yahoo_rss` and `yahoo` are Yahoo. `gnews` and `newsapi` share an
upstream. `independent_sources()` counts distinct origins, not distinct vendor
names, because counting resyndication as corroboration inflates apparent
confirmation exactly where a reader would rely on it.

## A failed narrative is withheld

Not annotated and shown anyway. If the generated explanation contradicts the
signal, misstates the risk band, or repeats instruction-like text from
evidence, the deterministic fallback is served instead.
