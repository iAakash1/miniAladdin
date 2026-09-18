/* familyLine: the deterministic template behind "Since your last analysis".
   Never invents a contributor and never asserts a direction the number does
   not support — "contributed more/less" is true regardless of which side of
   zero the family started on, unlike "improved/worsened" would be. */
import { strict as assert } from 'node:assert'
import test from 'node:test'

import { familyLine } from '../src/components/research/ResearchHistory'

test('a positive delta reads as contributing more', () => {
  assert.equal(
    familyLine({ label: 'Momentum', before: -0.05, after: 0.05, delta: 0.10 }),
    'Momentum contributed more to the score.',
  )
})

test('a negative delta reads as contributing less, even from a negative base', () => {
  // The case the "improved/worsened" phrasing would get backwards: the
  // family was already negative and became more negative. The number moved
  // down (contributed less); calling that "worse" would be an opinion this
  // function does not have grounds to state.
  assert.equal(
    familyLine({ label: 'Value', before: -0.10, after: -0.25, delta: -0.15 }),
    'Value contributed less to the score.',
  )
})

test('a family that newly appears is reported as newly measured, not as a delta', () => {
  assert.equal(
    familyLine({ label: 'News', before: null, after: 0.08, delta: 0.08 }),
    'News is now measured.',
  )
})

test('a family that drops out is reported as unmeasured, not as a zero delta', () => {
  assert.equal(
    familyLine({ label: 'News', before: 0.08, after: null, delta: -0.08 }),
    'News could not be measured this time.',
  )
})

test('a zero delta is not reached by this function in practice, but resolves without throwing', () => {
  // The component only calls this for entries compare() marked `changed`, so
  // delta is never exactly 0 in production — but the function itself must not
  // throw or misreport if it ever is.
  assert.equal(
    familyLine({ label: 'Quality', before: 0.10, after: 0.10, delta: 0 }),
    'Quality contributed less to the score.',
  )
})
