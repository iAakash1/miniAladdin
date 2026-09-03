/* The palette paints headers and rows in one column but selects with a single
   flat index. If the painted order and the index disagree the surface breaks
   quietly: the highlighted row and the row Enter opens are different rows.

   That is not hypothetical. An earlier palette counted during render with a
   trailing `+ 1`, so option ids ran 1..N while the cursor ran 0..N-1 — nothing
   highlighted on open, one arrow press highlighted one row while Enter opened
   the next, and the last result could never be reached.

   These assert the invariant that makes the listbox coherent: the indices this
   produces are exactly 0..N-1 in render order, headers carry none, and a header
   never appears without rows under it. */
import { strict as assert } from 'node:assert'
import test from 'node:test'

import { buildRows, selectableRows } from '../src/lib/palette-rows'

interface Obj { kind: string; id: string }

const obj = (kind: string, id: string): Obj => ({ kind, id })

const build = (over: Partial<Parameters<typeof buildRows<string, Obj>>[0]> = {}) =>
  buildRows<string, Obj>({
    commands: [],
    commandKey: (c) => c,
    groups: [],
    objectKey: (o) => `${o.kind}:${o.id}`,
    showSuggestions: false,
    ...over,
  })

test('indices are exactly 0..N-1 in paint order', () => {
  const rows = build({
    commands: ['a', 'b'],
    groups: [
      { key: 'factor', label: 'Factors', items: [obj('factor', 'r12'), obj('factor', 'value')] },
      { key: 'model', label: 'Models', items: [obj('model', 'hgb')] },
    ],
  })
  const indices = selectableRows(rows).map((r) => r.index)
  assert.deepEqual(indices, [0, 1, 2, 3, 4])
})

test('paint order and index order are the same order', () => {
  const rows = build({
    commands: ['only'],
    groups: [{ key: 'model', label: 'Models', items: [obj('model', 'hgb')] }],
  })
  // Walking the painted list and skipping headers must recover the indices in
  // ascending order. Anything else means the cursor and the eye disagree.
  let expected = 0
  for (const row of rows) {
    if (row.type === 'header') continue
    assert.equal(row.index, expected, 'painted order does not match index order')
    expected += 1
  }
})

test('headers carry no index and never appear empty', () => {
  const rows = build({
    commands: ['a'],
    groups: [
      { key: 'factor', label: 'Factors', items: [] },
      { key: 'model', label: 'Models', items: [obj('model', 'hgb')] },
    ],
  })
  const headers = rows.filter((r) => r.type === 'header')
  assert.deepEqual(headers.map((h) => h.label), ['Commands', 'Models'])
  for (const h of headers) assert.ok(!('index' in h))
})

test('suggestions appear only when there is no query', () => {
  const pinned = { label: 'Pinned', keyPrefix: 'p:', items: [obj('model', 'hgb')] }
  const recent = { label: 'Recent', keyPrefix: 'r:', items: [obj('factor', 'r12')] }

  const withQuery = build({ pinned, recent, showSuggestions: false })
  assert.equal(selectableRows(withQuery).length, 0)

  const blank = build({ pinned, recent, showSuggestions: true })
  assert.deepEqual(selectableRows(blank).map((r) => r.index), [0, 1])
})

test('keys are unique across every section', () => {
  // The same object can be a result, pinned and recent at once. Duplicate React
  // keys silently drop rows, which is the same failure as a wrong index.
  const same = obj('model', 'hgb')
  const rows = build({
    groups: [{ key: 'model', label: 'Models', items: [same] }],
    pinned: { label: 'Pinned', keyPrefix: 'p:', items: [same] },
    recent: { label: 'Recent', keyPrefix: 'r:', items: [same] },
    showSuggestions: true,
  })
  const keys = rows.map((r) => r.key)
  assert.equal(new Set(keys).size, keys.length, `duplicate row keys: ${keys.join(', ')}`)
})

test('an empty palette produces nothing selectable', () => {
  assert.deepEqual(build(), [])
  assert.deepEqual(selectableRows(build()), [])
})
