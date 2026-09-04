/* The cross-provider audit, and the correction it makes to the payload.

   The research payload reports Apple's last price as a conflict: four
   providers, `conflict: true`, dispersion 2.25%. Read as it stands that says
   four vendors disagree about Apple's price by seven dollars.

   They do not. Three report a *last sale* — 321.03, 320.98, 321.03, a spread
   of 0.02% — and the fourth reports the *previous session's close*, from the
   day before. The 2.25% is the distance between a last sale and a prior
   close, differenced as though they were the same measurement.

   These fix the numbers from that live payload so the correction cannot
   silently regress into an average of incomparable things. */
import { strict as assert } from 'node:assert'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { assessReadings, describeGroups, spreadPct, UNSTATED } from '../src/components/terminal/security/DataQuality'

const SOURCE = readFileSync(
  new URL('../src/components/terminal/security/DataQuality.tsx', import.meta.url), 'utf8',
)

/* Comments stripped before any detector runs.

   The panel's own doc comment explains at length that it computes no letter
   grade and no weighted index — and the detector below looks for exactly
   those words, so the file failed for saying it does not do the thing. The
   answer is to scan what executes rather than to weaken the pattern until the
   prose slips past, because a pattern loosened to accommodate a comment stops
   catching the real offender too. */
const CODE = SOURCE
  .replace(/\/\*[\s\S]*?\*\//g, ' ')
  .split('\n')
  .filter((l) => !l.trim().startsWith('//'))
  .join('\n')

/** Apple, as the providers actually answered on 4 September 2026. */
const AAPL = [
  { provider: 'finnhub', price: 321.03, basis: 'last sale', as_of: '2026-09-04T18:31:41+00:00' },
  { provider: 'polygon', price: 328.21, basis: 'previous session close', as_of: '2026-09-03T20:00:00+00:00' },
  { provider: 'twelvedata', price: 320.98, basis: 'last sale', as_of: '2026-09-04' },
  { provider: 'yfinance', price: 321.0299987792969, basis: null, as_of: null },
]

test('readings are grouped by what they measure, not pooled', () => {
  const a = assessReadings(AAPL)
  assert.equal(a.groups.size, 3, 'three distinct measurements were collapsed')
  assert.equal(a.groups.get('last sale')?.length, 2)
  assert.equal(a.groups.get('previous session close')?.length, 1)
  assert.equal(a.groups.get(UNSTATED)?.length, 1)
})

test('a vendor that states no basis is never folded into one that does', () => {
  // yfinance returns 321.0299… which is within a rounding error of the two
  // last-sale readings. Grouping it with them on that resemblance is exactly
  // the inference this refuses to make: what it is a price *of* was not said.
  const a = assessReadings(AAPL)
  assert.ok(!a.groups.get('last sale')?.some((r) => r.provider === 'yfinance'),
    'an unlabelled reading was assumed to be a last sale because its number looked like one')
  assert.deepEqual(a.stated, ['last sale', 'previous session close'])
})

test('the extreme pair is judged incomparable, and by the shared engine', () => {
  const a = assessReadings(AAPL)
  assert.ok(a.extremes, 'no verdict was reached on the two readings furthest apart')
  assert.equal(a.extremes.ok, false, 'a last sale was ruled comparable with a previous close')
  assert.match(a.extremes.reason ?? '', /last sale/)
  assert.match(a.extremes.reason ?? '', /previous session close/)
})

test('real disagreement is measured inside one basis', () => {
  const a = assessReadings(AAPL)
  assert.equal(a.worstWithin?.basis, 'last sale')
  assert.equal(a.worstWithin?.n, 2)
  // 321.03 against 320.98 — two hundredths of a percent, not 2.25%.
  assert.ok(a.worstWithin!.spread < 0.05,
    `within-basis spread came out ${a.worstWithin!.spread}, which is the cross-basis number`)
})

test('the cross-basis spread is not reported as vendor disagreement', () => {
  // The payload's own 2.25%. It must never become this panel's headline
  // agreement figure, which is what pooling all four would produce.
  const pooled = spreadPct(AAPL.map((r) => r.price))!
  assert.ok(pooled > 2.2 && pooled < 2.3, `pooled spread was ${pooled}`)
  const a = assessReadings(AAPL)
  assert.ok(a.worstWithin!.spread < pooled / 10,
    'the within-basis spread is not meaningfully smaller than the pooled one')
})

test('providers that do agree are reported as agreeing', () => {
  // The correction must not simply refuse every comparison. Two vendors on
  // one basis are comparable and the panel has to say so.
  const a = assessReadings([
    { provider: 'finnhub', price: 321.03, basis: 'last sale' },
    { provider: 'twelvedata', price: 320.98, basis: 'last sale' },
  ])
  assert.equal(a.groups.size, 1)
  assert.equal(a.extremes?.ok, true, 'two readings on one basis were refused')
  assert.equal(a.extremes?.caveat, undefined, 'a caveat was raised where the bases match')
})

test('one stated basis against one unstated raises a caveat, not silence', () => {
  const a = assessReadings([
    { provider: 'finnhub', price: 321.03, basis: 'last sale' },
    { provider: 'yfinance', price: 330.0, basis: null },
  ])
  assert.equal(a.extremes?.ok, true)
  assert.match(a.extremes?.caveat ?? '', /does not say/,
    'an unlabelled reading was compared against a labelled one in silence')
})

test('a reading with no usable price is dropped, not zeroed', () => {
  const a = assessReadings([
    { provider: 'finnhub', price: 321.03, basis: 'last sale' },
    { provider: 'broken', price: null, basis: 'last sale' },
    { provider: 'nan', price: Number.NaN, basis: 'last sale' },
  ])
  assert.equal(a.sorted.length, 1, 'a null or NaN price entered the comparison')
  assert.equal(a.worstWithin, null, 'a spread was computed from one reading')
})

test('a single reading yields no verdict rather than a false agreement', () => {
  const a = assessReadings([{ provider: 'finnhub', price: 321.03, basis: 'last sale' }])
  assert.equal(a.extremes, null)
  assert.equal(a.worstWithin, null)
})

test('spread is undefined for fewer than two prices and for a zero floor', () => {
  assert.equal(spreadPct([]), null)
  assert.equal(spreadPct([10]), null)
  assert.equal(spreadPct([0, 10]), null, 'a zero low produced a division by zero')
  assert.equal(spreadPct([100, 110]), 10)
})


test('the table is ordered by measurement, not by price alone', () => {
  // Sorting by price alone put polygon's previous close between two last
  // sales, so the row order contradicted the sentence above the table.
  const a = assessReadings(AAPL)
  const bases = a.ordered.map((r) => r.basis ?? UNSTATED)
  assert.deepEqual(bases, ['last sale', 'last sale', 'previous session close', UNSTATED])
  // Cheapest first inside a group.
  assert.deepEqual(
    a.ordered.slice(0, 2).map((r) => r.provider),
    ['twelvedata', 'finnhub'],
  )
  // Every reading still present — grouping reorders, it does not drop.
  assert.equal(a.ordered.length, a.sorted.length)
})

test('the list of measurements reads as one English sentence', () => {
  assert.equal(
    describeGroups(assessReadings(AAPL)),
    '2 report the last sale, 1 reports the previous session close, '
    + 'and 1 does not say what the figure is of',
  )
})

test('the sentence agrees in number for one provider and for two', () => {
  const one = describeGroups(assessReadings([
    { provider: 'finnhub', price: 1, basis: 'last sale' },
  ]))
  assert.equal(one, '1 reports the last sale')

  const two = describeGroups(assessReadings([
    { provider: 'finnhub', price: 1, basis: 'last sale' },
    { provider: 'polygon', price: 2, basis: 'previous session close' },
  ]))
  assert.equal(two, '1 reports the last sale and 1 reports the previous session close')
  assert.doesNotMatch(two, /,/, 'a two-item list was punctuated as a three-item one')
})

/* A composite figure is a *binding*, not a word.

   The first version of this looked for the bare words "score" and "grade"
   anywhere in the file, and failed on the panel's own sentence telling the
   reader there is no quality grade. Matching prose is not the same as
   matching the defect: these look for something named like a score being
   declared or assigned, which is what actually building one looks like.
   Proven below against a real offender rather than assumed. */
const COMPOSITE: RegExp[] = [
  /\b(?:const|let|var|function)\s+\w*(?:score|grade|rating|health)\w*/i,
  /\b\w*(?:score|grade|rating)\w*\s*[:=][^=]/i,
  /weighted/i,
]

test('the composite-figure detector catches a real one', () => {
  // Without this, narrowing the patterns above could have quietly disarmed
  // them and every run would still be green.
  const offender = `
    const agreement = 100
    const coverage = 71
    const qualityScore = agreement * 0.6 + coverage * 0.4
  `
  assert.ok(
    COMPOSITE.some((r) => r.test(offender)),
    'the detector no longer catches a weighted quality index',
  )
  const asField = 'return { data_quality_score: 87 }'
  assert.ok(
    COMPOSITE.some((r) => r.test(asField)),
    'the detector no longer catches a score emitted as a field',
  )
})

/* ── the panel's own restraint ─────────────────────────────────────────── */

test('no quality score is computed', () => {
  /* The brief asked for a data-quality surface and explicitly forbade a fake
     quality score. Folding coverage, agreement and freshness into one index
     is the obvious thing to build and it destroys the three signals it is
     made of — each has a different cause and a different remedy. */
  for (const shape of COMPOSITE) {
    assert.doesNotMatch(CODE, shape, `a composite quality figure appeared: ${shape}`)
  }
})

test('the consensus figure is displayed but never used in arithmetic', () => {
  // The payload supplies a single consensus price and does not say how it was
  // chosen. Showing it is honest; computing with it would launder an
  // unlabelled aggregation of readings taken on different bases.
  const uses = SOURCE.match(/consensus\.consensus/g) ?? []
  assert.ok(uses.length > 0, 'the consensus figure is not shown at all')
  assert.doesNotMatch(
    SOURCE,
    /consensus\.consensus\s*[-+*/]/,
    'the consensus figure is an operand in a calculation',
  )
})

test('the unchecked part of the series is derived, never assumed', () => {
  // `shared` counts sessions two or more providers returned; the rest of the
  // union was seen by exactly one and cross-checked by nothing. Agreement
  // percentages that omit this describe a subset while looking total.
  assert.match(SOURCE, /union\s*-\s*shared/, 'the uncross-checked sessions are not computed')
  assert.match(SOURCE, /never checked against a second source/)
})

test('comparability is delegated, not reimplemented here', () => {
  assert.match(SOURCE, /from '@\/lib\/semantics'/)
  assert.match(SOURCE, /comparable\(\s*\n?\s*\{ kind: 'currency', basis:/,
    'the basis comparison is decided somewhere other than the semantic layer')
})
