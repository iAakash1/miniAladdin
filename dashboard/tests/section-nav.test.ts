/* Which report section the nav highlights while reading.

   The rule is "the last section whose top has crossed the reading line",
   not "the most visible section". Ranking by visible area sounds more
   natural and is wrong: the report has sections from 150px to 900px tall,
   so the tallest one wins far past the point where the reader has moved on,
   and the highlight jumps backwards. */
import { strict as assert } from 'node:assert'
import test from 'node:test'
import { currentSectionId } from '../src/components/terminal/CompanyReport'

const LINE = 300

test('highlights the section whose top most recently passed the line', () => {
  // overview scrolled well past, scorecard just above the line, price below.
  assert.equal(currentSectionId([
    { id: 'overview', top: -900 },
    { id: 'scorecard', top: 120 },
    { id: 'price', top: 940 },
  ], LINE), 'scorecard')
})

test('before any section reaches the line, the first stays current', () => {
  assert.equal(currentSectionId([
    { id: 'overview', top: 420 },
    { id: 'report', top: 1100 },
  ], LINE), 'overview')
})

test('a tall section does not keep the highlight once the next one passes', () => {
  // `technical` is 900px tall and still occupies most of the viewport, but
  // `street` has crossed the line — the reader is in `street`.
  assert.equal(currentSectionId([
    { id: 'technical', top: -840 },
    { id: 'street', top: 60 },
  ], LINE), 'street')
})

test('at the bottom of the page the last section wins', () => {
  assert.equal(currentSectionId([
    { id: 'ecosystem', top: -600 },
    { id: 'related', top: -120 },
  ], LINE), 'related')
})

test('exactly on the line counts as reached', () => {
  assert.equal(currentSectionId([
    { id: 'a', top: -100 },
    { id: 'b', top: LINE },
  ], LINE), 'b')
})

test('an empty section list has no current section', () => {
  assert.equal(currentSectionId([], LINE), null)
})
