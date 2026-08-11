/* Narrowing the rolling-IC window is how a reader separates "this never
   worked" from "this stopped working". The slice must always be the most
   recent points — taking from the front would answer the opposite question. */
import { strict as assert } from 'node:assert'
import test from 'node:test'
import { IC_WINDOWS, sliceIc } from '../src/components/terminal/ValidationCharts'

const series = Array.from({ length: 20 }, (_, i) => ({ date: `d${i}`, ic: i / 100 }))

test('keeps the most recent points, never the earliest', () => {
  const out = sliceIc(series, 'last12')
  assert.equal(out.length, 12)
  assert.equal(out[out.length - 1].date, 'd19', 'must end at the latest signal')
  assert.equal(out[0].date, 'd8')
})

test('a window wider than the series returns everything unchanged', () => {
  assert.equal(sliceIc(series, 'last26'), series, 'should not copy when nothing is dropped')
})

test('"all" never slices', () => {
  assert.equal(sliceIc(series, 'all'), series)
})

test('every declared window is honoured', () => {
  for (const w of IC_WINDOWS) {
    const out = sliceIc(series, w.id)
    const expected = Number.isFinite(w.keep) ? Math.min(w.keep, series.length) : series.length
    assert.equal(out.length, expected, `${w.id} produced ${out.length}`)
  }
})

test('an empty series stays empty rather than throwing', () => {
  assert.deepEqual(sliceIc([], 'last12'), [])
})
