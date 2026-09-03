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
  assert.match(VIEW, /change_1d[^}]*digits: 2/, 'the daily change is not at two decimals')
  assert.match(VIEW, /change_1w[^}]*digits: 2/, 'the weekly change is not at two decimals')
})

test('price is currency, not a bare ratio', () => {
  assert.match(VIEW, /label: 'Last', value: price\?\.price \?\? null, kind: 'currency'/)
})
