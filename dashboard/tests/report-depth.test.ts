/* Explanation depth is a reader preference with a safe default. */
import { strict as assert } from 'node:assert'
import test from 'node:test'

import { DEFAULT_DEPTH, DEPTHS, isDepth, storedDepth } from '../src/lib/report-depth'

test('the three depths are offered in order, intermediate by default', () => {
  assert.deepEqual(DEPTHS.map((d) => d.key), ['beginner', 'intermediate', 'advanced'])
  assert.equal(DEFAULT_DEPTH, 'intermediate')
})

test('an unknown depth is not a depth', () => {
  assert.equal(isDepth('advanced'), true)
  assert.equal(isDepth('expert'), false)
  assert.equal(isDepth(undefined), false)
})

test('without browser storage the default depth is used', () => {
  assert.equal(storedDepth(), 'intermediate')
})
