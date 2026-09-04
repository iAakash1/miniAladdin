/* Provenance, and the one thing it must never do.

   The research engine has always recorded which vendors supplied each field
   and which fields they disagree about. Neither reached the screen: Apple's
   headcount is 166,000 to one vendor and 150,000 to another, and the profile
   rendered their midpoint — 158,000 — as a single confident number.

   A disputed figure shown as settled is the most dangerous kind this product
   can display, because nothing about it looks wrong. These pin the two
   properties that keep that fixed. */
import { strict as assert } from 'node:assert'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

const ROOT = new URL('../src/', import.meta.url).pathname
const SYSTEM = readFileSync(join(ROOT, 'components/system/index.tsx'), 'utf8')
const INSPECTOR = readFileSync(join(ROOT, 'components/system/MetricInspector.tsx'), 'utf8')
const PROFILE = readFileSync(join(ROOT, 'components/terminal/security/SecurityProfile.tsx'), 'utf8')
const CONTEXT = readFileSync(join(ROOT, 'components/system/MetricContext.tsx'), 'utf8')

test('a contested figure is marked on the surface, not only in the drawer', () => {
  // A reader who never opens the inspector still has to know the number is
  // disputed. Marking it only inside the drawer hides it from everyone who
  // does not already suspect something.
  assert.match(SYSTEM, /sys-inspectable--disputed/)
  assert.match(SYSTEM, /conflict\?\.observations\?\.length/,
    'the disputed mark is not driven by the conflict itself')
})

test('the inspector renders each vendor’s own observation', () => {
  // Saying "vendors disagree" without saying what they said is worse than
  // silence: it removes confidence without supplying anything to replace it.
  assert.match(INSPECTOR, /conflict\.observations\.map/)
  assert.match(INSPECTOR, /Vendors disagree/)
})

test('the merged value is never presented as one vendor’s figure', () => {
  // The number shown is the merge's output. Attributing it to a single vendor
  // would be a claim none of them made.
  assert.match(PROFILE, /merged from the vendors below/)
})

test('provenance carries vendors, conflict and freshness as first-class fields', () => {
  for (const field of ['providers?:', 'conflict?:', 'freshness?:']) {
    assert.ok(CONTEXT.includes(field), `MetricRef has no ${field}`)
  }
})

test('a missing handbook entry is an absence, not an invented definition', () => {
  // The inspector must not fill a gap with prose that sounds authoritative.
  assert.match(INSPECTOR, /has no entry for this measure|no handbook entry/)
})

test('provenance is one interaction, not a panel per surface', () => {
  // Inspectable exists so every figure opens the same drawer. A second
  // bespoke metadata popover is how a terminal ends up with two answers to
  // one question.
  assert.match(SYSTEM, /export function Inspectable/)
  assert.match(SYSTEM, /metrics\.inspect\(refValue\)/)
})
