/* The semantic contract.

   Every defect this product has shipped and caught was semantic rather than
   typographic: a count printed as "+0", a percentage printed as a fraction, a
   rank correlation subtracted from a return correlation. Each was formatted
   flawlessly. These assert the layer that knows what a number is. */
import { strict as assert } from 'node:assert'
import test from 'node:test'

import { SPECS, format, type Kind } from '../src/lib/quantity'
import { SEMANTICS, comparable, delta, toneFor } from '../src/lib/semantics'
import {
  formatCount, formatPercentage, formatProbability, formatShare, metric,
} from '../src/lib/metric'

test('every formattable kind declares its meaning', () => {
  // A kind with a precision but no semantics can be printed and not reasoned
  // about, which is exactly the state the Evidence registry was in.
  const undeclared = (Object.keys(SPECS) as Kind[]).filter((k) => !SEMANTICS[k])
  assert.deepEqual(undeclared, [], `kinds with no declared semantics: ${undeclared.join(', ')}`)
})

/* ── comparability ──────────────────────────────────────────────────────── */

test('like compares with like', () => {
  assert.equal(comparable({ kind: 'ic' }, { kind: 'ic' }).ok, true)
  assert.equal(comparable({ kind: 'sharpe' }, { kind: 'sharpe' }).ok, true)
  assert.equal(comparable({ kind: 'probability' }, { kind: 'probability' }).ok, true)
})

test('a rank correlation is not a return correlation', () => {
  const v = comparable({ kind: 'ic' }, { kind: 'correlation' })
  assert.equal(v.ok, false)
  assert.match(v.reason ?? '', /rank agreement|linear agreement/)
})

test('a count is not a probability', () => {
  assert.equal(comparable({ kind: 'count' }, { kind: 'probability' }).ok, false)
})

test('a return is not a Sharpe ratio', () => {
  assert.equal(comparable({ kind: 'return' }, { kind: 'sharpe' }).ok, false)
})

test('a fraction is not a percentage', () => {
  // 0.61 and 61 are the same fact on two scales. Differencing them is wrong by
  // a factor of a hundred, and the result looks entirely reasonable.
  const v = comparable({ kind: 'share' }, { kind: 'percent' })
  assert.equal(v.ok, false)
  assert.match(v.reason ?? '', /percentage|fraction/)
})

test('the same kind against different targets is still incomparable', () => {
  const v = comparable({ kind: 'ic', basis: 'fwd_rank_21' }, { kind: 'ic', basis: 'fwd_ret_21' })
  assert.equal(v.ok, false)
  assert.match(v.reason ?? '', /fwd_rank_21|fwd_ret_21/)
})

test('a rank has no meaningful difference', () => {
  assert.equal(comparable({ kind: 'rank' }, { kind: 'rank' }).ok, false)
})

/* ── delta semantics ────────────────────────────────────────────────────── */

test('a difference is not an improvement', () => {
  // Higher IC is better; higher PBO is not. B − A is identical arithmetic and
  // opposite news.
  assert.equal(delta(0.05, 0.03, { kind: 'ic' }).interpretation, 'better')
  assert.equal(delta(0.93, 0.20, { kind: 'probability' }).interpretation, 'no-direction')
  // Drawdowns are signed negative here — every max_drawdown the registry
  // records is at or below zero — so a value nearer zero is the shallower
  // decline and the better outcome. Written with positive drawdowns this
  // assertion reads the other way, which is exactly the confusion the
  // `magnitude` kind exists to keep separate.
  assert.equal(delta(-0.30, -0.10, { kind: 'drawdown' }).interpretation, 'worse')
  assert.equal(delta(-0.10, -0.30, { kind: 'drawdown' }).interpretation, 'better')
  // The same loss reported positive inverts the direction.
  assert.equal(delta(0.30, 0.10, { kind: 'magnitude' }).interpretation, 'worse')
})

test('a metric with no direction is never judged', () => {
  for (const d of [delta(3.7, 1.2, { kind: 'tstat' }), delta(0.4, 0.1, { kind: 'weight' })]) {
    assert.equal(d.interpretation, 'no-direction')
  }
})

test('a difference against a missing value is refused, not treated as zero', () => {
  const d = delta(0.05, null, { kind: 'ic' })
  assert.equal(d.value, null)
  assert.equal(d.interpretation, 'incomparable')
  assert.match(d.reason ?? '', /not recorded|not zero/)
})

test('an incomparable pair yields no arithmetic at all', () => {
  const d = delta(0.05, 0.9, { kind: 'ic' }, { kind: 'probability' })
  assert.equal(d.value, null)
  assert.equal(d.interpretation, 'incomparable')
})

test('a multiple compares as a ratio, and refuses a zero baseline', () => {
  assert.equal(delta(12, 6, { kind: 'multiple' }).value, 2)
  const zero = delta(12, 0, { kind: 'multiple' })
  assert.equal(zero.value, null)
  assert.match(zero.reason ?? '', /undefined|zero/)
})

test('an unchanged value is unchanged, not better', () => {
  assert.equal(delta(0.05, 0.05, { kind: 'ic' }).interpretation, 'unchanged')
})

/* ── tone ───────────────────────────────────────────────────────────────── */

test('tone follows direction, never sign', () => {
  assert.equal(toneFor(3.67, 'tstat'), 'neutral', 'a large t-statistic is not good news')
  assert.equal(toneFor(0.929, 'probability'), 'neutral', 'a high PBO must not read as positive')
  assert.equal(toneFor(0.4, 'weight'), 'neutral')
  assert.equal(toneFor(0.05, 'ic'), 'positive')
  assert.equal(toneFor(-0.05, 'ic'), 'negative')
  assert.equal(toneFor(-0.3, 'drawdown'), 'negative', 'a decline is not good news')
  assert.equal(toneFor(0.3, 'magnitude'), 'negative', 'a loss reported positive is still a loss')
})

test('zero is never toned', () => {
  assert.equal(toneFor(0, 'ic'), 'neutral')
  assert.equal(toneFor(0, 'sharpe'), 'neutral')
})

/* ── absence, zero, and the values that are neither ─────────────────────── */

test('null, undefined, NaN and Infinity are all absent — and none is zero', () => {
  for (const v of [null, undefined, NaN, Infinity, -Infinity]) {
    const m = metric({ value: v as number, kind: 'sharpe' })
    assert.equal(m.absent, true, `${String(v)} should be absent`)
    assert.equal(m.formatted.text, '—')
    assert.notEqual(m.formatted.text, '0')
    assert.notEqual(m.formatted.text, '0.00')
  }
})

test('a measured zero is shown, and is not absence', () => {
  for (const kind of ['sharpe', 'ic', 'count', 'bps', 'multiple', 'share'] as Kind[]) {
    const m = metric({ value: 0, kind })
    assert.equal(m.absent, false, `a zero ${kind} is a measurement`)
    assert.match(m.formatted.text, /^0/, `a zero ${kind} should render as a zero`)
  }
})

test('a count is never signed', () => {
  assert.equal(formatCount(0).text, '0')
  assert.equal(formatCount(103).text, '103')
  assert.equal(formatCount(1).text, '1')
  for (const n of [0, 1, 12, 103]) {
    assert.doesNotMatch(formatCount(n).text, /^\+/, 'a population is not a change')
  }
})

test('a percentage and a share are different scales, and neither converts', () => {
  // 61 means 61%. The formatter must not multiply, and must not divide.
  assert.match(formatPercentage(61).text, /^61/)
  assert.equal(formatPercentage(61).unit, '%')
  assert.match(formatShare(0.61).text, /^0\.61/)
  assert.notEqual(formatShare(0.61).unit, '%')
})

test('negative values keep their sign across every kind that can be negative', () => {
  for (const kind of ['ic', 'sharpe', 'return', 'zscore', 'tstat', 'weight'] as Kind[]) {
    assert.match(metric({ value: -0.5, kind }).formatted.text, /^−|^-/, `${kind} lost its sign`)
  }
})

test('a probability stays on its own side of one', () => {
  assert.match(formatProbability(0.929).text, /^0\.9/)
  assert.match(formatProbability(0.2).text, /^0\.2/)
})

/* ── the presentation bundle ────────────────────────────────────────────── */

test('a metric answers what it is and what would make it wrong', () => {
  const m = metric({
    value: 0.0331,
    kind: 'ic',
    basis: 'fwd_rank_21',
    source: 'data/research/models/registry.json',
    asOf: '2026-09-01',
    method: 'Spearman rank correlation, per fold, averaged',
    failureConditions: ['leakage through a non-point-in-time join', 'insufficient cross-sectional coverage'],
  })
  assert.equal(m.semantics.label, 'information coefficient')
  assert.equal(m.semantics.direction, 'higher-better')
  assert.equal(m.tone, 'positive')
  assert.equal(m.comparableWith({ kind: 'ic', basis: 'fwd_rank_21' }).ok, true)
  assert.equal(m.comparableWith({ kind: 'ic', basis: 'fwd_ret_21' }).ok, false)
  assert.ok(m.failureConditions?.length)
  assert.ok(m.semantics.zeroMeans, 'an IC of zero should say what it means')
})

/* ── magnitude ──────────────────────────────────────────────────────────── */

test('a large currency amount is abbreviated, not printed in full', () => {
  // Apple's market capitalisation rendered as 4,789,955,589,281 — thirteen
  // digits nobody reads as a number. The eye counts commas to find the
  // magnitude and gets it wrong.
  assert.equal(format(4_789_955_589_281, 'currency').text, '4.79T')
  assert.equal(format(3_120_000_000, 'currency').text, '3.12B')
  assert.equal(format(45_600_000, 'currency').text, '45.60M')
})

test('a price is not abbreviated', () => {
  // The threshold is a million. Below it the exact amount is short enough to
  // read, and is what a share price looks like.
  assert.match(format(324.96, 'currency').text, /^324\.96$/)
  assert.match(format(999_999, 'currency').text, /^999,999/)
})

test('a negative amount keeps its sign through abbreviation', () => {
  assert.equal(format(-2_400_000_000, 'currency').text, '-2.40B')
})

test('beta is not signed', () => {
  // A beta of 1.09 is not "up 1.09"; there is no direction to state.
  assert.doesNotMatch(format(1.0942, 'multiple').text, /^\+/)
})

/* ── delta units ────────────────────────────────────────────────────────── */

test('the gap between two percentages is percentage points', () => {
  // A margin moving from 48.6% to 67.9% is +19.3pp. Calling that +19.3%
  // describes a different quantity entirely — a 19.3% relative increase would
  // land at 58.0%.
  const d = delta(67.9, 48.6, { kind: 'percent' })
  assert.equal(d.unit, 'pp')
  assert.match(d.formatted?.text ?? '', /^\+19\.3/)
})

test('the gap between two multiples is a ratio, and says so', () => {
  const d = delta(27.58, 37.32, { kind: 'multiple' })
  assert.equal(d.kind, 'multiplicative')
  assert.equal(d.unit, '×', 'a bare 0.74 between a P/E of 37 and one of 28 reads as an absolute difference')
})

test('a difference in a unitless kind carries no unit', () => {
  assert.equal(delta(0.05, 0.03, { kind: 'ic' }).unit, null)
  assert.equal(delta(1.4, 1.1, { kind: 'sharpe' }).unit, null)
})

test('a basis-point difference stays in basis points', () => {
  assert.equal(delta(15, 10, { kind: 'bps' }).unit, 'bp')
})
