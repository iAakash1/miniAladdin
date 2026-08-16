/* Visual identity is an attribution surface.

   A favicon beside a headline is a claim about who published it, and a logo
   beside a ticker is a claim about which company a row is. Both are derived
   from the payload rather than looked up by hand, so the derivation is where
   a wrong attribution would come from — not from a typo in a mapping table
   somebody would notice, but from a fallback quietly guessing when it had
   nothing to go on.

   The property these tests hold: with no evidence, produce nothing. An empty
   string renders as "no mark"; a plausible-looking guess renders as a
   publisher who never said it. */
import { strict as assert } from 'node:assert'
import test from 'node:test'

import { faviconFor, logoSources, sectorProxy, sourceDomain, sourceLabel } from '../src/lib/identity'

test('an article URL identifies its own source, whatever the feed calls itself', () => {
  // Real observed value: RSS aggregators prepend banner text to the vendor
  // name, so the name is not a reliable identifier but the URL always is.
  assert.equal(
    sourceDomain('🔴 BREAKING | Barchart', 'https://www.barchart.com/story/news/3867712/x'),
    'barchart.com',
  )
  assert.equal(sourceDomain('EUROPE SAYS', 'https://www.europesays.com/3194715/'), 'europesays.com')
  assert.equal(
    sourceDomain('Markets Insider', 'https://markets.businessinsider.com/news/x'),
    'markets.businessinsider.com',
  )
})

test('the URL wins over the vendor name, because it is the source itself', () => {
  // A name we happen to have mapped must not override the actual address the
  // claim came from.
  assert.equal(sourceDomain('Reuters', 'https://apnews.com/article/x'), 'apnews.com')
})

test('an internal vendor id resolves without a URL', () => {
  // Macro cards carry `source: "fred"` and no link at all.
  assert.equal(sourceDomain('fred'), 'fred.stlouisfed.org')
  assert.equal(sourceDomain('SEC'), 'sec.gov')
  assert.equal(sourceDomain('yfinance'), 'finance.yahoo.com')
})

test('a decorated vendor name still resolves through a contained key', () => {
  assert.equal(sourceDomain('🔴 BREAKING | Barchart'), 'barchart.com')
  assert.equal(sourceDomain('Seeking Alpha News Desk'), 'seekingalpha.com')
})

test('nothing identifiable produces no mark rather than a guess', () => {
  // The failure that matters: attributing a claim to a publisher who did not
  // make it. An empty domain renders as the source's initial instead.
  assert.equal(sourceDomain(null, null), '')
  assert.equal(sourceDomain('Some Local Newsletter'), '')
  assert.equal(sourceDomain('', ''), '')
})

test('an unparseable URL falls through to the vendor map instead of throwing', () => {
  assert.equal(sourceDomain('fred', 'not a url'), 'fred.stlouisfed.org')
  assert.equal(sourceDomain('Nobody', 'not a url'), '')
})

test('the display name drops feed banner decoration but never becomes empty', () => {
  assert.equal(sourceLabel('🔴 BREAKING | Barchart'), 'Barchart')
  assert.equal(sourceLabel('Seeking Alpha'), 'Seeking Alpha')
  // With no name at all, the domain stands in; with neither, a word that is
  // honest about the absence.
  assert.equal(sourceLabel(null, 'https://www.reuters.com/x'), 'reuters.com')
  assert.equal(sourceLabel(null, null), 'Unattributed')
})

test('every logo provider is offered for a ticker, best first', () => {
  const sources = logoSources('nvda')
  assert.ok(sources.length >= 2, 'a single provider is not a fallback chain')
  // Uppercased: providers key on the listed symbol.
  assert.ok(sources.every((url) => url.includes('NVDA')), sources.join(' '))
  assert.equal(new Set(sources).size, sources.length, 'a repeated URL is not a second chance')
})

test('symbols that need escaping survive the URL', () => {
  // Class shares and preferreds carry punctuation that would otherwise end a
  // path segment early.
  const [first] = logoSources('BRK-B')
  assert.ok(first.includes('BRK-B'), first)
  assert.ok(!logoSources('A B').some((url) => url.includes(' ')), 'unescaped space')
})

test('no ticker means no request', () => {
  assert.deepEqual(logoSources(''), [])
  assert.deepEqual(logoSources('   '), [])
})

test('a sector borrows the identity of the ETF that actually trades it', () => {
  // These are the symbols the breadth map already uses, so Market and a
  // company report name a sector the same way.
  assert.equal(sectorProxy('Technology'), 'XLK')
  assert.equal(sectorProxy('information technology'), 'XLK')
  assert.equal(sectorProxy('Consumer Cyclical'), 'XLY')
  assert.equal(sectorProxy('Real Estate'), 'XLRE')
})

test('an unmapped sector gets no mark rather than a nearby one', () => {
  assert.equal(sectorProxy('Conglomerates'), '')
  assert.equal(sectorProxy(null), '')
  assert.equal(sectorProxy(''), '')
})

test('favicon URLs escape the domain they are given', () => {
  const url = faviconFor('example.com/../evil')
  assert.ok(!url.includes('../'), url)
})
