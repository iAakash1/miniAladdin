/* The price-series arithmetic, and the two scales in one payload.

   Every figure in this section was already being computed and returned on
   every research request, and none of it reached the security page — the two
   components that read `technicals` are not on that route. Twenty-four fields
   arriving and being discarded.

   The trap in exposing them: `technicals.return_5d` is 0.0266, a fraction,
   while `ratios.gross_margin_ttm` in the same response is 48.65, a
   percentage. Similar names, one response, scales a hundred apart. */
import { strict as assert } from 'node:assert'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

const ROOT = new URL('../src/', import.meta.url).pathname
const M = readFileSync(join(ROOT, 'components/terminal/security/MarketStats.tsx'), 'utf8')
/* Comments explain why the signals are excluded, and naming a thing in order
   to exclude it is not rendering it. Stripped rather than the pattern
   loosened, so a genuine render is still caught. */
const CODE = M.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '')

test('fractions are scaled exactly once, at the boundary', () => {
  // No formatter in this product multiplies, so the conversion has to happen
  // where the scale is known — and exactly once.
  assert.match(M, /const pct = /)
  assert.match(M, /v \* 100/)
  const doubled = M.match(/pct\([^)]*\)\s*\*\s*100/)
  assert.equal(doubled, null, 'a value is scaled twice')
})

test('every fraction field goes through the scaler', () => {
  for (const field of ['return_5d', 'return_21d', 'volatility', 'max_drawdown']) {
    assert.match(M, new RegExp(`pct\\(t\\.${field}\\)`), `${field} is not scaled`)
  }
})

test('ratios and indices are not scaled', () => {
  // Sharpe, Sortino, RSI and beta are not fractions of anything. Multiplying
  // a Sharpe of 0.99 by a hundred would report 99.
  for (const field of ['sharpe_ratio', 'sortino_ratio', 'rsi_14', 'beta']) {
    assert.doesNotMatch(M, new RegExp(`pct\\(t\\.${field}\\)`), `${field} is being scaled`)
  }
})

test('the trading signals are deliberately not rendered', () => {
  // The block carries raw_signal and risk_adjusted_signal, both currently
  // "Buy". They come from a scoring function, not from anything promoted —
  // the programme's verdict is NO PRODUCTION CANDIDATE. Rendering "Buy"
  // beside a price would make an unpromoted heuristic look endorsed.
  assert.doesNotMatch(CODE, /raw_signal|risk_adjusted_signal/,
    'a trading signal is being rendered')
})

test('the pre-formatted market cap string is not used here', () => {
  // technicals.market_cap arrives as "$4.68T" — a string that cannot carry a
  // unit or a provenance chain. The profile returns a number; that one wins.
  assert.doesNotMatch(CODE, /t\.market_cap/)
})

test('every derived figure declares its method and when it fails', () => {
  const adds = [...M.matchAll(/add\('([^']+)'/g)].map((m) => m[1])
  assert.ok(adds.length >= 6, 'too few measures to be worth checking')
  // Each add() call must carry a claim and a method.
  const calls = M.split('add(').slice(1)
  for (const c of calls.slice(0, adds.length)) {
    const head = c.slice(0, 1400)
    assert.match(head, /claim:/, 'a measure has no claim')
    assert.match(head, /method:/, 'a measure has no method')
  }
})

test('the Sharpe discloses that no risk-free rate is subtracted', () => {
  // It is (mean × 252) / (std × √252). Most readers assume a Sharpe nets off
  // a risk-free rate; this one does not, and a positive rate would lower it.
  assert.match(M, /No risk-free rate is subtracted/)
  assert.match(M, /risk-free rate is zero/i)
})

test('annualising from three months is named as a failure condition', () => {
  // A yearly figure from about sixty-three observations is noisy, and the
  // number itself does not look noisy.
  assert.match(M, /sixty-three observations|about 63 sessions/)
})

test('an absent statistic is absent, never zero', () => {
  assert.match(M, /if \(value === null\) return/)
  assert.match(M, /not a statement that the series is flat/)
})
