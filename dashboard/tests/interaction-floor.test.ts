/* The interaction layer holds one shape, however a screen is written.

   Two button families coexisted: legacy `.btn` (17 files) and the system's
   `.sys-btn` (45 files), never in the same file, so pages differed from one
   another rather than within themselves. They disagreed where it matters to
   a keyboard user: `.btn` drew its own focus ring, and a second, global one
   in the stylesheet also rewrote `border-radius` on whatever was focused,
   squaring the corners of any rounded element the moment it was tabbed to.
   Reduced motion was handled class by class and eight animations, among them
   the pulsing live dot and the looping progress bar, had no override.
   The smallest buttons were 22px tall against WCAG 2.2's 24px minimum. */

import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import test from 'node:test'

const SRC = join(__dirname, '..', 'src')
const read = (f: string) => readFileSync(f, 'utf8')
const code = (f: string) => read(f).replace(/\/\*[\s\S]*?\*\//g, '')
const SYSTEM = code(join(SRC, 'styles', 'system.css'))
const GLOBALS = code(join(SRC, 'app', 'globals.css'))

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (/\.tsx?$/.test(name)) out.push(full)
  }
  return out
}

test('there is one button family: nothing uses the legacy .btn classes', () => {
  const offenders: string[] = []
  for (const file of walk(SRC)) {
    for (const m of read(file).matchAll(/className=(?:"([^"]*)"|'([^']*)'|\{`([^`]*)`\})/g)) {
      const tokens = (m[1] ?? m[2] ?? m[3] ?? '').split(/\s+/)
      if (tokens.some((t) => t === 'btn' || t.startsWith('btn--'))) offenders.push(`${relative(SRC, file).split(sep).join('/')}: ${m[0].slice(0, 70)}`)
    }
  }
  assert.deepEqual(offenders, [])
  assert.doesNotMatch(SYSTEM + GLOBALS, /(^|[\s,}])\.btn(--[\w-]+)?\s*[{:,[.]/m, 'legacy button rules are back in the stylesheets')
})

test('the system button has every variant the legacy one carried', () => {
  for (const variant of ['primary', 'ghost', 'accent', 'xs', 'lg', 'go', 'icon', 'micro']) {
    assert.match(SYSTEM + GLOBALS, new RegExp(`\\.sys-btn--${variant}\\b`), `.sys-btn--${variant} is missing`)
  }
  assert.match(SYSTEM, /\.sys-btn\[data-loading='true'\]/)
  assert.match(SYSTEM, /\.sys-btn:disabled,\s*\.sys-btn\[aria-disabled='true'\]/)
})

test('there is exactly one global focus ring and it does not reshape the element', () => {
  const rules = [...(SYSTEM + '\n' + GLOBALS).matchAll(/(?:^|\n)\s*:focus-visible\s*\{([^{}]*)\}/g)]
  assert.equal(rules.length, 1, `${rules.length} global :focus-visible rules`)
  assert.match(rules[0][1], /outline:\s*2px solid var\(--rule-focus\)/)
  assert.doesNotMatch(rules[0][1], /border-radius/, 'the focus ring rewrites the radius of the focused element')
})

test('reduced motion is a catch-all, so a new animation cannot forget to opt out', () => {
  assert.match(SYSTEM, /@media \(prefers-reduced-motion: reduce\)\s*\{\s*\*,\s*\*::before,\s*\*::after\s*\{[^}]*animation-duration:\s*0\.01ms !important[^}]*animation-iteration-count:\s*1 !important[^}]*transition-duration:\s*0\.01ms !important/)
})

test('the smallest button is at least 24px tall, and fingers get a larger floor', () => {
  for (const variant of ['xs', 'micro']) {
    const m = new RegExp(`\\.sys-btn--${variant}\\s*\\{[^}]*height:\\s*(\\d+)px`).exec(SYSTEM)
    assert.ok(m && Number(m[1]) >= 24, `.sys-btn--${variant} is ${m?.[1]}px tall; WCAG 2.2 SC 2.5.8 asks for 24`)
  }
  assert.match(SYSTEM, /@media \(pointer: coarse\)\s*\{[^}]*\.sys-btn\s*\{\s*min-height:\s*36px/)
})

test('forced-colors mode restates the states a background wash cannot carry', () => {
  const block = /@media \(forced-colors: active\)\s*\{([\s\S]*?)\n\}/.exec(GLOBALS)?.[1] ?? ''
  assert.match(block, /\.sys-btn\[aria-pressed='true'\]/)
  assert.match(block, /outline:\s*2px solid Highlight/)
  assert.match(block, /\.sys-btn/)
})

test('on touch, a text field is never under 16px, so iOS does not zoom the page on focus', () => {
  const coarse = SYSTEM.slice(SYSTEM.indexOf('@media (pointer: coarse)'))
  const rule = coarse.match(/:is\(input, select, textarea\)([^{]*)\{([^}]*)\}/)
  assert.ok(rule, 'no coarse-pointer rule for text fields')
  assert.match(rule[2], /font-size:\s*var\(--t-base\)/)
  // checkboxes, radios and buttons are not text fields
  for (const type of ['checkbox', 'radio', 'range', 'button', 'submit']) assert.ok(rule[1].includes(`[type='${type}']`), `${type} should be excluded`)
  // 0,6,1 beats any single-class selector that sizes a field
  assert.ok((rule[1].match(/:not\(/g)?.length ?? 0) >= 4)
})
