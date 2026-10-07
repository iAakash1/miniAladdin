/* The search box's instant local matches, and the highlight helper.

   These tested a `localMatches` that read a `Watchlist[]` and an analysis
   history — stores the live search box does not use. It was correct, tested,
   and wired to nothing, so typing a ticker the reader already had on this
   device still showed an empty list until the network answered. The helper
   now takes the two lists the box actually holds, and these assert the
   behaviour that reaches a reader. */

import assert from 'node:assert/strict'
import test from 'node:test'
import { looksLikeSymbol, rankSecurities, symbolKey, typedSymbol } from '../src/lib/security'
import { highlightSegments, localMatches } from '../src/lib/search'

test('a ticker in the watchlist matches before the network answers', () => {
  // The reported case: NVDA in the reader's own list, "Nothing found".
  const out = localMatches('NVD', [], ['NVDA', 'AAPL'])
  assert.deepEqual(out, [{ symbol: 'NVDA', context: 'Watchlist' }])
})

test('an explicitly watched symbol outranks one merely visited', () => {
  const out = localMatches('A', ['AMD'], ['AAPL'])
  assert.deepEqual(out.map((m) => m.symbol), ['AAPL', 'AMD'])
  assert.equal(out[0].context, 'Watchlist')
  assert.equal(out[1].context, 'Recent')
})

test('matching is by prefix, not substring', () => {
  /* "AP" must not surface GAP above AAPL. In a ticker box the reader is
     typing the start of a symbol, and substring matching puts accidental
     interior hits beside the thing they are reaching for. */
  const out = localMatches('AP', ['GAP', 'SNAP'], [])
  assert.deepEqual(out, [], 'an interior match was surfaced as a local hit')
  assert.deepEqual(localMatches('GA', ['GAP'], []).map((m) => m.symbol), ['GAP'])
})

test('a symbol in both lists appears once, as the watchlist entry', () => {
  const out = localMatches('AAP', ['AAPL'], ['AAPL'])
  assert.equal(out.length, 1)
  assert.equal(out[0].context, 'Watchlist')
})

test('matching is case-insensitive on both sides', () => {
  assert.deepEqual(localMatches('aap', [], ['aapl']).map((m) => m.symbol), ['AAPL'])
})

test('an empty query matches nothing rather than everything', () => {
  assert.deepEqual(localMatches('', ['AAPL'], ['MSFT']), [])
  assert.deepEqual(localMatches('   ', ['AAPL'], ['MSFT']), [])
})

test('the local list is capped so it cannot bury the vendor answer', () => {
  const many = ['A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7']
  assert.equal(localMatches('A', many, []).length, 5)
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

/* Share classes are written three ways and a reader types a fourth.

   Searching "BRK B" or "BRK-B" returned nothing: neither spelling is a prefix
   or substring of the symbol BRK.B, so the ranker scored the row as unrelated
   and dropped it — the one security the reader named was the one thing
   removed. The local matcher had the same blind spot against a watchlist that
   held BRK.B. */
const BERKSHIRE = [
  { symbol: 'BRK.A', name: 'Berkshire Hathaway Inc-Cl A', via: 'x' },
  { symbol: 'BRK.B', name: 'Berkshire Hathaway Inc-Cl B', via: 'x' },
]

test('every spelling of a share class reaches its listing', () => {
  for (const q of ['BRK.B', 'BRK-B', 'BRK B', 'brk b', 'BRK/B', 'BRKB']) {
    assert.equal(rankSecurities(q, BERKSHIRE)[0]?.symbol, 'BRK.B', `"${q}" did not reach BRK.B`)
  }
})

test('a share-class query does not promote the other class', () => {
  assert.equal(rankSecurities('BRK B', BERKSHIRE)[0].symbol, 'BRK.B')
  assert.equal(rankSecurities('BRK A', BERKSHIRE)[0].symbol, 'BRK.A')
})

test('typing the root still lists every class', () => {
  assert.deepEqual(rankSecurities('BRK', BERKSHIRE).map((r) => r.symbol), ['BRK.A', 'BRK.B'])
  // A trailing separator mid-typing must not empty the list.
  assert.deepEqual(rankSecurities('BRK-', BERKSHIRE).map((r) => r.symbol), ['BRK.A', 'BRK.B'])
})

test('an exact literal symbol outranks a spelling-equivalent one', () => {
  const rows = [
    { symbol: 'BRK-B', name: 'Berkshire Hathaway Inc-Cl B', via: 'x' },
    { symbol: 'BRK.B', name: 'Berkshire Hathaway Inc-Cl B', via: 'x' },
  ]
  assert.equal(rankSecurities('BRK.B', rows)[0].symbol, 'BRK.B')
  assert.equal(rankSecurities('BRK-B', rows)[0].symbol, 'BRK-B')
})

test('AAPL reaches AAPL and does not surface APLE', () => {
  const rows = [
    { symbol: 'APLE', name: 'Apple Hospitality REIT Inc', via: 'x' },
    { symbol: 'AAPL', name: 'Apple Inc', via: 'x' },
  ]
  assert.deepEqual(rankSecurities('AAPL', rows).map((r) => r.symbol), ['AAPL'])
})

test('a ticker nobody lists returns nothing rather than a guess', () => {
  assert.deepEqual(rankSecurities('QZXW', BERKSHIRE), [])
})

test('the local matcher finds a watched share class by any spelling', () => {
  for (const q of ['BRK B', 'BRK-B', 'brk.b']) {
    assert.deepEqual(localMatches(q, [], ['BRK.B']).map((m) => m.symbol), ['BRK.B'], q)
  }
  assert.deepEqual(localMatches('BRK B', [], ['AAPL']), [])
})

test('a spaced share class is ticker-shaped and opens as a dotted symbol', () => {
  assert.equal(looksLikeSymbol('BRK B'), true)
  assert.equal(looksLikeSymbol('brk/b'), true)
  assert.equal(typedSymbol('BRK B'), 'BRK.B')
  assert.equal(typedSymbol('brk/b'), 'BRK.B')
  // Already symbols: not rewritten.
  assert.equal(typedSymbol('BRK-B'), 'BRK-B')
  assert.equal(typedSymbol('BRK.B'), 'BRK.B')
  assert.equal(typedSymbol('aapl'), 'AAPL')
})

test('free text is not mistaken for a share class', () => {
  assert.equal(looksLikeSymbol('copper miners'), false)
  assert.equal(looksLikeSymbol('apple inc'), false)
  assert.equal(symbolKey('BRK.B'), symbolKey('brk b'))
  assert.notEqual(symbolKey('AAPL'), symbolKey('APLE'))
})
