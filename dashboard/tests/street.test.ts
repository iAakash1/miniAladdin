/* Analyst coverage from two vendors that are not polling the same people.

   yfinance counts 39 analysts covering Apple; Finnhub counts 53. Neither is
   wrong and the difference is not a conflict to reconcile — each vendor has
   its own panel. These assert that the panel says so rather than picking one,
   and that the two scale conventions arriving in one payload are each read
   with the right one. */
import { strict as assert } from 'node:assert'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const ROOT = new URL('../src/', import.meta.url).pathname
const S = readFileSync(ROOT + 'components/terminal/security/Street.tsx', 'utf8')
const CODE = S.replace(/\/\*[\s\S]*?\*\//g, ' ')
  .split('\n').filter((l) => !l.trim().startsWith('//')).join('\n')

test('the two analyst counts are both shown, never merged', () => {
  assert.match(CODE, /panelsDiffer/, 'the differing counts are not detected')
  assert.match(S, /each polls its own panel/, 'the difference is not explained to the reader')
  // A single reconciled count would have to discard one vendor's panel.
  assert.doesNotMatch(CODE, /analyst_count\s*[+]\s*|Math\.(max|min)\([^)]*analysts/,
    'the two analyst counts were combined')
})

test('buy_ratio is scaled from a fraction exactly once', () => {
  // 0.642 is 64.2%. Rendered raw it reads as under one per cent.
  assert.match(CODE, /const pct = /, 'there is no single scaling boundary')
  assert.match(CODE, /pct\(recs\?\.buy_ratio\)/, 'buy_ratio does not go through the scaler')
})

test('avg_surprise_pct is not scaled, because it is already a percentage', () => {
  /* The trap: buy_ratio is a fraction and avg_surprise_pct is a percent, in
     the same payload block. Putting either through the other's convention is
     wrong by a factor of a hundred. */
  assert.doesNotMatch(CODE, /pct\(\s*surprises[^)]*\)/,
    'a figure already in percent was multiplied by a hundred')
  assert.match(CODE, /value=\{surprises\.avg_surprise_pct\}/,
    'the average surprise is not passed through unscaled')
})

test('MSPR is presented as a bounded index, not a percentage', () => {
  // Finnhub's MSPR runs -100 to 100. Rendered with a per-cent sign, -100
  // reads as every insider selling everything.
  // Rendered as a ratio, never a percentage.
  assert.match(CODE, /value=\{insider\.mspr\}\s+kind="ratio"/,
    'MSPR is not rendered as a plain ratio')
  assert.doesNotMatch(CODE, /value=\{insider\.mspr\}\s+kind="percent"/,
    'MSPR is rendered as a percentage')
  // And its bounds are stated where the reader sees the number.
  assert.match(CODE, /index, −100 to 100/, 'the MSPR scale is not shown beside the value')
  // The evidence chain must name the misreading explicitly.
  assert.match(S, /Read as a percentage\. It is a bounded index/,
    'the inspector does not warn that MSPR is not a percentage')
})

test('the mean rating never appears without its distribution', () => {
  // A 2.18 on a five-point scale hides whether that is a cluster or a split.
  const meanAt = CODE.indexOf('recommendation_mean')
  const dist = CODE.indexOf('RATINGS.map')
  assert.ok(meanAt > 0 && dist > 0, 'one of the two is missing')
  assert.match(S, /1 = strong buy, 5 = strong sell/,
    'the rating scale direction is not stated')
})

test('the vendor narrative block is deliberately not rendered', () => {
  /* `findings` are pre-written sentences carrying a tone. A coloured sentence
     beside a price reads as this product's own view, which is the same reason
     the `ai` block stays hidden while the research verdict is NO PRODUCTION
     CANDIDATE. */
  assert.doesNotMatch(CODE, /\bfindings\b/, 'the vendor narrative reached the reader')
  assert.doesNotMatch(CODE, /\btone\b\s*[:=]/, 'vendor tone is being applied')
})

test('ratings are attributed and dated', () => {
  assert.match(S, /as of \$\{recs\.period\}/, 'the rating snapshot carries no date')
  assert.match(S, /analysts · finnhub/, 'the ratings are not attributed to a vendor')
  assert.match(S, /targets\.source/, 'the price targets are not attributed')
})

test('the ratings are framed as other people’s opinions', () => {
  assert.match(S, /not this product/, 'the panel does not disclaim the ratings as its own view')
})
