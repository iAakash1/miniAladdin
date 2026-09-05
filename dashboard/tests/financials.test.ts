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

/* The accounting identity, and why nothing is derived from these facts.

   Assets = Liabilities + Equity holds exactly in any filed balance sheet.
   Across the audited securities it fails — 51% of assets for NVDA FY2026,
   12% for MSFT, 4% for AAPL FY2023 — which means the concepts for a labelled
   year are not drawn from one reconciled context.

   That does not make any single fact wrong. It makes arithmetic across them
   invalid, and it is why this panel derives nothing. */
test('the balance identity is checked, not assumed', () => {
  assert.match(FIN, /Total liabilities/)
  assert.match(FIN, /Shareholders/)
  assert.match(FIN, /a - \(l \+ e\)/, 'the identity is not actually computed')
})

test('a failure is shown to the reader, not left in a document', () => {
  assert.match(FIN, /do not reconcile/i)
  assert.match(FIN, /do not compute across them/i)
})

test('presentation rounding is not reported as a reconciliation failure', () => {
  // A tenth of a per cent is rounding in a filing. Flagging it would train
  // the reader to ignore the warning.
  assert.match(FIN, /pct > 0\.1/)
})

test('nothing is derived from facts that fail the identity', () => {
  // The brief asked for derived metrics with declared formulas. The honest
  // answer here is that the inputs do not reconcile, so a derived figure
  // would be a wrong number carrying a citation.
  const code = FIN.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '')
  for (const derived of ['margin', 'freeCashFlow', 'fcf', 'growth', 'cagr', 'ratio']) {
    assert.doesNotMatch(code, new RegExp(`const ${derived}`, 'i'),
      `${derived} is being derived from facts that fail the balance identity`)
  }
})

test('a concept absent for one security is not rendered as zero', () => {
  // NVDA returns no Dividends paid. NVIDIA does pay one, so that is a tagging
  // gap — rendering it as zero would assert something false about the company.
  assert.match(FIN, /No fact for this year/)
  assert.doesNotMatch(FIN, /\?\?\s*0\b/, 'a missing fact falls back to zero somewhere')
})


/* ── the period a fact describes, not the year its filing carried ────────── */

test('the period end travels into the evidence chain', () => {
  /* EDGAR's `fy` is the filing's fiscal year, not the fact's period: Apple's
     FY2025 10-K supplies assets for 2025-09-27 and 2024-09-28 with `fy: 2025`
     on both. The column label is now derived from the period end, so the
     inspector must show the date the label stands for. */
  assert.match(FIN, /period_end\?: string/, 'the fact type carries no period end')
  assert.match(FIN, /period ending \$\{f\.period_end\}/,
    'the inspector still reports a fiscal year with no date behind it')
})

test('the XBRL tag is recorded on the fact', () => {
  // Filers change tags between years. Which tag a series came from is part of
  // what the number means, and the reason two tags are never unioned.
  assert.match(FIN, /concept_tag\?: string/, 'the fact type carries no tag')
  assert.match(FIN, /f\.concept_tag/, 'the tag never reaches the reader')
  assert.match(FIN, /definition would change partway down the column/,
    'the single-tag rule is not explained where it matters')
})

test('the reconciliation check is kept, not deleted', () => {
  /* It was firing for an upstream reason and that reason is fixed — but the
     check is what found the defect, and removing it now would mean the next
     one goes unseen. */
  assert.match(FIN, /Assets should equal liabilities plus equity/,
    'the accounting identity check was removed')
  assert.match(FIN, /unbalanced/, 'the identity result is no longer computed')
})

test('the panel no longer describes coverage gaps it caused itself', () => {
  // The doc comment cited Apple's single 2018 revenue fact as evidence that
  // filings are sparse. That was an adapter defect, not a filing one.
  assert.doesNotMatch(FIN, /exactly one Revenue fact/,
    'the panel still attributes its own former defect to the filings')
})
