import assert from 'node:assert/strict'
import test from 'node:test'

import { GOTO_TARGETS } from '../src/components/terminal/useGotoShortcuts'

test('every chord points at a route that exists', () => {
  // Routes present under dashboard/src/app. A shortcut to a page that does not
  // exist is worse than no shortcut: it fails silently on a 404.
  const routes = new Set([
    '/terminal', '/terminal/analyze', '/terminal/factors', '/quant',
    '/terminal/models', '/terminal/portfolio', '/terminal/sessions',
    '/terminal/validation',
  ])
  for (const target of GOTO_TARGETS) {
    assert.ok(routes.has(target.href), `${target.href} is not a known route`)
  }
})

test('chord keys are unique', () => {
  const keys = GOTO_TARGETS.map((t) => t.key)
  assert.equal(new Set(keys).size, keys.length, 'two chords cannot share a key')
})

test('chord keys are single lowercase letters', () => {
  for (const target of GOTO_TARGETS) {
    assert.match(target.key, /^[a-z]$/, `${target.key} is not a single lowercase letter`)
  }
})

test('no chord uses g, the prefix itself', () => {
  assert.ok(!GOTO_TARGETS.some((t) => t.key === 'g'))
})

test('every chord has a label for the discoverability footer', () => {
  for (const target of GOTO_TARGETS) {
    assert.ok(target.label.length > 0)
  }
})
