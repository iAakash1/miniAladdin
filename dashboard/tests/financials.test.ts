/* Filed financials, and the trap in the data.

   Coverage is uneven and the gaps are large. Apple has six fiscal years of
   net income, total assets and shareholders' equity — and exactly one Revenue
   fact, from fiscal 2018, and one Dividends paid fact from 2017.

   A sheet that printed "Revenue $215.64B" beside "Net income $96.99B" would
   be showing figures seven years apart as one year's business, and nothing on
   screen would say so. These pin the properties that make that impossible. */
import { strict as assert } from 'node:assert'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

const ROOT = new URL('../src/', import.meta.url).pathname
const FIN = readFileSync(join(ROOT, 'components/terminal/security/Financials.tsx'), 'utf8')

test('the fiscal year is a column, not a caption', () => {
  // A bare value with the year in a footnote is the shape that lets a 2018
  // figure sit under a 2025 heading.
  assert.match(FIN, /FY\{y\}/, 'years are not rendered as column headers')
})

test('a year with no fact renders an em dash, never a carried value', () => {
  assert.match(FIN, /No fact for this year/)
  assert.match(FIN, /sys-null/)
  // The guard must cover a missing fact *and* a non-numeric one.
  assert.match(FIN, /!f \|\| typeof f\.value !== 'number'/)
})

test('a concept whose latest filing is behind the others says so', () => {
  assert.match(FIN, /latest FY\{newest\}/)
  assert.match(FIN, /newest < latestYear/)
})

test('columns come from the facts, not from a year range', () => {
  // Generating a range would invent columns nobody filed for.
  assert.match(FIN, /present\.flatMap/)
  assert.doesNotMatch(FIN, /for \(let y = /, 'years appear to be generated rather than observed')
})

test('filed facts are not mixed with derived ratios', () => {
  // The ratio surface is computed by a vendor on a different basis. One grid
  // holding both makes it impossible to say which a number is.
  assert.match(FIN, /not mixed in here|deliberately not mixed/)
  for (const derived of ['margin', 'growth', 'CAGR', 'yield']) {
    assert.doesNotMatch(
      FIN.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, ''),
      new RegExp(`concepts: \\[[^\\]]*${derived}`, 'i'),
      `${derived} appears as a filed concept`,
    )
  }
})

test('a filed date is not a retrieval date', () => {
  // A 2018 filing date under the word "Retrieved" claims this product read it
  // in 2018. It did not; the company filed it then.
  assert.match(FIN, /filedAt: f\.filed/)
  assert.doesNotMatch(FIN, /retrievedAt: f\.filed/)
})

test('the drawer shows the figure the way the cell does', () => {
  // 215639000000 in the drawer where the cell reads 215.64B looks like a
  // different number.
  assert.match(FIN, /display: format\(f\.value, 'currency'/)
})

test('no facts is an absence, not an assertion that none were filed', () => {
  assert.match(FIN, /not a statement that the company filed nothing/)
})
