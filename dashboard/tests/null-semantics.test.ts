/* Absence must survive the frontend boundary.

   `normalizeAnalysis`, `normalizeMacro` and `normalizeChart` converted every
   missing financial field into a real zero: price, both returns, volatility,
   Sharpe, Sortino, RSI, max drawdown, the term spread, CPI, the Fed funds
   rate and session volume. A provider outage arrived at the screen as a
   security worth $0 that returned 0%, carried no volatility, had never drawn
   down, and traded nothing — a complete, confident, false picture.

   The adjacent fields (peRatio, eps, beta) were already `?? null`, so these
   were the outliers rather than the convention.

   The distinction these pin is exact: a value the API omitted is null, and a
   value the API sent as 0 stays 0. Nullish coalescing gets that right and
   truthiness does not, which is why `?? null` is the rule and `|| 0` is the
   bug. */
import { strict as assert } from 'node:assert'
import test from 'node:test'

import { normalizeAnalysis, normalizeChart, normalizeChartSeries, normalizeMacro } from '../src/lib/api'
import { parsePercentString } from '../src/lib/format'

/** The eight fields that were coerced. */
const COERCED = [
  ['price', 'current_price'],
  ['return5d', 'return_5d'],
  ['return21d', 'return_21d'],
  ['volatility', 'volatility'],
  ['sharpe', 'sharpe_ratio'],
  ['sortino', 'sortino_ratio'],
  ['rsi', 'rsi_14'],
  ['maxDrawdown', 'max_drawdown'],
] as const

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const analysis = (technicals: Record<string, unknown>): any =>
  normalizeAnalysis({ ticker: 'X', technicals } as never)

// ── missing stays missing ───────────────────────────────────────────────────

for (const [field, apiKey] of COERCED) {
  test(`${field} is null when the API omits ${apiKey}`, () => {
    assert.equal(analysis({})[field], null,
      `${field} was manufactured from an absent ${apiKey}`)
  })

  test(`${field} is null when the API sends ${apiKey}: null`, () => {
    assert.equal(analysis({ [apiKey]: null })[field], null)
  })

  test(`${field} keeps a real zero`, () => {
    // The whole point of `?? null` over `|| 0`: zero is a measurement.
    assert.equal(analysis({ [apiKey]: 0 })[field], 0,
      `${field} discarded a genuine zero`)
  })

  test(`${field} keeps a negative value`, () => {
    assert.equal(analysis({ [apiKey]: -0.25 })[field], -0.25)
  })
}

test('a technicals block that is entirely absent yields nulls, not zeros', () => {
  const a = analysis({})
  for (const [field] of COERCED) assert.equal(a[field], null)
})

// ── macro ───────────────────────────────────────────────────────────────────

test('no macro payload at all yields no economic claims', () => {
  const m = normalizeMacro(null)
  assert.equal(m.srm, null, 'a risk multiplier was invented from nothing')
  assert.equal(m.yieldSpread, null)
  assert.equal(m.cpi, null)
  assert.equal(m.fedRate, null)
  assert.equal(m.inverted, null, 'an unread curve was reported as not inverted')
  assert.equal(m.recessionWarning, null)
  assert.equal(m.status, 'UNAVAILABLE')
})

test('the backend unavailable block survives the boundary intact', () => {
  const m = normalizeMacro({
    risk_multiplier: null,
    status: 'UNAVAILABLE',
    yield_spread: null,
    inflation_rate: null,
    fed_funds_rate: null,
    yield_curve_inverted: null,
    recession_warning: null,
  } as never)
  assert.equal(m.srm, null, 'the frontend coerced the multiplier back to a number')
  assert.equal(m.yieldSpread, null)
  assert.equal(m.cpi, null)
  assert.equal(m.fedRate, null)
})

test('a partial macro reading keeps what arrived and nulls what did not', () => {
  const m = normalizeMacro({
    risk_multiplier: null,
    status: 'UNAVAILABLE',
    yield_spread: 0.41,
    inflation_rate: null,
    fed_funds_rate: '3.63%',
  } as never)
  assert.equal(m.yieldSpread, 0.41)
  assert.equal(m.fedRate, 3.63)
  assert.equal(m.cpi, null)
})

test('a genuine zero spread is a reading, not an absence', () => {
  const m = normalizeMacro({ risk_multiplier: 1.0, yield_spread: 0, status: 'STABLE' } as never)
  assert.equal(m.yieldSpread, 0)
  assert.equal(m.srm, 1.0)
})

// ── percent strings ─────────────────────────────────────────────────────────

test('an unparseable percent is absent rather than zero', () => {
  assert.equal(parsePercentString(null), null)
  assert.equal(parsePercentString(undefined), null)
  assert.equal(parsePercentString('N/A'), null)
  assert.equal(parsePercentString(''), null)
})

test('a real percent parses, including zero and negatives', () => {
  assert.equal(parsePercentString('3.52%'), 3.52)
  assert.equal(parsePercentString('0%'), 0)
  assert.equal(parsePercentString('-0.35%'), -0.35)
  assert.equal(parsePercentString(2.5), 2.5)
})

test('non-finite input is rejected, not passed through', () => {
  // An Infinity that arrived from a provider is not a rate.
  assert.equal(parsePercentString(Number.POSITIVE_INFINITY), null)
  assert.equal(parsePercentString(Number.NEGATIVE_INFINITY), null)
  assert.equal(parsePercentString(Number.NaN), null)
})

// ── chart ───────────────────────────────────────────────────────────────────

test('a session with no reported volume is null, not a halt', () => {
  const [point] = normalizeChart({ prices: [{ date: '2026-09-04', close: 100 }] } as never)
  assert.equal(point.volume, null, 'an unreported volume was rendered as no trading')
  assert.equal(point.close, 100)
})

test('a genuinely zero volume survives', () => {
  const [point] = normalizeChart({ prices: [{ date: '2026-09-04', close: 100, volume: 0 }] } as never)
  assert.equal(point.volume, 0)
})

test('an empty price list is an empty chart, not an error', () => {
  assert.deepEqual(normalizeChart({ prices: [] } as never), [])
})


/* ── a provider outage is not an empty chart ──────────────────────────────── */

test('an outage and a security with no history are distinguishable', () => {
  /* Both carry no prices. Conflating them told a reader that a security has
     never traded when the vendors were simply down. */
  const outage = normalizeChartSeries({
    ticker: 'AAPL', prices: [], status: 'unavailable', error: 'all vendors failed',
  } as never)
  const empty = normalizeChartSeries({
    ticker: 'AAPL', prices: [], status: 'empty', error: null,
  } as never)

  assert.deepEqual(outage.points, [])
  assert.deepEqual(empty.points, [])
  assert.notEqual(outage.status, empty.status)
  assert.equal(outage.reason, 'all vendors failed')
  assert.match(String(empty.reason), /No sessions returned/)
})

test('a healthy series carries no reason and names its source', () => {
  const s = normalizeChartSeries({
    ticker: 'AAPL', status: 'ok', source: 'polygon',
    prices: [{ date: '2026-09-04', close: 100, volume: 10 }],
  } as never)
  assert.equal(s.status, 'ok')
  assert.equal(s.reason, null)
  assert.equal(s.source, 'polygon')
  assert.equal(s.points.length, 1)
})

test('a stale series is drawn but labelled stale', () => {
  const s = normalizeChartSeries({
    ticker: 'AAPL', status: 'stale',
    prices: [{ date: '2026-09-04', close: 100 }],
  } as never)
  assert.equal(s.status, 'stale')
  assert.equal(s.reason, null, 'a stale series that has points has nothing to explain')
})

test('a response with no status falls back on whether it has points', () => {
  // Older payloads, and any caller that has not been updated.
  assert.equal(normalizeChartSeries({ prices: [] } as never).status, 'empty')
  assert.equal(
    normalizeChartSeries({ prices: [{ date: 'd', close: 1 }] } as never).status, 'ok',
  )
})
