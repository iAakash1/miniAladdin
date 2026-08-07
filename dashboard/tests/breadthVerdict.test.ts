import assert from 'node:assert/strict'
import test from 'node:test'
import { readScore } from '../src/components/terminal/BreadthHeatmap'

/* The score is a number; readScore is what turns it into a conclusion. It is
   the only real logic in the breadth panel, so it is the part worth pinning. */

test('a wide rally reads as broad participation', () => {
  const v = readScore(91, 10, 11)
  assert.equal(v.headline, 'Broad participation')
  assert.equal(v.tone, 'pos')
})

test('a collapse reads as broad weakness', () => {
  assert.equal(readScore(9, 1, 11).headline, 'Broad weakness')
  assert.equal(readScore(9, 1, 11).tone, 'neg')
})

test('a split market reads as mixed rather than healthy', () => {
  const v = readScore(45, 5, 11)
  assert.equal(v.headline, 'Mixed')
  assert.equal(v.tone, 'neutral')
})

test('narrowing is caught even when the headline score looks strong', () => {
  // 82% hold their 50-day average, but only 27% are positive over 21 days:
  // the trend read is stale and leadership is thinning. A score-only panel
  // would call this healthy.
  const v = readScore(82, 3, 11)
  assert.equal(v.headline, 'Narrowing')
  assert.equal(v.tone, 'warn')
  assert.match(v.detail, /thinning/)
})

test('narrowing does not fire when short and medium term agree', () => {
  assert.equal(readScore(82, 9, 11).headline, 'Broad participation')
})

test('a missing score is reported as unavailable, never as zero', () => {
  const v = readScore(null, 0, 0)
  assert.equal(v.headline, 'Unavailable')
  assert.equal(v.tone, 'neutral')
})

test('an empty sector list does not divide by zero', () => {
  assert.doesNotThrow(() => readScore(50, 0, 0))
})
