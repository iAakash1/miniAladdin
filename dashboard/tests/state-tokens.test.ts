/* One mapping from a research state to its colour.

   `--s-*` tokens in tokens.css and the `.sys-status[data-state]` rules in system.css each said which
   colour a state wears, and they disagreed: the token made `recorded` muted, the chip painted it faint.
   Six states had no token at all. The chip now reads the token for every state, so changing the mapping
   is one edit and the other places that read `--s-*` (lineage dots, coverage bars, the graph key)
   cannot drift from it. */

import assert from 'node:assert/strict'
import test from 'node:test'

import { STATE_ORDER } from '../src/components/system/state-meaning'
import { loadAllCss } from './css-scan'

const RULES = loadAllCss()
const declared = (name: string) => RULES.some((r) => r.decls.some(([p]) => p === name))
const chipRule = (state: string) =>
  RULES.filter((r) => r.selector.split(',').some((s) => s.trim() === `.sys-status[data-state='${state}']`))

test('every research state has a colour token', () => {
  const missing = STATE_ORDER.filter((state) => !declared(`--s-${state}`))
  assert.deepEqual(missing, [])
})

test('the chip for every state reads that state\'s token, and no other colour', () => {
  const offenders: string[] = []
  for (const state of STATE_ORDER) {
    const rules = chipRule(state)
    if (rules.length === 0) { offenders.push(`${state}: no rule`); continue }
    const colours = rules.flatMap((r) => r.decls.filter(([p]) => p === '--tone' || p === 'color'))
    // retired is drawn as a ring and sets no dot tone; everything else sets --tone.
    if (state !== 'retired' && !colours.some(([p, v]) => p === '--tone' && v === `var(--s-${state})`)) {
      offenders.push(`${state}: --tone is not var(--s-${state})`)
    }
    for (const [p, v] of colours) {
      if (/var\(--e-(pos|neg|warn|null|info)\)/.test(v)) offenders.push(`${state}: ${p} repeats a literal ${v}`)
    }
  }
  assert.deepEqual(offenders, [])
})

test('no state token is a raw colour; each aliases a semantic or ink token', () => {
  const bad = RULES
    .flatMap((r) => r.decls.filter(([p, v]) => /^--s-[a-z]+$/.test(p) && !/^var\(--(e-|ink-|accent)/.test(v)))
    .map(([p, v]) => `${p}: ${v}`)
  assert.deepEqual(bad, [])
})
