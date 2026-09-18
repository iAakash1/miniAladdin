# Next quantitative research plan

> Preparation for the next dedicated research sprint. Nothing in this document
> was executed. No experiment was run, no holdout was touched, no artifact was
> modified to produce it.

## Where the research actually stands

EXP-006's specification "contains weak but statistically detectable
cross-sectional ranking information, but does not clear the declared
cost-adjusted promotion threshold." That sentence is worth preserving exactly
as written rather than compressed to "low accuracy" — the two claims are
different, and the difference is the whole reason `PROMOTION BLOCKED` is a
research finding and not a bug report. A specification with a measurable,
non-zero mean IC and a t-stat worth taking seriously, whose costed portfolio
Sharpe is still negative after realistic transaction costs, is telling a
specific, useful story: *some* cross-sectional information exists, and it is
not currently worth enough to trade. Those are two different follow-up
questions — "is there really nothing here" versus "how do we capture more of
what is here, or spend less to act on it" — and this plan is written for the
second question, because the evidence already answered the first one weakly
in the affirmative.

Production remains at 0 models. The holdout remains unspent. This plan does
not propose changing either fact; it proposes what to test before either
fact might change.

## A. Learning-to-rank objective

The current target is cross-sectional rank via point regression on forward
returns. A point-regression loss (MSE, quantile) optimises for getting the
*magnitude* right; what the product actually consumes is the *ordering* —
`rank_cross_section` and the composite screen only ever use relative
position, never the predicted return's absolute value. That mismatch between
what is optimised and what is used is itself a hypothesis worth testing
directly, not assuming away.

Candidates for the next sprint, in order of how well-trodden they are for
this exact problem shape (cross-sectional stock ranking, tabular features,
weekly rebalance):

- **LightGBM `LambdaRank`** — the most standard starting point; ranks within
  a group (here, a date's cross-section) directly, and the group structure
  the panel already has (`date`, `symbol`) maps onto it without restructuring
  the data.
- **XGBoost `rank:pairwise` / `rank:ndcg`** — a second implementation of the
  same idea, useful as a cross-check that a result is the objective and not
  one library's particular optimiser.
- **Explicit pairwise methods** (RankNet-style, or a simple pairwise logistic
  loss over `(better, worse)` pairs within a date) — more work to implement
  correctly, and only worth it if the off-the-shelf ranking objectives above
  show a real gap over the current point-regression baseline.

**Not proposed:** adding a dependency to do this. LightGBM and XGBoost both
already ship ranking objectives in the versions this project already
depends on (`requirements-quant.txt`), so this is a training-configuration
change, not a new library.

## B. Sector / size neutralisation

The open question this section exists to answer: is EXP-006's detected
signal coming from *security-specific* information, or is it partly (or
mostly) a sector bet or a size effect wearing a stock-picking model's name?
That is not a rhetorical concern — a model that has quietly learned "small
caps outperformed in this sample" will look like skill in-sample and behave
like an uncompensated factor bet out of sample.

Three targets to compare against the current raw forward rank, holding
everything else in the pipeline fixed:

1. **Raw forward rank** (current) — the baseline this compares against.
2. **Sector-neutral rank** — rank within GICS sector (or the coarser sector
   classification the panel already carries) rather than across the whole
   universe.
3. **Sector- and size-neutral rank** — the above, with a market-cap bucket
   control added.

If IC drops sharply moving from (1) to (2)/(3), the honest conclusion is that
a meaningful share of the detected edge was a sector or size tilt, not
security selection — and that is exactly the kind of finding this plan exists
to surface before it is mistaken for stock-picking skill.

## C. Estimate revision features

Not currently in the panel. Candidate sources for the next data-sourcing
pass: analyst EPS revision breadth/magnitude, revenue estimate revisions,
price-target changes, and the trajectory of earnings surprises across recent
quarters (is the company beating by a widening or narrowing margin). These
are a different information class from the current panel's price/volume/
macro/fundamental-ratio features — they proxy for what informed analysts are
updating their models to reflect, which price momentum captures with a lag
and fundamentals capture not at all.

## D. Event data

Not currently in the panel beyond the existing SEC-filing and earnings-date
machinery. Candidates: earnings and guidance events (already partially
present via `pead_inputs`/days-since-earnings — worth auditing for
completeness before adding new sources), 8-K event classification, corporate
actions, insider transaction filings (Form 4), and management-change events.
Each is a discrete, dated signal rather than a continuous series, and would
need its own point-in-time discipline — an event feature computed with
knowledge of what happened *after* the event date is exactly the leakage
class `docs/quant-leakage-prevention.md` exists to catch.

## E. Options / implied information

Not currently available — this product's options coverage (`Options.tsx`,
one provider) is a display surface, not a research data source, and has
never been wired into the panel. Candidates for a future data-sourcing
evaluation: implied volatility level and term structure, skew, put/call
ratios, and options volume relative to underlying volume. All of these are
forward-looking in a way price history is not, which is exactly why they are
worth testing rather than assuming price/volume already captures the same
information.

## F. Ownership / flow

Not currently in the panel. Candidates: institutional holdings changes
(13F-derived, quarterly and therefore lower-frequency than the rest of the
panel — a real constraint to design around, not ignore), insider buying/
selling (Form 4, same source as section D's event angle but used here as a
continuous flow measure rather than a discrete event), fund flow data, and
short interest. Short interest in particular pairs naturally with the
existing risk/quality families as a crowding signal.

## G. Alternative fundamental quality

The panel already has gross-profit-over-assets, net share issuance and asset
growth (`quality_inputs`). Candidates to extend the quality family: accruals
(the classic Sloan measure — high accruals predicting lower forward returns
is one of the more replicated findings in this literature), a broader
profitability decomposition beyond gross margin, an investment factor
(capital expenditure growth), and cash-flow-quality measures (the gap between
reported earnings and operating cash flow). These extend an existing,
already-populated family rather than opening a new one.

## H. Ensemble disagreement as uncertainty

**Explicitly not a new recommendation weight.** The proposal is to compute
directional/rank agreement across model families that already exist as
candidates in the registry (linear, tree-based, gradient-boosted variants)
at the *research* layer only, and expose it as a diagnostic — "how much do
independent specifications agree about this point" — never as an input that
changes a score or a rank. If a future empirical study finds that
disagreement predicts realised error well enough to justify using it as a
confidence adjustment, that would be its own proposal, evaluated on its own
evidence, not assumed here. `MODEL_AGREEMENT` plumbing (contract only, no
fabricated values) is a reasonable first step for the implementation side of
this; it was not built in this pass — see the product sprint's own
"Remaining limitations."

## I. Regime-conditional models

Test whether a model conditioned on the macro regime the panel already
classifies (`regimes` — the same classification `momentum_gate` reads) beats
one global model, rather than assuming a single specification should behave
identically in every regime. The honest failure mode to watch for: a
regime-conditional model can look better in-sample purely by having more
parameters fit to fewer effective observations per regime, so this needs the
same walk-forward and multiple-testing discipline as every other candidate
in the ledger — not a shortcut around it.

## J. Transaction-cost-aware learning

The current pipeline measures cost sensitivity *after* training (backtest
attribution, turnover reporting). The open question: does training against an
objective that penalises turnover directly (a soft turnover penalty in the
loss, or a target formulated on a longer holding period to begin with)
produce a specification whose *net* Sharpe is more robust than a
point-regression model whose turnover is only discovered after the fact.
This is the one candidate here that changes what is optimised for cost
sensitivity, rather than measuring cost sensitivity of something optimised
without it in mind.

## What this plan is not

Not a commitment to run all ten of these. Not a claim that any of them will
work — EXP-004 and EXP-005 already found that several plausible-sounding
data additions made the model *worse*, which is exactly the kind of result a
plan like this should expect some fraction of the time, not treat as a
process failure. The next sprint's job is to pick the highest-value one or
two of these, run them with the same walk-forward, multiple-testing-corrected
discipline as every experiment in the ledger, and update `RESEARCH_LEDGER.md`
with the result whichever way it comes out.

## What this pass deliberately did not do

Per this sprint's own constraints: no new predictive experiment was run, the
sealed holdout was not read, EXP-007 was not rerun or modified, and no model
was promoted. This document is preparation, not research.
