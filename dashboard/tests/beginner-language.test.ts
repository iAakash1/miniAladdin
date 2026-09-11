/* The Beginner surface simplifies the presentation, never the claim.

   Three phrasings separate an educational research tool from an unlicensed
   recommendation, and each is lost one careless label at a time:

     - a signal belongs to the model, not the reader
     - confidence describes the evidence, not the outcome
     - risk describes exposure, not a probability of loss

   The fourth property is decision invariance: a Beginner and an Advanced
   reader look at the same scorecard. Nothing in this layer recomputes,
   rounds, clamps or re-derives a number on its way to the screen, so the
   reasons shown here are the engine's own factor contributions rather than
   anything authored to sound encouraging. */
import { strict as assert } from 'node:assert'
import test from 'node:test'

import {
  DISCLAIMER, explainCompleteness, explainConfidence, explainRisk,
  reasons, signalSentence, whatCouldChange,
} from '../src/lib/beginner'
import type { QuantFactor } from '../src/lib/types'

function factor(name: string, contribution: number, family = 'momentum'): QuantFactor {
  return { name, family, value: 1, z: 1, score: 1, contribution }
}

/* ── the model owns the signal ─────────────────────────────────────────── */

test('a signal is attributed to the model, never issued to the reader', () => {
  const sentence = signalSentence('Buy')
  assert.match(sentence, /OmniSignal model signal/i)
  for (const forbidden of [/you should/i, /we recommend/i, /guaranteed/i, /will rise/i]) {
    assert.ok(!forbidden.test(sentence), `"${sentence}" reads as advice`)
  }
})

test('an absent verdict is stated as absent rather than softened to hold', () => {
  const sentence = signalSentence(null)
  assert.match(sentence, /could not produce a signal/i)
  assert.ok(!/hold/i.test(sentence))
})

test('the disclaimer names this as educational and not personalised', () => {
  assert.match(DISCLAIMER, /educational/i)
  assert.match(DISCLAIMER, /not personalised investment advice/i)
})

/* ── confidence is about evidence ──────────────────────────────────────── */

for (const value of [95, 78, 50, 30, 5]) {
  test(`confidence ${value} is never described as a probability of profit`, () => {
    const text = explainConfidence(value)
    for (const forbidden of [/chance/i, /probability/i, /likely to (rise|gain)/i, /% chance/]) {
      assert.ok(!forbidden.test(text), `"${text}" reads as a probability`)
    }
    assert.match(text, /evidence/i)
  })
}

test('an unavailable confidence says so rather than reporting zero', () => {
  assert.match(explainConfidence(null), /could not be computed/i)
})

/* ── risk is exposure, not a loss probability ──────────────────────────── */

for (const [level, score] of [['LOW', 12], ['MEDIUM', 50], ['HIGH', 88]] as const) {
  test(`${level} risk is described as exposure rather than a chance of loss`, () => {
    const text = explainRisk(level, score)
    for (const forbidden of [/chance of los/i, /probability of los/i, /% chance/]) {
      assert.ok(!forbidden.test(text), `"${text}" reads as a loss probability`)
    }
    assert.ok(text.includes(String(score)))
  })
}

test('unmeasured risk is not presented as low risk', () => {
  const text = explainRisk(null, null)
  assert.match(text, /could not be measured/i)
  assert.match(text, /not the same as it being low/i)
})

/* ── coverage is not accuracy ──────────────────────────────────────────── */

test('data completeness is described as coverage, never accuracy', () => {
  const text = explainCompleteness(0.91)
  assert.ok(text.includes('91%'))
  assert.match(text, /coverage, not accuracy/i)
})

test('an unknown completeness is not rendered as zero percent', () => {
  const text = explainCompleteness(null)
  assert.match(text, /unknown/i)
  assert.ok(!text.includes('0%'))
})

/* ── reasons come from the engine ──────────────────────────────────────── */

test('reasons are the strongest contributions, in order', () => {
  const { positive, cautious } = reasons([
    factor('r12_1', 0.05),
    factor('vol_confirm', 0.02),
    factor('earnings_yield', -0.04, 'fundamental'),
    factor('reversal', -0.01, 'reversal'),
  ])
  assert.deepEqual(positive.map((r) => r.key), ['r12_1', 'vol_confirm'])
  assert.deepEqual(cautious.map((r) => r.key), ['earnings_yield', 'reversal'])
})

test('a factor the engine did not score contributes no reason', () => {
  const unscored: QuantFactor = {
    name: 'r63', family: 'momentum', value: null, z: null, score: null, contribution: 0.9,
  }
  const { positive } = reasons([unscored])
  assert.equal(positive.length, 0)
})

test('no factors yields no reasons rather than invented ones', () => {
  const { positive, cautious } = reasons([])
  assert.deepEqual(positive, [])
  assert.deepEqual(cautious, [])
  assert.deepEqual(reasons(undefined).positive, [])
})

test('a documented factor is named in plain language', () => {
  const { positive } = reasons([factor('r12_1', 0.1)])
  assert.equal(positive[0].label, '12-1 Month Momentum')
  assert.ok(positive[0].detail.length > 0)
})

test('an undocumented factor is still shown rather than dropped', () => {
  /* Hiding it would silently delete a reason that moved the score. */
  const { positive } = reasons([factor('some_new_factor', 0.1)])
  assert.equal(positive.length, 1)
  assert.equal(positive[0].label, 'some new factor')
})

/* ── what could change ─────────────────────────────────────────────────── */

test('what-could-change is built from the factors carrying the verdict', () => {
  const lines = whatCouldChange([factor('r12_1', 0.08), factor('earnings_yield', -0.03, 'fundamental')], 'Buy')
  assert.ok(lines.length > 0)
  assert.ok(lines.some((l) => l.includes('12-1 Month Momentum')))
})

test('what-could-change never predicts a dated event', () => {
  const lines = whatCouldChange([factor('r12_1', 0.08)], 'Buy')
  for (const line of lines) {
    for (const forbidden of [/next (week|month|quarter)/i, /will /i, /expect(ed)? to/i, /\b20\d\d\b/]) {
      assert.ok(!forbidden.test(line), `"${line}" makes a claim about the future`)
    }
  }
})

test('a bearish verdict inverts the framing rather than reusing the bullish one', () => {
  const bullish = whatCouldChange([factor('r12_1', 0.08)], 'Buy')
  const bearish = whatCouldChange([factor('r12_1', 0.08)], 'Sell')
  assert.notDeepEqual(bullish, bearish)
})
