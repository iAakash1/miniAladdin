/* Tests for the pure local-match + highlight logic behind ScreenSearch
   (search-fix pass). */

import assert from 'node:assert/strict'
import test from 'node:test'
import type { AnalysisSnapshot } from '../src/lib/history'
import { rankSecurities } from '../src/lib/security'
import { highlightSegments, localMatches } from '../src/lib/search'
import type { Watchlist } from '../src/lib/watchlists'

function watchlist(overrides: Partial<Watchlist> = {}): Watchlist {
  return { id: 'wl_1', name: 'Tech', tickers: ['AAPL'], createdAt: '2026-07-01T00:00:00Z', ...overrides }
}

function snapshot(overrides: Partial<AnalysisSnapshot> = {}): AnalysisSnapshot {
  return {
    ts: '2026-07-01T00:00:00Z',
    verdict: 'Hold',
    rawVerdict: 'Hold',
    confidence: 70,
    riskLevel: 'MEDIUM',
    rawScore: 0.1,
    momentumScore: 0.2,
    fundamentalScore: 0,
    newsScore: null,
    macroGate: 1,
    srm: 1,
    regimes: [],
    factors: [],
    price: 100,
    ...overrides,
  }
}

test('localMatches finds a ticker sitting in a watchlist — the reported NVDA scenario', () => {
  const lists = [watchlist({ name: 'AI', tickers: ['NVDA', 'AMD'] })]
  const matches = localMatches('NVDA', lists, {})
  assert.equal(matches.length, 1)
  assert.equal(matches[0].symbol, 'NVDA')
  assert.match(matches[0].context, /AI/)
})

test('localMatches is substring-based and also searches analysis history', () => {
  const history = { TSLA: [snapshot({ verdict: 'Sell' })] }
  const matches = localMatches('TSL', [], history)
  assert.equal(matches.length, 1)
  assert.equal(matches[0].symbol, 'TSLA')
  assert.match(matches[0].context, /Sell/)
})

test('localMatches returns nothing for an empty query', () => {
  assert.deepEqual(localMatches('', [watchlist()], {}), [])
})

test('localMatches de-duplicates a ticker that appears in both a watchlist and history', () => {
  const lists = [watchlist({ tickers: ['NVDA'] })]
  const history = { NVDA: [snapshot()] }
  const matches = localMatches('NVDA', lists, history)
  assert.equal(matches.length, 1)
})

test('localMatches ignores a ticker with an empty history timeline', () => {
  const matches = localMatches('NVDA', [], { NVDA: [] })
  assert.deepEqual(matches, [])
})

test('highlightSegments wraps the matched substring case-insensitively', () => {
  const segments = highlightSegments('NVIDIA Corporation', 'vidia')
  assert.deepEqual(segments, [
    { text: 'N', match: false },
    { text: 'VIDIA', match: true },
    { text: ' Corporation', match: false },
  ])
})

test('highlightSegments returns the text unmatched when the query is empty or absent', () => {
  assert.deepEqual(highlightSegments('AAPL', ''), [{ text: 'AAPL', match: false }])
  assert.deepEqual(highlightSegments('AAPL', 'zzz'), [{ text: 'AAPL', match: false }])
})

test('highlightSegments matches a query that spans the full string', () => {
  assert.deepEqual(highlightSegments('NVDA', 'nvda'), [{ text: 'NVDA', match: true }])
})

/* The symbol database answers something for almost any input.

   Searching "ZZZZNOTREAL" came back with ten securities led by ZJUN — nothing
   to do with what was typed. Ranked last they were still on screen under the
   heading of a search, where the first row reads as the best answer to the
   query. */
test('rows the query does not appear in are dropped, not ranked last', () => {
  const junk = rankSecurities('ZZZZNOTREAL', [
    { symbol: 'ZJUN', name: 'Some Fund', via: 'x' },
    { symbol: 'ZSEP', name: 'Another Fund', via: 'x' },
  ])
  assert.equal(junk.length, 0, 'unrelated rows survived the ranking')
})

test('a genuine match on symbol or name still survives', () => {
  const rows = [
    { symbol: 'ZJUN', name: 'Some Fund', via: 'x' },
    { symbol: 'AAPL', name: 'Apple Inc.', via: 'x' },
  ]
  assert.deepEqual(rankSecurities('AAPL', rows).map((r) => r.symbol), ['AAPL'])
  // Company-name search must keep working — "apple" finds AAPL by name.
  assert.deepEqual(rankSecurities('apple', rows).map((r) => r.symbol), ['AAPL'])
  // A substring of the symbol counts too.
  assert.deepEqual(rankSecurities('JUN', rows).map((r) => r.symbol), ['ZJUN'])
})

test('an exact ticker still outranks a name match', () => {
  const rows = [
    { symbol: 'APPS', name: 'Digital Turbine', via: 'x' },
    { symbol: 'APP', name: 'Applovin', via: 'x' },
  ]
  assert.equal(rankSecurities('APP', rows)[0].symbol, 'APP')
})
