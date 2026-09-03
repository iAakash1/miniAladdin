/* Telling what is true now from what was true last time anyone looked.

   The status rail shipped a version that kept announcing HOLDOUT SEALED and
   REGISTRY 103 ENTRIES while the backend was unreachable. Both had been true
   an hour earlier; neither was known when displayed. The rail is the
   reassuring strip that is always in view, which makes it the last thing a
   reader would think to doubt.

   Showing nothing is honest and wasteful — a reader who has just lost the
   backend usually still wants its last word, provided the screen says that is
   what it is doing. These assert the distinction that makes that safe. */
import { strict as assert } from 'node:assert'
import test from 'node:test'

import { ageMinutes, failed, isCurrent, notRecorded, observed, staleNote } from '../src/lib/observation'

test('a successful read is current', () => {
  const o = observed({ entries: 103 }, '2026-09-03T11:27:12Z')
  assert.equal(o.state, 'observed')
  assert.equal(isCurrent(o), true)
  assert.equal(staleNote(o, (v) => `${v.entries}`), null, 'a current value needs no caveat')
})

test('a failure with nothing behind it invents no value', () => {
  const o = failed(null, 'the status request returned 500')
  assert.equal(o.state, 'unavailable')
  assert.equal(o.value, null)
  assert.equal(o.at, null)
  assert.equal(isCurrent(o), false)
})

test('a failure after a success keeps the value and stops calling it current', () => {
  const before = observed({ entries: 103 }, '2026-09-03T11:27:12Z')
  const after = failed(before, 'connection refused')
  assert.equal(after.state, 'last-observed')
  assert.deepEqual(after.value, { entries: 103 })
  assert.equal(isCurrent(after), false, 'a remembered value must not read as current')
})

test('a remembered value keeps the time it was read, not the time of the failure', () => {
  // Timestamping the failure would make a stale reading look fresh, which is
  // the failure mode this module exists to prevent.
  const before = observed({ entries: 103 }, '2026-09-03T11:27:12Z')
  const after = failed(before, 'connection refused')
  assert.equal(after.at, '2026-09-03T11:27:12Z')
})

test('a remembered value is always introduced as remembered', () => {
  const after = failed(observed({ entries: 103 }, '2026-09-03T11:27:12Z'), 'down')
  const note = staleNote(after, (v) => `${v.entries} entries`)
  assert.match(note ?? '', /last seen/, 'the phrase is what stops it reading as live')
  assert.match(note ?? '', /103 entries/)
  assert.match(note ?? '', /2026-09-03 11:27:12/, 'a remembered value must carry its time')
})

test('recovery returns to current and drops the caveat', () => {
  const down = failed(observed({ entries: 103 }, '2026-09-03T11:27:12Z'), 'down')
  assert.equal(down.state, 'last-observed')
  const back = observed({ entries: 104 }, '2026-09-03T11:31:00Z')
  assert.equal(back.state, 'observed')
  assert.equal(staleNote(back, (v) => `${v.entries}`), null)
})

test('a source reporting no value is not a source that could not be read', () => {
  const n = notRecorded<{ entries: number }>('2026-09-03T11:27:12Z')
  assert.equal(n.state, 'not-recorded')
  assert.equal(n.value, null)
  // It was read. That is the difference from `unavailable`, and it decides
  // whether the work is to fix a connection or to run a measurement.
  assert.notEqual(n.at, null)
  assert.notEqual(n.state, 'unavailable')
})

test('age is measured from the observation, and absent when there is none', () => {
  const at = '2026-09-03T11:00:00Z'
  const o = observed({ x: 1 }, at)
  assert.equal(ageMinutes(o, Date.parse('2026-09-03T11:45:00Z')), 45)
  assert.equal(ageMinutes(failed(null, 'down')), null)
})
