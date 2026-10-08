/* Width breakpoints come from one ladder.

   Fifteen distinct `max-width` values had accumulated, three of them the same
   decision made twice (1279 and 1280, 700 and 720, 820 and 860). That is not
   flexibility: it means the same layout switches at two different widths on two
   different screens, and nobody can say which is right.

   Some thresholds are genuinely different - a four-column grid and a navigation
   rail do not stop fitting at the same width - so this does not force one
   number. It holds a ladder: layout tiers (where the page's structure changes)
   and content thresholds (where one component's own content stops fitting),
   each written down in tokens.css with the reason. A new width must be added
   to both, with a reason, rather than appearing in passing. */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

import { loadAllCss } from './css-scan'

const TIERS = [640, 760, 1023, 1280]
const CONTENT = [480, 560, 720, 860, 900, 980, 1100, 1180]
const LADDER = [...TIERS, ...CONTENT].sort((a, b) => a - b)

const RULES = loadAllCss()
const used = (() => {
  const widths = new Map<number, number>()
  for (const rule of RULES) {
    for (const context of rule.context) {
      for (const m of context.matchAll(/\((?:min|max)-width:\s*([\d.]+)(px|em|rem)\)/g)) {
        assert.equal(m[2], 'px', `${context}: breakpoints are written in px`)
        widths.set(Number(m[1]), (widths.get(Number(m[1])) ?? 0) + 1)
      }
    }
  }
  return widths
})()

test('every width query uses a value from the ladder', () => {
  const strays = [...used.keys()].filter((w) => !LADDER.includes(w)).sort((a, b) => a - b)
  assert.deepEqual(strays, [], `breakpoints outside the ladder: ${strays.join(', ')}. Add the value to tokens.css and this test, with the content reason.`)
})

test('no two breakpoints are within 30px of each other', () => {
  const sorted = [...used.keys()].sort((a, b) => a - b)
  const close = sorted.slice(1).map((w, i) => [sorted[i], w]).filter(([a, b]) => b - a < 30)
  assert.deepEqual(close, [], 'near-duplicate breakpoints: the same decision is being made twice')
})

test('the ladder is written down in the token file, tier by tier', () => {
  const tokens = readFileSync(join(__dirname, '..', 'src', 'styles', 'tokens.css'), 'utf8')
  const block = /Breakpoints\.[\s\S]*?Add a value only for a content reason/.exec(tokens)?.[0] ?? ''
  assert.ok(block, 'the breakpoint ladder is not documented in tokens.css')
  for (const width of LADDER) assert.match(block, new RegExp(`\\b${width}\\b`), `${width} is in the ladder but not in the documentation`)
  const documented = [...block.matchAll(/^\s{7}(\d{3,4})\s{2,}/gm)].map((m) => Number(m[1])).sort((a, b) => a - b)
  assert.deepEqual(documented, LADDER, 'the documented ladder and the tested ladder differ')
})

test('the stylesheets use the layout tiers where the structure changes', () => {
  // The shell collapse and the phone tier are the two every screen depends on.
  assert.ok((used.get(1023) ?? 0) >= 5, 'the shell no longer collapses at 1023')
  assert.ok((used.get(640) ?? 0) >= 10, 'the phone tier is gone')
  assert.ok((used.get(760) ?? 0) >= 10, 'the tablet tier is gone')
})

test('there is no min-width query: the stylesheets are written desktop-first, consistently', () => {
  const mins = RULES.flatMap((r) => r.context).filter((c) => /\(min-width/.test(c))
  assert.deepEqual(mins, [], 'mixing min-width into a max-width ladder makes the boundaries ambiguous')
})
