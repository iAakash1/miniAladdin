# Explore — cross-sectional ranking

## What it is not

`screen_service` answers "which securities relate to this phrase" by searching
the web and extracting tickers; ordering there reflects how a search engine
ranked pages. Explore answers "of the securities we can score, which rank
highest on a stated quantitative dimension". They are kept apart so that
page-rank cannot leak into something a reader will read as a financial
ordering.

## The universe

`config/universe_us_v1.json` — 77 liquid US-listed common equities across 11
GICS sectors, versioned as `us-v1`.

Membership says only that this stack can obtain the inputs its factor model
needs. It is not a recommendation, and absence is not a judgement. *Which*
securities are considered is configuration; *how they rank* is model output.
A ranking is only reproducible against the universe it ran over, so
`universe_version` travels with every response.

## Eligibility

A security must clear every gate. Failures are reported together, not one at a
time, because a security can fail several and reporting only the first makes
the fix look smaller.

| Gate | Threshold |
|---|---|
| asset type | `common_equity` |
| history | ≥ 60 bars |
| price | present and > 0 |
| price age | ≤ 7 days |
| scorecard | present |
| data completeness | ≥ 0.55 |
| analysis confidence | ≥ 25 |
| validation state | not `CONFLICTED` / `UNSUPPORTED` |

**Why every gate excludes on absence.** A thinly covered security has few
factors; few factors mean little disagreement; little disagreement means high
confidence and low measured risk. Left alone, the name we understand least
sorts first.

**The confidence floor is calibrated, not guessed.** `confidence` starts at 100
and is reduced multiplicatively by eight factors before being clipped to
[5, 95], so healthy readings are nowhere near 100. Measured over twelve
well-covered large caps the band was 33–48 (median 44) at full completeness.
An earlier draft used 35 and excluded a mega-cap sitting at 33 — a gate firing
on the ordinary bottom of the healthy band rejects noise, not uncertainty.

## Overall rank

Every component is normalised to 0–100 before weighting, so the result is
0–100.

```
overall_rank = 0.55 × signal_strength_percentile
             + 0.20 × confidence
             + 0.15 × (100 − risk_score)
             + 0.10 × (data_completeness × 100)
```

Ranges were measured, not assumed. `raw_score` is a weighted sum of
tanh-squashed family scores over weights that renormalise to 1, so it is
bounded **[-1, 1]** — not 0–100. `data_completeness` is a **0–1 fraction**.
`confidence` and `risk_score` are 0–100.

Signal dominates because it is the model's actual output; the other three
qualify how much it can be relied on. They are not re-derived factor families:
the scorecard has already combined momentum, value, quality, news and
reversal, and adding them again here would count the same evidence twice.

A missing component yields no rank at all rather than a default, because a
default would let absence act as evidence.

## Trending — not a recommendation

```
trend_score = 0.35 × momentum_21d_percentile
            + 0.25 × momentum_5d_percentile
            + 0.20 × relative_volume_percentile
            + 0.10 × news_activity_percentile
            + 0.10 × high_52w_proximity_percentile
```

Missing components are dropped and the surviving weights renormalised, rather
than filled with a neutral value: renormalising says "scored on what we have",
filling says "we measured this and it was average".

The score is unsigned, so `trend_direction` is reported beside it — "trending"
alone cannot tell a rally from a collapse. **The model signal is rendered on
every row of every tab, trending included.** A security falling hard on heavy
coverage leads that list and may carry a Sell signal while it does.

## Categories

| Category | Orders by |
|---|---|
| Overall | `overall_rank` |
| Trending | `trend_score` |
| Momentum | momentum sleeve percentile |
| Quality | quality sleeve percentile |
| Value | fundamental sleeve percentile |
| Profitability | operating margin, **sector-relative** percentile |
| Performance | `performance_score` — risk-adjusted history, **not** the model's view |
| Low Risk | `risk_score` ascending |
| News Buzz | headline volume percentile |
| Analyst Upside | mean target vs last close |

Profitability is sector-relative because a software margin and a grocery
margin are not the same measurement; ranking them against each other mostly
ranks industries.

**Unknown is not good.** A row missing a category's own measure is dropped
rather than sorted last — appearing last in "Low Risk" still reads as a risk
statement, and we do not have one to make.

**Growth is deliberately absent.** Reconciling TTM against fiscal-year revenue
across vendors is not solved here, and a growth tab built on unreconciled
periods would rank accounting conventions rather than companies.

**Performance is history, not a forecast**, and it regularly disagrees with
Overall — a security can have compounded beautifully and still carry a HOLD
because it is expensive today. The composite, the windows and the reason Sharpe
here subtracts no risk-free rate are in
[PERFORMANCE_SCORING.md](PERFORMANCE_SCORING.md).

**The registry and the interface are checked against each other.** A category
the frontend has no case for renders a dash in its own column while the tab
appears, selects and sorts — nothing errors and no test fails, because the
backend is right and the frontend is merely silent. Both switches and the
`CategoryKey` union are asserted against `CATEGORIES` by name.

## High conviction — a threshold, not a ranking

A separate concept from the orderings above, and not a view of one. Overall
always has a first row; high conviction has entries only when every condition
agrees at once, and **most days nothing does**. A tier that always had members
would be a ranking wearing a threshold's name.

Each bound in `services/conviction.py` records the observation that set it —
`min_confidence = 42` sits just below a median of 44 against a live maximum of
51, because on this engine's scale there is no such thing as a high confidence
bar. The sketched "confidence >= 75" would have qualified nobody.

Missing values **block** rather than pass. A security whose risk could not be
measured has not demonstrated acceptable risk, and a conviction tier treating
silence as agreement would hand its strongest label to the names it understands
least.

When the tier is empty the interface shows the near misses and what each is
missing, computed beside the tier by the same assessment, so the explanation
cannot disagree with the decision. Securities that are ineligible, or that were
never assessed, are excluded — they did not fail the policy.

## Why one security ranks above another

`overall_rank` is a weighted sum, so the gap between two securities decomposes
**exactly** into four contributions that add back up to it. `/api/compare/rank`
returns that decomposition; no model is consulted.

Asked why one name ranks above another, a model produces fluent reasons —
market position, product cycle — that the ranking has never looked at, and the
reader comes away believing it considered them. Ranking above is also not a
recommendation: it is a position on one composite score, and both securities
can carry the same signal.

## Caching

Snapshots are cached for 10 minutes; these are daily-bar rankings. On a
refresh failure the previous snapshot is served with `stale: true` and the
reason attached, within a one-hour grace window. "No security qualified" and
"we could not reach the vendors" look identical once the rows are gone, and
only one of them is a finding.

No language model runs in this pipeline. Sorting numbers does not need one,
and one narrative call per security would be ~77 model requests per refresh to
produce an ordering arithmetic already determined.
