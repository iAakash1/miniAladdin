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

/* The account's research record writes verdicts as "BUY" and "STRONG_BUY";
   this browser's snapshots write "Buy". Ranked as written, every recorded run
   sorted with the unanalysed names and the column mixed both spellings. */
test('a verdict from either store is spelled, and therefore ranked, one way', async () => {
  const { canonicalVerdict } = await import('../src/components/terminal/PortfolioView')
  assert.equal(canonicalVerdict('BUY'), 'Buy')
  assert.equal(canonicalVerdict('STRONG_BUY'), 'Strong Buy')
  assert.equal(canonicalVerdict('strong sell'), 'Strong Sell')
  assert.equal(canonicalVerdict('Hold'), 'Hold')
  // Anything outside the five verdicts is left as the source wrote it.
  assert.equal(canonicalVerdict('INSUFFICIENT_DATA'), 'INSUFFICIENT_DATA')
})

/* Holdings are their own record. The page used to render positions and the
   book's figures only inside the watchlist branch, so an account with
   positions and no list saw "No watchlists yet" and nothing it held. */
test('the portfolio renders holdings whatever the state of the watchlists', async () => {
  const { readFileSync } = await import('node:fs')
  const { join } = await import('node:path')
  const src = readFileSync(join(__dirname, '..', 'src', 'components', 'terminal', 'PortfolioView.tsx'), 'utf8')
  const page = src.slice(src.indexOf('export default function PortfolioView'))
  assert.match(page, /<PositionsPanel \/>/)
  assert.match(page, /<PortfolioIntelligence \/>/)
  // The list monitor is a sibling, not a gate.
  assert.ok(page.indexOf('<PositionsPanel />') < page.indexOf('<ListMonitor />'))
  assert.doesNotMatch(page, /useWatchlists|lists\.length/)
})
