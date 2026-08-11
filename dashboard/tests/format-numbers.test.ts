/* Numeric formatting is a trust surface.

   A research terminal that prints "+Infinity%" or "-$0.00" is telling the
   reader something false about the data. Both were reachable from real
   inputs: a Sharpe ratio over zero realised volatility is `Infinity`, and a
   return of -0.0000004 rounds to "-0.00%" — a loss that did not happen. */
import { strict as assert } from 'node:assert'
import test from 'node:test'
import { fmtNum, fmtPct, fmtPctRaw, fmtPrice } from '../src/lib/format'

const MISSING = '—'

test('nothing that is not a finite number ever reaches the screen', () => {
  for (const bad of [NaN, Infinity, -Infinity, null, undefined]) {
    assert.equal(fmtNum(bad), MISSING, `fmtNum(${bad})`)
    assert.equal(fmtPct(bad), MISSING, `fmtPct(${bad})`)
    assert.equal(fmtPctRaw(bad), MISSING, `fmtPctRaw(${bad})`)
    assert.equal(fmtPrice(bad), MISSING, `fmtPrice(${bad})`)
  }
})

test('a value that rounds to zero carries no sign', () => {
  // The reader scans a column of returns; a "-" on a number that did not
  // move reads as a loss.
  assert.equal(fmtNum(-0), '0.00')
  assert.equal(fmtNum(-0.000001), '0.00')
  assert.equal(fmtPct(-0.0000004), '0.00%')
  assert.equal(fmtPct(0), '0.00%')
  assert.equal(fmtPctRaw(-0.001), '0.00%')
  assert.equal(fmtPrice(-0), '$0.00')
  assert.equal(fmtPrice(-0.0001), '$0.00')
})

test('a real move keeps its sign', () => {
  assert.equal(fmtPct(0.0431), '+4.31%')
  assert.equal(fmtPct(-0.0431), '-4.31%')
  assert.equal(fmtNum(-1.5), '-1.50')
  assert.equal(fmtPctRaw(-4.47), '-4.47%')
  assert.equal(fmtPrice(-12.5), '-$12.50')
})

test('the plus sign is decided after rounding, never before', () => {
  // 0.000001 * 100 = 0.0001 -> "0.00": positive, but not positive enough to
  // claim a gain.
  assert.equal(fmtPct(0.000001), '0.00%')
  assert.equal(fmtPct(0.00006), '+0.01%')
})

test('signed=false suppresses the plus but keeps a real minus', () => {
  assert.equal(fmtPct(0.0431, 2, false), '4.31%')
  assert.equal(fmtPct(-0.0431, 2, false), '-4.31%')
})

test('digit control is respected without reintroducing signed zero', () => {
  assert.equal(fmtNum(-0.004, 2), '0.00')
  assert.equal(fmtNum(-0.004, 3), '-0.004')
  assert.equal(fmtPct(-0.00004, 2), '0.00%')
  assert.equal(fmtPct(-0.00004, 3), '-0.004%')
})
