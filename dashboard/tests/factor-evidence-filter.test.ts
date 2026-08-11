/* Filtering the factor evidence.

   The property that matters is symmetry: the lab must be able to show what
   failed exactly as easily as what worked. A filter that only offers
   "significant" turns a research tool into a marketing page, so both
   predicates exist and `all` stays the default — nothing is hidden until
   the reader chooses to narrow. */
import { strict as assert } from 'node:assert'
import test from 'node:test'
import { filterEvidence } from '../src/components/terminal/FactorLabView'

const factors = [
  { factor: 'r12_1', significant: false },
  { factor: 'value', significant: true },
  { factor: 'quality', significant: false },
  { factor: 'news', significant: true },
]

const names = (list: Array<{ factor: string }>) => list.map((f) => f.factor)

test('"all" hides nothing and does not copy', () => {
  assert.equal(filterEvidence(factors, 'all'), factors)
})

test('significant and inconclusive are exact complements', () => {
  const yes = filterEvidence(factors, 'significant')
  const no = filterEvidence(factors, 'inconclusive')
  assert.deepEqual(names(yes), ['value', 'news'])
  assert.deepEqual(names(no), ['r12_1', 'quality'])
  assert.equal(yes.length + no.length, factors.length, 'every factor must land in exactly one bucket')
})

test('a sample where nothing cleared still reports the failures', () => {
  // The real mega30 result: no factor clears |t| 2 after the overlap
  // correction. The lab must still be able to show all eight.
  const none = factors.map((f) => ({ ...f, significant: false }))
  assert.equal(filterEvidence(none, 'significant').length, 0)
  assert.equal(filterEvidence(none, 'inconclusive').length, 4)
})

test('ordering is preserved so the t-stat ranking survives filtering', () => {
  assert.deepEqual(names(filterEvidence(factors, 'inconclusive')), ['r12_1', 'quality'])
})

test('an empty factor list is not an error', () => {
  assert.deepEqual(filterEvidence([], 'significant'), [])
})
