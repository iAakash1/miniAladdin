/* Unit tests for the news pipeline's pure functions.
   Run: npm test  (uses node's built-in test runner via tsx) */

import assert from 'node:assert/strict'
import test from 'node:test'
import { cleanText, parseFeedXml } from '../src/lib/news/parse'
import { classify } from '../src/lib/news/classify'

/* ---------- Fixtures modeled on the real feeds ---------- */

const YAHOO_STYLE_RSS = `<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:media="http://search.yahoo.com/mrss/" version="2.0">
  <channel>
    <title>Yahoo Finance</title>
    <item>
      <title>Fed holds rates steady as inflation cools to 4.1%</title>
      <link>https://finance.yahoo.com/news/fed-holds-rates.html</link>
      <pubDate>Thu, 02 Jul 2026 14:10:00 +0000</pubDate>
      <description><![CDATA[The central bank kept its benchmark rate unchanged&nbsp;on Wednesday.]]></description>
      <media:content url="https://s.yimg.com/uu/api/res/1.2/abc/image.jpg" width="1200" height="800"/>
      <dc:creator xmlns:dc="http://purl.org/dc/elements/1.1/">Jane Analyst</dc:creator>
    </item>
    <item>
      <title>Fed holds rates steady as inflation cools to 4.1%</title>
      <link>https://duplicate.example.com/story</link>
      <pubDate>Thu, 02 Jul 2026 14:12:00 +0000</pubDate>
      <description>Same story, different feed.</description>
    </item>
    <item>
      <title></title>
      <link>https://example.com/malformed-no-title</link>
    </item>
  </channel>
</rss>`

const DOWJONES_STYLE_RSS = `<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>MarketWatch</title>
    <item>
      <title>Nvidia earnings beat estimates as data-center revenue doubles</title>
      <link>https://www.marketwatch.com/story/nvidia-earnings</link>
      <pubDate>Thu, 02 Jul 2026 13:00:00 GMT</pubDate>
      <description>Shares rose after hours. &lt;a href="x"&gt;Read more&lt;/a&gt;</description>
    </item>
  </channel>
</rss>`

const ATOM_FEED = `<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example Atom</title>
  <entry>
    <title>Bitcoin crosses $120,000 for the first time</title>
    <link rel="alternate" href="https://example.com/btc-120k"/>
    <published>2026-07-01T09:00:00Z</published>
    <summary>The largest cryptocurrency extended its rally.</summary>
    <author><name>Sam Reporter</name></author>
  </entry>
</feed>`

/* ---------- parseFeedXml ---------- */

test('parses RSS 2.0 with media:content, CDATA and entities', () => {
  const items = parseFeedXml(YAHOO_STYLE_RSS)
  // Malformed (empty-title) item dropped; duplicate kept here (dedupe happens in aggregate)
  assert.equal(items.length, 2)
  const first = items[0]
  assert.equal(first.title, 'Fed holds rates steady as inflation cools to 4.1%')
  assert.equal(first.url, 'https://finance.yahoo.com/news/fed-holds-rates.html')
  assert.equal(first.image, 'https://s.yimg.com/uu/api/res/1.2/abc/image.jpg')
  assert.equal(first.author, 'Jane Analyst')
  assert.match(first.summary, /unchanged on Wednesday/)
  assert.ok(!first.summary.includes('&nbsp;'), 'entities decoded')
  assert.ok(first.publishedAt.startsWith('2026-07-02T14:10'), 'pubDate normalized to ISO')
})

test('parses plain RSS without images and strips embedded HTML', () => {
  const items = parseFeedXml(DOWJONES_STYLE_RSS)
  assert.equal(items.length, 1)
  assert.equal(items[0].image, null)
  assert.ok(!items[0].summary.includes('<a'), 'tags stripped')
  assert.match(items[0].summary, /Shares rose after hours/)
})

test('parses Atom feeds', () => {
  const items = parseFeedXml(ATOM_FEED)
  assert.equal(items.length, 1)
  assert.equal(items[0].url, 'https://example.com/btc-120k')
  assert.equal(items[0].author, 'Sam Reporter')
})

test('malformed XML returns empty array, never throws', () => {
  assert.deepEqual(parseFeedXml('<not-xml'), [])
  assert.deepEqual(parseFeedXml(''), [])
  assert.deepEqual(parseFeedXml('<html><body>Rate limited</body></html>'), [])
})

/* ---------- cleanText ---------- */

test('cleanText strips tags, CDATA and collapses whitespace', () => {
  assert.equal(cleanText('<![CDATA[Hello   <b>world</b>&amp;co]]>'), 'Hello world &co')
})

/* ---------- classify ---------- */

test('classifier routes by keyword with correct precedence', () => {
  assert.equal(classify('Bitcoin ETF sees record inflows', '', null), 'crypto')
  assert.equal(classify('Fed signals rate cut in September', '', null), 'economy')
  assert.equal(classify('New AI chip from TSMC', '', null), 'technology')
  assert.equal(classify('Apple earnings top estimates', '', null), 'companies')
  assert.equal(classify('Stocks drift ahead of holiday weekend', '', null), 'markets')
  // Fallback respected when no rule matches
  assert.equal(classify('Quiet day on Wall Street', '', 'economy'), 'economy')
  // Crypto beats companies when both match
  assert.equal(classify('Coinbase earnings: crypto exchange beats', '', null), 'crypto')
})
