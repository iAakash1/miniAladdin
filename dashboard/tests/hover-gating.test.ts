/* A hover that moves something is only for a pointer that can hover.

   On a touch screen `:hover` is sticky: after a tap the element keeps the
   hovered state until the next tap elsewhere, so a card that lifts a pixel on
   hover stays lifted, a check-mark preview stays half-drawn, and an arrow stays
   nudged. Seven rules did exactly that.

   The rule is narrow on purpose. Colour, border and shadow feedback may stay on
   `:hover` - a stuck border tint is harmless and a tap deserves some answer.
   Anything that changes *geometry* (a transform, a margin, a size) goes behind
   `@media (hover: hover) and (pointer: fine)`. Keyboard focus keeps its own,
   ungated equivalent, so the information is the same for every input method. */

import assert from 'node:assert/strict'
import { basename } from 'node:path'
import test from 'node:test'

import { loadAllCss, type CssRule } from './css-scan'

const MOVES = new Set([
  'transform', 'translate', 'scale', 'rotate', 'margin', 'margin-top', 'margin-right',
  'margin-bottom', 'margin-left', 'top', 'right', 'bottom', 'left', 'inset', 'width',
  'height', 'padding',
])
const NOTHING = new Set(['none', '0', '0px', 'auto', 'inherit', 'unset', 'initial'])

const RULES = loadAllCss()
const hoverGated = (rule: CssRule) => rule.context.some((c) => c.replace(/\s+/g, '').includes('(hover:hover)'))
const isHoverRule = (rule: CssRule) => /:hover/.test(rule.selector)
const movement = (rule: CssRule) => rule.decls.filter(([prop, value]) => MOVES.has(prop) && !NOTHING.has(value))

test('every :hover rule that moves or resizes an element is gated on a hover-capable pointer', () => {
  const offenders = RULES
    .filter((rule) => isHoverRule(rule) && !rule.keyframes && !hoverGated(rule))
    .filter((rule) => movement(rule).length > 0)
    .map((rule) => `${basename(rule.file)}:${rule.line} ${rule.selector} { ${movement(rule).map(([p, v]) => `${p}: ${v}`).join('; ')} }`)
  assert.deepEqual(offenders, [], 'a hover that moves something is not gated on (hover: hover)')
})

test('the gate is the combined hover and fine-pointer query, written one way', () => {
  const gates = new Set<string>()
  for (const rule of RULES) {
    for (const c of rule.context) if (c.replace(/\s+/g, '').includes('(hover:hover)')) gates.add(c)
  }
  assert.ok(gates.size > 0, 'no hover gate exists')
  assert.deepEqual([...gates], ['@media (hover: hover) and (pointer: fine)'], 'hover gating is spelled more than one way')
})

test('keyboard focus keeps the movement a hover is gated away from', () => {
  // For every gated hover rule on a selector that also has a focus form, the
  // focus form must exist ungated, or a keyboard user loses information a mouse
  // user gets.
  const focusMoves = (selector: string) => RULES.some((rule) =>
    !hoverGated(rule) && !isHoverRule(rule) && movement(rule).length > 0
    && rule.selector.split(',').some((part) => part.trim().startsWith(selector) && /:focus(-visible|-within)/.test(part)))
  for (const base of ['.ws-resume', '.ws-card', '.pick::after', '.sys-btn--go']) {
    const probe = base.endsWith('::after') ? base.replace('::after', '') : base
    assert.ok(focusMoves(probe), `${base} lost its keyboard equivalent`)
  }
})

test('reduced motion still switches the gated movement off', () => {
  // The catch-all (`transition-duration: 0.01ms`) stops the animation; the one
  // transform that is positioned rather than animated is also reset explicitly.
  const cmarkReset = RULES.some((rule) =>
    rule.context.some((c) => c.includes('prefers-reduced-motion'))
    && /\.panel:hover \.sugg-marks \.cmark/.test(rule.selector)
    && rule.decls.some(([p, v]) => p === 'transform' && v === 'none'))
  assert.ok(cmarkReset, 'the suggestion marks keep their lift under reduced motion')
})
