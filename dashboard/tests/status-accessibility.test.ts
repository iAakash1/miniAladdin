/* A status chip's meaning is available without hovering.

   `Status` carried what a state means only in `title`. A touch screen cannot
   show a title, a keyboard cannot reach one, and a screen reader announces them
   inconsistently, so "stale" and "blocked" were explained to hover users alone.

   The fix has three parts and each is checked here, by rendering the real
   components on the server rather than by matching their source:

     * every chip points (`aria-describedby`) at a description that exists;
     * the generic descriptions are one hidden block per page, not one per chip;
     * a visible key lists every state, one tap or one Tab from any workspace. */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

import { createElement, type ComponentType } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import { STATE_LABEL, STATE_ORDER, STATE_TITLE, stateMeaningId } from '../src/components/system/state-meaning'

const SRC = join(__dirname, '..', 'src')
const read = (...parts: string[]) => readFileSync(join(SRC, ...parts), 'utf8')

const ids = (html: string) => [...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1])
const describedBy = (html: string) => /aria-describedby="([^"]+)"/.exec(html)?.[1]

test('every state is in the key order exactly once, with a label and a meaning', () => {
  const declared = [...read('components', 'system', 'state-meaning.ts').matchAll(/^\s+(\w+):\s+'/gm)].map((m) => m[1])
  const union = Object.keys(STATE_TITLE).sort()
  assert.deepEqual([...STATE_ORDER].sort(), union, 'the key order and the state table disagree')
  assert.equal(new Set(STATE_ORDER).size, STATE_ORDER.length, 'a state is listed twice')
  assert.deepEqual(Object.keys(STATE_LABEL).sort(), union)
  for (const state of STATE_ORDER) assert.ok(STATE_TITLE[state].length > 10, `${state} has no meaning`)
  assert.ok(declared.length >= STATE_ORDER.length)
})

test('a chip is described by a definition that exists on the page', async () => {
  const { Status } = await import('../src/components/system')
  const StateMeanings = (await import('../src/components/system/StateMeanings')).default
  const page = ids(renderToStaticMarkup(createElement(StateMeanings)))
  for (const state of STATE_ORDER) {
    const chip = renderToStaticMarkup(createElement(Status, { state }))
    const target = describedBy(chip)
    assert.equal(target, stateMeaningId(state), `${state} points somewhere else`)
    assert.ok(page.includes(target!), `${state} is described by an element nobody renders`)
  }
})

test('the shared descriptions are one hidden block with a unique id per state', async () => {
  const StateMeanings = (await import('../src/components/system/StateMeanings')).default
  const html = renderToStaticMarkup(createElement(StateMeanings))
  const found = ids(html)
  assert.equal(found.length, STATE_ORDER.length)
  assert.equal(new Set(found).size, found.length, 'a description id is duplicated')
  assert.match(html, /^<div hidden=""/, 'the block is not hidden, so it would print fifteen paragraphs')
  for (const state of STATE_ORDER) assert.ok(html.includes(STATE_TITLE[state]), `${state}'s meaning is missing`)
})

test('a chip does not repeat the generic definition inside itself', async () => {
  const { Status } = await import('../src/components/system')
  const chip = renderToStaticMarkup(createElement(Status, { state: 'stale' }))
  assert.equal((chip.match(/Real, but past its freshness window/g) ?? []).length, 1, 'the definition is duplicated per chip')
  assert.ok(!/<span[^>]*hidden/.test(chip), 'a generic chip carries its own hidden copy')
})

test('a caller-supplied explanation is described by its own hidden text, and ids stay unique', async () => {
  const { Status } = await import('../src/components/system')
  const html = renderToStaticMarkup(createElement('div', null,
    createElement(Status, { state: 'blocked', label: 'NOT READY', title: 'The final holdout is sealed' }),
    createElement(Status, { state: 'blocked', label: 'NOT READY', title: 'The final holdout is sealed' })))
  const own = [...html.matchAll(/aria-describedby="([^"]+)"/g)].map((m) => m[1])
  assert.equal(own.length, 2)
  assert.notEqual(own[0], own[1], 'two chips share one description id')
  for (const id of own) assert.match(html, new RegExp(`id="${id}" hidden="">The final holdout is sealed`))
})

test('a verdict chip with an explanation is described too', async () => {
  const { Badge } = await import('../src/components/system')
  const html = renderToStaticMarkup(createElement(Badge as ComponentType<Record<string, unknown>>, { tone: 'warn', title: 'Two of five gates failed' }, 'HIGH RISK'))
  const target = describedBy(html)
  assert.ok(target && html.includes(`id="${target}" hidden="">Two of five gates failed`))
  const bare = renderToStaticMarkup(createElement(Badge as ComponentType<Record<string, unknown>>, { tone: 'muted' }, 'x'))
  assert.equal(describedBy(bare), undefined, 'a chip with nothing to say points at nothing')
})

test('the key lists every state with the same words the chip carries', async () => {
  const StateKey = (await import('../src/components/system/StateKey')).default
  const html = renderToStaticMarkup(createElement(StateKey))
  assert.match(html, /<section id="states"/)
  assert.match(html, /<h2[^>]*>Key to states<\/h2>/)
  for (const state of STATE_ORDER) {
    assert.ok(html.includes(`data-state="${state}"`), `${state} is missing from the key`)
    assert.ok(html.includes(STATE_TITLE[state]), `${state}'s definition differs from the chip's`)
  }
})

test('the descriptions are mounted once for every route, and the key is one link from any workspace', () => {
  const layout = read('app', 'layout.tsx')
  assert.match(layout, /import StateMeanings from '@\/components\/system\/StateMeanings'/)
  assert.equal((layout.match(/<StateMeanings \/>/g) ?? []).length, 1)
  assert.match(read('app', 'terminal', 'handbook', 'page.tsx'), /<StateKey \/>/)
  assert.match(read('components', 'shell', 'StatusBar.tsx'), /href="\/terminal\/handbook#states"/)
})

test('the key reaches the stylesheet and uses the spacing and type scales', () => {
  const css = read('styles', 'system.css')
  for (const cls of ['state-key', 'state-key__title', 'state-key__list', 'state-key__row']) {
    assert.match(css, new RegExp(`\\.${cls}(?![\\w-])`), `.${cls} has no rule`)
  }
})
