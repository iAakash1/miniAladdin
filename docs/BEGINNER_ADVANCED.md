# Beginner, Intermediate and Advanced

Three presentations of one analysis. Not three products, and not three models.

## The invariant

The same security under the same evidence produces the same verdict,
confidence and risk in every mode. This is structural rather than
conventional: `experience_mode` is a user preference stored beside `theme`, it
is absent from `score_ticker`'s signature and from every scoring module, and
`tests/test_decision_invariance.py` asserts that absence.

## What differs

| | Beginner | Intermediate | Advanced |
|---|---|---|---|
| Verdict, confidence, risk | identical | identical | identical |
| Factor attribution | top 3 for and against, in plain language | scorecard and strongest contributions | full decomposition with contributions |
| Provenance | Evidence Health | Evidence Health plus agent checks | complete per-field reconciliation |
| Statements, ownership, filings | not shown | selected valuation/analyst context | shown |
| Narrative | short, plain, no jargon | analytical summary | full institutional report |
| Explore | same rankings, 12 rows | same rankings, 24 rows | same rankings, filters and 40 rows |

## Language rules

Three phrasings separate an educational research tool from an unlicensed
recommendation, and each is lost one careless label at a time.

| Say | Never |
|---|---|
| OmniSignal model signal: BUY | You should buy |
| Analysis confidence 78/100 | 78% chance the stock rises |
| Risk level: MEDIUM | 62% chance of losing money |
| Data completeness 91% | 91% accurate |
| Top Ranked Ideas | Guaranteed winners |
| Trending | Worth buying |

`dashboard/tests/beginner-language.test.ts` asserts these against the actual
strings, including that unmeasured risk is never presented as low risk.

## Reasons come from the engine

The "why" lists are the engine's own factor contributions, named through the
existing factor glossary. A reason a reader cannot trace back to a factor row
is a reason we invented, so when nothing scored, nothing is shown rather than
the space being filled. An undocumented factor is still displayed under its
raw name — hiding it would silently drop a reason that moved the score.

## Onboarding

Keyed off `experience_mode_chosen`, not the mode. An unset preference resolves to `advanced`
when unset, but only one means "never asked"; keying off the mode would
re-prompt every advanced user on every visit. Existing accounts default to
`advanced` so nobody is moved out of the terminal they already use.

The question asked is **"How much detail would you like?"** — about the
presentation, never about the person. Nothing labels a reader a beginner, and
the choice is reversible from every mode.

## What each mode adds

No mode has its own model, its own ranking or its own verdict. The
difference is how much of one analysis is shown.

**Simple** gets a six-item navigation rather than the twenty-five-destination
rail, the discovery concepts as cards, Ask OmniSignal, and the What-If Lab.

**Intermediate** adds the factor scorecard, valuation and analyst context,
embedded real agent checks, comparisons and portfolio intelligence without
opening the experiment archive by default.

**Advanced** gets the terminal: the full rail with foldable groups, the Agent
Observatory, the evidence audit with a claim-level drawer, High Conviction with
its near misses, and the rank decomposition in Compare.

The What-If Lab appears in every company analysis, because "what would have to change for this to
read differently" is not an expert's question. It calls the real scoring engine
with one perturbed input rather than estimating what the engine would say — see
[WHAT_IF.md](WHAT_IF.md) — and is labelled SIMULATION wherever it appears.
