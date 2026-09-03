import assert from 'node:assert/strict'
import { test } from 'node:test'

import { bounds, commit, resolve, MIN_SPAN } from '../src/lib/chart-window'

test('a window is discarded when the series shortens under it', () => {
  // The reader selected observations 40..60 of a 200-point series. The series
  // reloaded with 50 points. Indices 40..60 now mean something else entirely.
  assert.equal(resolve({ from: 40, to: 60 }, 50), null)
  assert.deepEqual(bounds({ from: 40, to: 60 }, 50), { from: 0, to: 49 })
})

test('a window that still fits is kept', () => {
  assert.deepEqual(resolve({ from: 40, to: 60 }, 200), { from: 40, to: 60 })
  assert.deepEqual(bounds({ from: 40, to: 60 }, 200), { from: 40, to: 60 })
})

test('a window spanning the whole series is not a window', () => {
  // Otherwise the chart would announce itself as windowed while showing
  // everything, and the disclosure would start reading as noise.
  assert.equal(resolve({ from: 0, to: 99 }, 100), null)
})

test('inverted and negative windows are refused', () => {
  assert.equal(resolve({ from: 60, to: 40 }, 200), null)
  assert.equal(resolve({ from: -1, to: 40 }, 200), null)
})

test('a drag shorter than the minimum span is not a selection', () => {
  assert.equal(commit({ from: 10, to: 10 }, 0, 200), null)
  assert.equal(commit({ from: 10, to: 10 + MIN_SPAN - 1 }, 0, 200), null)
  assert.deepEqual(commit({ from: 10, to: 10 + MIN_SPAN }, 0, 200), { from: 10, to: 12 })
})

test('a drag inside an existing window resolves against the full series', () => {
  // Visible window is 100..199. The reader drags across its first ten points.
  // That is 100..110 of the full series, not 0..10.
  assert.deepEqual(commit({ from: 0, to: 10 }, 100, 300), { from: 100, to: 110 })
})

test('a drag is refused when it would fall outside the series', () => {
  assert.equal(commit({ from: 0, to: 10 }, 295, 300), null)
})

test('an empty series has no window', () => {
  assert.equal(resolve({ from: 0, to: 5 }, 0), null)
  assert.deepEqual(bounds(null, 0), { from: 0, to: 0 })
})
