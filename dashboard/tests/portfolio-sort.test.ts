/* Watchlist column sorting.

   The rule that matters: a row with no value sinks in BOTH directions. A
   ticker that has never been analysed has no confidence — it is absent, not
   zero — and sorting confidence ascending must not bury the analysed rows
   under a block of blanks. */
import { strict as assert } from 'node:assert'
import test from 'node:test'
import { nextSort, sortRows, type SortState } from '../src/components/terminal/PortfolioView'

const row = (
  ticker: string,
  price: number | null,
  verdict: string | null,
  confidence: number | null,
  ts: string | null,
) => ({
  ticker,
  quote: price === null ? undefined : { price, change_1d: null, change_1w: null },
  latest: verdict && confidence !== null && ts ? { verdict, confidence, ts } : null,
})

const rows = [
  row('AAPL', 190, 'Buy', 62, '2026-08-01T00:00:00Z'),
  row('ZZZ', null, null, null, null),          // never analysed, no quote
  row('MSFT', 410, 'Hold', 44, '2026-07-01T00:00:00Z'),
  row('NVDA', 217, 'Strong Buy', 71, '2026-08-10T00:00:00Z'),
]

const ids = (list: Array<{ ticker: string }>) => list.map((r) => r.ticker)

test('descending puts the largest first', () => {
  assert.deepEqual(
    ids(sortRows(rows, { key: 'confidence', dir: 'desc' })),
    ['NVDA', 'AAPL', 'MSFT', 'ZZZ'],
  )
})

test('rows with no value sink in ascending order too', () => {
  const sorted = ids(sortRows(rows, { key: 'confidence', dir: 'asc' }))
  assert.deepEqual(sorted, ['MSFT', 'AAPL', 'NVDA', 'ZZZ'])
  assert.equal(sorted[sorted.length - 1], 'ZZZ', 'an unanalysed row must never lead an ascending sort')
})

test('verdict sorts by conviction, not alphabetically', () => {
  // "Strong Buy" must outrank "Buy"; alphabetical would put Buy first.
  assert.deepEqual(
    ids(sortRows(rows, { key: 'verdict', dir: 'desc' })),
    ['NVDA', 'AAPL', 'MSFT', 'ZZZ'],
  )
})

test('ticker sorts as text', () => {
  assert.deepEqual(
    ids(sortRows(rows, { key: 'ticker', dir: 'asc' })),
    ['AAPL', 'MSFT', 'NVDA', 'ZZZ'],
  )
})

test('most recently analysed first', () => {
  assert.deepEqual(
    ids(sortRows(rows, { key: 'analyzed', dir: 'desc' })),
    ['NVDA', 'AAPL', 'MSFT', 'ZZZ'],
  )
})

test('no active column leaves the default ranking untouched', () => {
  const state: SortState = { key: null, dir: 'desc' }
  assert.equal(sortRows(rows, state), rows, 'should return the same array reference')
})

test('sorting never drops or duplicates a row', () => {
  for (const key of ['ticker', 'price', 'verdict', 'confidence', 'analyzed'] as const) {
    for (const dir of ['asc', 'desc'] as const) {
      const out = sortRows(rows, { key, dir })
      assert.equal(out.length, rows.length, `${key}/${dir} changed row count`)
      assert.deepEqual(new Set(ids(out)), new Set(ids(rows)), `${key}/${dir} lost a row`)
    }
  }
})

test('clicking a column cycles desc -> asc -> off', () => {
  let s: SortState = { key: null, dir: 'desc' }
  s = nextSort(s, 'confidence')
  assert.deepEqual(s, { key: 'confidence', dir: 'desc' })
  s = nextSort(s, 'confidence')
  assert.deepEqual(s, { key: 'confidence', dir: 'asc' })
  s = nextSort(s, 'confidence')
  assert.equal(s.key, null, 'a third click returns to the default ranking')
})

test('clicking a different column starts it descending', () => {
  const s = nextSort({ key: 'confidence', dir: 'asc' }, 'price')
  assert.deepEqual(s, { key: 'price', dir: 'desc' })
})
