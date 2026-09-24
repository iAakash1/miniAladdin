/* The palette paints headers and rows in one column but selects with a single
   flat index. If the painted order and the index disagree the surface breaks
   quietly: the highlighted row and the row Enter opens are different rows.

   These assert the invariant that makes the listbox coherent: the indices this
   produces are exactly 0..N-1 in render order, headers carry none, and a header
   never appears without rows under it. */
import { strict as assert } from 'node:assert'
import test from 'node:test'

import { buildRows, selectableRows, type PaletteSection } from '../src/lib/palette-rows'

const section = (key: string, items: string[]): PaletteSection<string> => ({
  key, label: key[0].toUpperCase() + key.slice(1), items, itemKey: (s) => s,
})

test('indices are exactly 0..N-1 in paint order', () => {
  const rows = buildRows([
    section('companies', ['AAPL', 'MSFT']),
    section('actions', ['watch']),
    section('models', ['hgb', 'ridge']),
  ])
  assert.deepEqual(selectableRows(rows).map((r) => r.index), [0, 1, 2, 3, 4])
})

test('paint order and index order are the same order', () => {
  const rows = buildRows([section('companies', ['AAPL']), section('goto', ['home', 'providers'])])
  let expected = 0
  for (const row of rows) {
    if (row.type === 'header') continue
    assert.equal(row.index, expected, 'painted order does not match index order')
    expected += 1
  }
})

test('headers carry no index and never appear empty', () => {
  const rows = buildRows([section('companies', []), section('models', ['hgb'])])
  const headers = rows.filter((r) => r.type === 'header')
  assert.deepEqual(headers.map((h) => h.label), ['Models'])
  for (const h of headers) assert.ok(!('index' in h))
})

test('keys are unique across sections that share an item', () => {
  // The same symbol can be a search result and a recent company at once.
  // Duplicate React keys silently drop rows.
  const rows = buildRows([section('recent', ['AAPL']), section('companies', ['AAPL'])])
  const keys = rows.map((r) => r.key)
  assert.equal(new Set(keys).size, keys.length, `duplicate row keys: ${keys.join(', ')}`)
})

test('an empty palette produces nothing selectable', () => {
  assert.deepEqual(buildRows([]), [])
  assert.deepEqual(selectableRows(buildRows([section('companies', [])])), [])
})
