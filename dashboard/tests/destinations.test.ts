/* The navigation registry is read by the rail, the palette, the chords and
   the workspace tabs. These keep the four from disagreeing. */
import { strict as assert } from 'node:assert'
import { existsSync } from 'node:fs'
import test from 'node:test'

import {
  ALL_DESTINATIONS, ALL_VIEWS, DESTINATIONS, GOTO, destinationAt, groupOf, viewAt,
} from '../src/lib/destinations'

const APP = new URL('../src/app/', import.meta.url).pathname

test('every chord is unique and reaches its destination', () => {
  const keys = ALL_DESTINATIONS.map((d) => d.key)
  assert.equal(new Set(keys).size, keys.length, `duplicate chord letters: ${keys.join(' ')}`)
  for (const d of ALL_DESTINATIONS) assert.equal(GOTO[d.key], d.href)
  // `g c` is reserved for reopening the last company.
  assert.ok(!keys.includes('c'))
})

test('every view resolves to the destination that owns it', () => {
  for (const d of ALL_DESTINATIONS) {
    for (const v of d.views ?? []) {
      assert.equal(destinationAt(v.href)?.href, d.href, `${v.href} does not resolve to ${d.label}`)
      assert.equal(viewAt(v.href)?.href, v.href)
    }
  }
})

test('a route appears in the registry once', () => {
  const hrefs = ALL_VIEWS.map((v) => v.href)
  assert.equal(new Set(hrefs).size, hrefs.length, 'a view is listed under two destinations')
})

test('a destination with views lists its own route first', () => {
  for (const d of ALL_DESTINATIONS) {
    if (d.views?.length) assert.equal(d.views[0].href, d.href, `${d.label} does not open on its first tab`)
  }
})

test('every registered route has a page', () => {
  for (const v of ALL_VIEWS) {
    const dir = v.href.replace(/^\//, '')
    assert.ok(existsSync(`${APP}${dir}/page.tsx`), `${v.href} has no page`)
  }
})

test('sub-routes and unknown routes resolve sensibly', () => {
  assert.equal(groupOf('/terminal/graph/explore'), 'Research')
  assert.equal(viewAt('/terminal/graph/explore')?.label, 'Path explorer')
  assert.equal(groupOf('/terminal/nowhere'), null)
  assert.equal(groupOf('/'), null)
  assert.equal(DESTINATIONS.length, 4)
})
