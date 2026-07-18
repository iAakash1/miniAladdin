/* Vault mode ↔ URL mapping (v5 F2): every vault state is a bookmarkable
   URL and the mapping round-trips exactly. */
import { strict as assert } from 'node:assert'
import test from 'node:test'
import { modeFromParams, modeToQuery, type Mode } from '../src/components/terminal/VaultView'

test('default URL is the history list', () => {
  assert.deepEqual(modeFromParams(new URLSearchParams('')), { view: 'history' })
})

test('round-trips every mode', () => {
  const modes: Mode[] = [
    { view: 'history' },
    { view: 'saved' },
    { view: 'detail', id: 'abc-123' },
    { view: 'compare', a: 'id-a', b: 'id-b' },
  ]
  for (const mode of modes) {
    const query = modeToQuery(mode)
    assert.deepEqual(modeFromParams(new URLSearchParams(query)), mode, query)
  }
})

test('detail id wins over other params', () => {
  assert.deepEqual(
    modeFromParams(new URLSearchParams('?id=x&view=saved')),
    { view: 'detail', id: 'x' },
  )
})

test('malformed compare falls back to history', () => {
  assert.deepEqual(modeFromParams(new URLSearchParams('?compare=onlyone')), { view: 'history' })
  assert.deepEqual(modeFromParams(new URLSearchParams('?compare=,')), { view: 'history' })
})

test('ids with special characters survive encoding', () => {
  const mode: Mode = { view: 'detail', id: 'a b/c&d' }
  assert.deepEqual(modeFromParams(new URLSearchParams(modeToQuery(mode))), mode)
})
