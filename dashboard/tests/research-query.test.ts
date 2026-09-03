/* Reading a search box as a research question.

   "HGB" is a name. "blocked models" is a question, and answering it with a
   fuzzy match against the string "blocked models" finds nothing, because no
   object is called that.

   Kind and state are the two vocabularies every object already carries, so a
   query naming either can be answered exactly. These assert that — and that
   nothing beyond them is invented, because a search box appearing to
   understand more than its index holds fails silently on exactly the queries a
   researcher would most want to trust. */
import { strict as assert } from 'node:assert'
import test from 'node:test'

import { describeQuery, matchesStructure, parseQuery } from '../src/lib/research/query'
import type { ResearchObject } from '../src/lib/research/objects'

const obj = (kind: string, id: string, state?: string): ResearchObject =>
  ({ kind, id, label: id, state } as ResearchObject)

test('a bare name stays a name', () => {
  const q = parseQuery('HGB')
  assert.deepEqual(q.kinds, [])
  assert.deepEqual(q.states, [])
  assert.equal(q.text, 'hgb')
  assert.equal(q.structural, false)
})

test('a kind word is recognised, singular or plural', () => {
  for (const word of ['model', 'models', 'experiment', 'experiments', 'datasets']) {
    const q = parseQuery(word)
    assert.ok(q.kinds.length === 1, `${word} did not resolve to a kind`)
    assert.equal(q.structural, true)
  }
})

test('a state word is recognised', () => {
  const q = parseQuery('blocked')
  assert.deepEqual(q.states, ['blocked'])
  assert.equal(q.structural, true)
})

test('a state and a kind together filter on both', () => {
  const q = parseQuery('blocked models')
  assert.deepEqual(q.states, ['blocked'])
  assert.equal(q.kinds.length, 1)
  assert.equal(q.text, '')

  assert.equal(matchesStructure(obj('model', 'hgb', 'blocked'), q), true)
  assert.equal(matchesStructure(obj('model', 'rf', 'experimental'), q), false, 'wrong state')
  assert.equal(matchesStructure(obj('dataset', 'ohlcv', 'blocked'), q), false, 'wrong kind')
})

test('two states mean either, which is what a reader typing both means', () => {
  const q = parseQuery('blocked stale models')
  assert.deepEqual(q.states.sort(), ['blocked', 'stale'])
  assert.equal(matchesStructure(obj('model', 'a', 'blocked'), q), true)
  assert.equal(matchesStructure(obj('model', 'b', 'stale'), q), true)
  assert.equal(matchesStructure(obj('model', 'c', 'production'), q), false)
})

test('a name beside a kind keeps the name for ranking', () => {
  const q = parseQuery('gradient models')
  assert.equal(q.kinds.length, 1)
  assert.equal(q.text, 'gradient')
  assert.equal(q.structural, false, 'there is still text to rank on')
})

test('an object with no state fails a state filter rather than passing it', () => {
  // A missing state is not a match. Treating absence as "any" would surface
  // unstated objects under every state query, which is the search-box version
  // of counting an unmeasured gate as passed.
  const q = parseQuery('blocked')
  assert.equal(matchesStructure(obj('model', 'a'), q), false)
})

test('the filter describes itself for the reader', () => {
  assert.equal(describeQuery(parseQuery('HGB')), null, 'a plain name needs no description')
  const d = describeQuery(parseQuery('blocked models'))
  assert.match(d ?? '', /blocked/)
  assert.match(d ?? '', /models/)
})

test('an unrecognised word is never silently dropped', () => {
  // It stays in the text, where it narrows results by name. Discarding it
  // would widen the result set beyond what was asked for.
  const q = parseQuery('blocked frobnicator')
  assert.deepEqual(q.states, ['blocked'])
  assert.equal(q.text, 'frobnicator')
})

test('a state word the registry uses is understood, not just the ones the UI renders', () => {
  // Models arrive as "experimental" and "retired" — the registry's vocabulary.
  // Neither is a render state, and a hardcoded list understood neither.
  const q = parseQuery('retired models', ['experimental', 'retired'])
  assert.deepEqual(q.states, ['retired'])
  assert.equal(q.structural, true)
  assert.equal(matchesStructure(obj('model', 'gb', 'retired'), q), true)
  assert.equal(matchesStructure(obj('model', 'rf', 'experimental'), q), false)
})

test('a render state is understood even when nothing currently holds it', () => {
  // "blocked models" with nothing blocked should return nothing — an answer.
  // Falling through to a name match on "blocked" would return an arbitrary set
  // and look like one.
  const q = parseQuery('blocked models', ['experimental', 'retired'])
  assert.deepEqual(q.states, ['blocked'])
  assert.equal(q.text, '', 'the word must not leak into name matching')
  assert.equal(matchesStructure(obj('model', 'gb', 'retired'), q), false)
})
