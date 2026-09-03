/* A comparison must refuse quantities that are not on the same scale.

   The registry holds models trained against fwd_rank_21 and against
   fwd_ret_21. Both record a field called mean_ic. Both are dimensionless. One
   is a rank correlation against a 21-session cross-sectional rank; the other is
   a correlation with a return.

   Subtracting one from the other produces a number with no meaning — which the
   comparison would nonetheless have painted green whenever it came out
   positive. These assert the rule that stops it. */
import { strict as assert } from 'node:assert'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const COMPARE = readFileSync(
  new URL('../src/components/system/Compare.tsx', import.meta.url), 'utf8',
)
const MODEL_COMPARE = readFileSync(
  new URL('../src/components/terminal/compare/ModelCompare.tsx', import.meta.url), 'utf8',
)

test('a subject can declare what its numbers are measured against', () => {
  assert.match(COMPARE, /basis\?:\s*string/, 'CompareSubject has no basis')
})

test('the comparison delegates the rule rather than reimplementing it', () => {
  // It used to carry its own direction table and its own subtraction, so a
  // metric's direction was a property of the screen rather than of the metric.
  // Both now come from the semantic layer, which is what stops one workspace
  // calling a rising drawdown an improvement while another calls it a
  // regression.
  assert.match(COMPARE, /from '@\/lib\/semantics'/, 'the comparison does not use the semantic layer')
  assert.match(COMPARE, /delta\(v, base, self, against\)/, 'the difference is not computed semantically')
  assert.match(
    COMPARE,
    /const commensurable = diff === null \|\| diff\.interpretation !== 'incomparable'/,
    'comparability is decided somewhere other than the semantic layer',
  )
})

test('the basis travels into the comparability decision', () => {
  // Same kind, different prediction target, still incomparable.
  assert.match(COMPARE, /basis: s\.basis/, 'the subject basis is not passed to the delta')
  assert.match(COMPARE, /basis: baseline\.basis/, 'the baseline basis is not passed to the delta')
})

test('an incomparable cell says so instead of showing a number', () => {
  assert.match(COMPARE, /not comparable with the baseline/, 'no incomparable state is rendered')
  // Stated once in the column header, not against every row.
  assert.match(COMPARE, /data-incomparable/, 'the incomparable column is not marked')
})

test('a better-or-worse verdict is withheld across bases', () => {
  // The outcome helper returns 'incomparable' straight from the semantic
  // layer's own verdict, so no colour is claimed across incompatible scales.
  assert.match(
    COMPARE,
    /if \(d\.interpretation === 'incomparable'\) return 'incomparable'/,
    'a better/worse verdict can still be claimed across incompatible bases',
  )
})

test('the model comparison uses the prediction target as its basis', () => {
  assert.match(
    MODEL_COMPARE,
    /basis:\s*r\.label/,
    'model subjects do not declare their prediction target as the basis',
  )
})
