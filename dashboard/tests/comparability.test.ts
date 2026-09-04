/* Comparing securities without pretending their years line up.

   This is not hypothetical. Asking the current providers for the latest filed
   Revenue gives fiscal 2018 for Apple, fiscal 2010 for Microsoft and fiscal
   2026 for NVIDIA. Put those in a row labelled "Revenue" and the table says
   NVIDIA earns twice what Microsoft does — wrong by roughly a factor of four,
   from cells that are each individually correct.

   Even with good coverage the years differ, because fiscal years do: Apple
   closes in September, Microsoft in June, NVIDIA in January. */
import { strict as assert } from 'node:assert'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

import { comparable, delta } from '../src/lib/semantics'

const ROOT = new URL('../src/', import.meta.url).pathname
const CMP = readFileSync(join(ROOT, 'components/terminal/compare/FiledComparison.tsx'), 'utf8')

test('different periods are a caveat, not a refusal', () => {
  // Refusing would withhold a useful comparison; showing it silently would
  // assert the years are the same. Neither is right.
  const fit = comparable(
    { kind: 'currency', period: 'FY2025' },
    { kind: 'currency', period: 'FY2024' },
  )
  assert.equal(fit.ok, true)
  assert.match(fit.caveat ?? '', /different periods/)
  assert.equal(fit.reason, undefined)
})

test('the same period carries no caveat', () => {
  const fit = comparable({ kind: 'currency', period: 'FY2025' }, { kind: 'currency', period: 'FY2025' })
  assert.equal(fit.ok, true)
  assert.equal(fit.caveat, undefined)
})

test('one side with no declared period is worse than two known ones', () => {
  const fit = comparable({ kind: 'currency', period: 'FY2025' }, { kind: 'currency' })
  assert.equal(fit.ok, true)
  assert.match(fit.caveat ?? '', /does not say which period/)
})

test('genuinely incompatible metrics are still refused outright', () => {
  // The caveat path must not become a way to compare anything with anything.
  const fit = comparable({ kind: 'percent' }, { kind: 'multiple' })
  assert.equal(fit.ok, false)
  assert.ok(fit.reason)
  assert.equal(fit.caveat, undefined)
})

test('a caveat survives the arithmetic', () => {
  // A period mismatch does not stop the subtraction; it changes what the
  // answer means, so it has to travel with the answer.
  const d = delta(96.99, 99.80, { kind: 'currency', period: 'FY2025' }, { kind: 'currency', period: 'FY2024' })
  assert.ok(d.value !== null, 'the difference was refused rather than annotated')
  assert.match(d.caveat ?? '', /FY2025 against FY2024/)
})

test('the fiscal year is rendered in the cell, never as a column header', () => {
  // A column header would assert a shared year that none of these securities
  // has. The year belongs to the observation.
  assert.match(CMP, /fcmp__fy/)
  assert.match(CMP, /a column header[,]? which would assert a shared year|header would assert a shared/i)
  assert.doesNotMatch(CMP, /<th[^>]*>FY\{/, 'a fiscal year is being used as a column header')
})

test('a missing fact is an em dash, never a zero or a carried value', () => {
  assert.match(CMP, /no filed fact returned/)
  assert.match(CMP, /sys-null/)
  assert.match(CMP, /not aligned, restated, interpolated or carried forward|Nothing here is aligned/)
})

test('the comparability judgement comes from the shared engine', () => {
  // A second opinion about what may be compared is how two surfaces end up
  // disagreeing about the same pair.
  assert.match(CMP, /comparable\(/)
  assert.match(CMP, /from '@\/lib\/semantics'/)
})

test('a wide year spread is marked more loudly than an adjacent one', () => {
  // FY2010 against FY2026 is not the same problem as FY2025 against FY2026.
  assert.match(CMP, /spread >= 3/)
  assert.match(CMP, /fcmp__warn/)
})
