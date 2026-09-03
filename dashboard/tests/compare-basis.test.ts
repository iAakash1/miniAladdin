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

test('a delta is only formed between subjects sharing a basis', () => {
  assert.match(
    COMPARE,
    /const commensurable\s*=[\s\S]*?s\.basis === baseline\.basis/,
    'the delta is not gated on a shared basis',
  )
  assert.match(
    COMPARE,
    /const delta = commensurable &&/,
    'a delta can still be computed across incompatible bases',
  )
})

test('an incomparable cell says so instead of showing a number', () => {
  assert.match(COMPARE, /not comparable with the baseline/, 'no incomparable state is rendered')
  // Stated once in the column header, not against every row.
  assert.match(COMPARE, /data-incomparable/, 'the incomparable column is not marked')
})

test('a better-or-worse verdict is withheld across bases', () => {
  // `o` drives the colour. It must fall back to 'same' — no green, no red —
  // when the two subjects are not on one scale.
  assert.match(
    COMPARE,
    /const o = isBase \|\| !commensurable \? 'same'/,
    'a better/worse verdict is still claimed across incompatible bases',
  )
})

test('the model comparison uses the prediction target as its basis', () => {
  assert.match(
    MODEL_COMPARE,
    /basis:\s*r\.label/,
    'model subjects do not declare their prediction target as the basis',
  )
})
