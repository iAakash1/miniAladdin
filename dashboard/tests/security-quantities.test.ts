/* Percentages on the security page.

   The window-change figure was computed as a fraction and rendered with the
   `percent` kind. AAPL moved from 229.72 to 324.96 over a year — a gain of
   41.5% — and the page said "+0.4%". The number was correct arithmetic, the
   unit was wrong, and it looked entirely plausible.

   The `percent` kind never multiplies, on purpose: a formatter that scales
   cannot tell 0.61 from 61. So the conversion belongs at the one place that
   knows the value is a ratio, and these assert it happens there. */
import { strict as assert } from 'node:assert'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { format } from '../src/lib/quantity'
import { ownershipConflict, windowShortfall } from '../src/lib/security'
import { titleCase, venueLabel } from '../src/lib/text'

const VIEW = readFileSync(
  new URL('../src/components/terminal/security/SecurityView.tsx', import.meta.url), 'utf8',
)

test('a ratio is scaled before it is called a percentage', () => {
  assert.match(
    VIEW,
    /\(\(last\.close - first\.close\) \/ first\.close\) \* 100/,
    'window change is passed to the percent kind without being scaled',
  )
})

test('the arithmetic matches the year AAPL actually had', () => {
  const first = 229.72
  const last = 324.96
  const pct = ((last - first) / first) * 100
  assert.ok(pct > 41 && pct < 42, `expected roughly 41.5%, got ${pct}`)
  assert.match(format(pct, 'percent', { digits: 2 }).text, /^41\.4/)
  // The unscaled value is what shipped. It is not a rounding difference.
  assert.match(format((last - first) / first, 'percent', { digits: 2 }).text, /^0\.41/)
})

test('session changes keep two decimals', () => {
  // A −0.05% day rounds to −0.1% at one decimal, which overstates it twofold
  // and is the precision every quote screen gets right.
  assert.equal(format(-0.05, 'percent', { digits: 2 }).text, '-0.05')
  assert.equal(format(-0.05, 'percent', { digits: 1 }).text, '-0.1')
  // The instrument field renders both moves. The precision is the point, not
  // the markup — these pin the digits wherever the field puts them.
  assert.match(VIEW, /change_1d[^/]*digits=\{2\}/, 'the daily change is not at two decimals')
  assert.match(VIEW, /change_1w[^/]*digits=\{2\}/, 'the weekly change is not at two decimals')
})

test('price is currency, not a bare ratio', () => {
  // The last price is the largest figure on the page and the one most likely
  // to be read as a bare number. It goes through the currency kind so it
  // carries its unit and its precision rather than the ratio default.
  assert.match(VIEW, /format\(price\.price, 'currency'\)/)
})

/* Ownership blocks that cannot be true as stated.

   Alphabet returns a float of 10,879,563,400 against 5,867,155,790 shares
   outstanding — the float spans every share class while the count is for the
   listed one. Apple, Amazon, Microsoft and Tesla are all internally
   consistent, so the check has to stay quiet on them or it is noise. */
test('a float larger than the shares outstanding is reported', () => {
  const msg = ownershipConflict({ shares_outstanding: 5867155790, float_shares: 10879563400 })
  assert.ok(msg, 'the impossible pair passed without comment')
  assert.match(msg ?? '', /different bases/)
})

test('an ordinary ownership block says nothing', () => {
  // AAPL, AMZN, MSFT and TSLA as the vendor returned them.
  const real = [
    { shares_outstanding: 14594180000, float_shares: 14569223952 },
    { shares_outstanding: 10786313572, float_shares: 9810583646 },
    { shares_outstanding: 7425545491, float_shares: 7414481428 },
    { shares_outstanding: 3949547394, float_shares: 2819186930 },
  ]
  for (const o of real) assert.equal(ownershipConflict(o), null)
})

test('a float exactly equal to the shares outstanding is not a conflict', () => {
  assert.equal(ownershipConflict({ shares_outstanding: 1000, float_shares: 1000 }), null)
})

test('a missing figure is not a conflict', () => {
  assert.equal(ownershipConflict({ shares_outstanding: 1000 }), null)
  assert.equal(ownershipConflict({ float_shares: 1000 }), null)
  assert.equal(ownershipConflict({ shares_outstanding: null, float_shares: null }), null)
  assert.equal(ownershipConflict({}), null)
})

test('a non-finite figure is not treated as a comparison', () => {
  assert.equal(ownershipConflict({ shares_outstanding: NaN, float_shares: 10 }), null)
  assert.equal(ownershipConflict({ shares_outstanding: 10, float_shares: Infinity }), null)
})

/* A range control that names a window the data does not cover.

   Asking the chart for five years of AAPL returns 502 sessions — under two
   years — because the answering vendor's plan stops there. Every point drawn
   is correct; the control is what lies. */
test('a five-year request served with two years of history says so', () => {
  const msg = windowShortfall('5y', '2024-09-04', '2026-09-03')
  assert.ok(msg, 'a three-year gap went unreported')
  assert.match(msg ?? '', /2\.0 years/)
  assert.match(msg ?? '', /2024-09-04/)
})

test('a range the provider covers is not annotated', () => {
  // 1y as actually returned: 2025-09-03 to 2026-09-02.
  assert.equal(windowShortfall('1y', '2025-09-03', '2026-09-02'), null)
  // 3mo as actually returned.
  assert.equal(windowShortfall('3mo', '2026-06-04', '2026-09-02'), null)
  // 1mo, where a few missing calendar days are holidays, not a shortfall.
  assert.equal(windowShortfall('1mo', '2026-08-04', '2026-09-03'), null)
})

test('an unknown range makes no claim about coverage', () => {
  assert.equal(windowShortfall('max', '2026-06-04', '2026-09-03'), null)
})

test('an unusable pair of dates is not an assertion of shortfall', () => {
  assert.equal(windowShortfall('5y', null, '2026-09-03'), null)
  assert.equal(windowShortfall('5y', '2026-09-03', null), null)
  assert.equal(windowShortfall('5y', 'not a date', '2026-09-03'), null)
  // Reversed dates are a bug elsewhere, not a shortfall to announce here.
  assert.equal(windowShortfall('5y', '2026-09-03', '2024-09-04'), null)
})

/* Venue labels.

   The vendor returns the full market description — "NASDAQ NMS - GLOBAL
   MARKET" for Apple, "NEW YORK STOCK EXCHANGE" for Nike. Beside a ticker
   those are too long to scan, and set in capitals beside a title-cased name
   they shout. */
test('a market description condenses to the venue', () => {
  assert.equal(venueLabel('NASDAQ NMS - GLOBAL MARKET'), 'NASDAQ')
  assert.equal(venueLabel('NEW YORK STOCK EXCHANGE'), 'NYSE')
  assert.equal(venueLabel('NEW YORK STOCK EXCHANGE, INC.'), 'NYSE')
})

test('an unrecognised venue is passed through, never guessed at', () => {
  // Abbreviating this would be inventing a claim about where it lists.
  assert.equal(venueLabel('BOLSA MEXICANA DE VALORES'), 'BOLSA MEXICANA DE VALORES')
  assert.equal(venueLabel('SOME REGIONAL EXCHANGE'), 'SOME REGIONAL EXCHANGE')
})

test('a missing exchange yields nothing rather than a placeholder', () => {
  assert.equal(venueLabel(null), null)
  assert.equal(venueLabel(undefined), null)
  assert.equal(venueLabel('   '), null)
})

/* Company names arrive shouting and are set at 34px. */
test('a legal name in capitals is cased for display', () => {
  assert.equal(titleCase('APPLE INC'), 'Apple Inc.')
  assert.equal(titleCase('MICROSOFT CORP'), 'Microsoft Corp.')
})

test('a name the provider already cased is left alone', () => {
  // A provider that bothered to case its own name knows better than a rule.
  assert.equal(titleCase('Apple Inc.'), 'Apple Inc.')
  assert.equal(titleCase('lululemon athletica inc.'), 'lululemon athletica inc.')
})

test('stylings survive casing', () => {
  assert.equal(titleCase('AT&T INC'), 'AT&T Inc.')
  assert.equal(titleCase('3M CO'), '3M Co.')
})

/* Share classes.

   "APPLOVIN CORP-CLASS A" rendered as "Applovin Corp-Class a", because the
   minor-word list contains the article "a". In a search list whose whole
   purpose is telling two listings of one company apart, a lowercase class
   letter reads as a typo. */
test('a share-class letter is not the article "a"', () => {
  assert.equal(titleCase('APPLOVIN CORP-CLASS A'), 'Applovin Corp-Class A')
  assert.equal(titleCase('ALPHABET INC CLASS C'), 'Alphabet Inc Class C')
})

test('minor words inside a name still lowercase', () => {
  assert.equal(titleCase('THE HOME DEPOT INC'), 'The Home Depot Inc.')
  assert.equal(titleCase('BANK OF AMERICA CORP'), 'Bank of America Corp.')
})
