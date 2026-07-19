/* Session state helpers: snapshots, activity, and the autosave contract. */
import { strict as assert } from 'node:assert'
import test from 'node:test'
import { captureSnapshot, emptyWorkspaceState, recordActivity } from '../src/lib/sessions'

test('empty state is complete and versioned', () => {
  const state = emptyWorkspaceState()
  assert.equal(state.schema_version, 1)
  for (const key of ['symbols', 'pinned', 'hidden', 'snapshots', 'activity', 'collections', 'bookmarks']) {
    assert.ok(Array.isArray((state as unknown as Record<string, unknown>)[key]), key)
  }
  assert.equal(state.filters.hops, 2)
})

test('activity is append-only, newest last, and bounded', () => {
  let state = emptyWorkspaceState()
  for (let i = 0; i < 250; i++) state = recordActivity(state, 'open', `entity-${i}`)
  assert.equal(state.activity.length, 200)
  // The most RECENT entries survive — an investigation log, not a stub.
  assert.equal(state.activity[state.activity.length - 1].detail, 'entity-249')
})

test('activity entries are timestamped', () => {
  const state = recordActivity(emptyWorkspaceState(), 'pin', 'company:NVDA')
  assert.ok(!Number.isNaN(Date.parse(state.activity[0].at)))
  assert.equal(state.activity[0].action, 'pin')
})

test('snapshot captures the restorable view and logs itself', () => {
  const base = { ...emptyWorkspaceState(), symbols: ['NVDA'], pinned: ['company:NVDA'] }
  const state = captureSnapshot(base, 'Before earnings')
  assert.equal(state.snapshots.length, 1)
  const snap = state.snapshots[0]
  assert.equal(snap.label, 'Before earnings')
  assert.deepEqual(snap.state.symbols, ['NVDA'])
  assert.deepEqual(snap.state.pinned, ['company:NVDA'])
  // Taking a snapshot is itself an investigation event.
  assert.equal(state.activity.at(-1)?.action, 'snapshot')
})

test('snapshots are bounded and unlabelled ones still get a name', () => {
  let state = emptyWorkspaceState()
  for (let i = 0; i < 45; i++) state = captureSnapshot(state, `s${i}`)
  assert.equal(state.snapshots.length, 40)
  const unnamed = captureSnapshot(emptyWorkspaceState(), '   ')
  assert.equal(unnamed.snapshots[0].label, 'Snapshot')
})

test('state updates are immutable — the original is never mutated', () => {
  const original = emptyWorkspaceState()
  const next = recordActivity(original, 'open', 'x')
  assert.equal(original.activity.length, 0)
  assert.equal(next.activity.length, 1)
})
