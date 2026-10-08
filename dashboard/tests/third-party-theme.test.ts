/* The two widgets that cannot read a CSS variable must still wear the product's colour.

   The sign-in form and the Razorpay checkout take a colour string. Both carried `#1e6b54`, a green
   from an earlier palette, while the product accent is blue, so the first screen a visitor sees and
   the payment screen used a colour the rest of the product never does. The sign-in button also
   hard-coded white text on the accent: 2.9:1 on the dark theme's accent, below the 4.5:1 minimum.
   The CSS guard against hard-coded text on an accent fill never saw it because it read style
   sheets, and this one lives in a TypeScript style object. */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

import { ACCENT_LITERAL, clerkAppearance } from '../src/lib/clerk-appearance'

const SRC = join(__dirname, '..', 'src')
const tokens = readFileSync(join(SRC, 'styles', 'tokens.css'), 'utf8')

const LIGHT = ":root[data-theme='light'] {"
const DARK = ':root {'

/** The first `--name: #hex` inside the block that follows `marker`. */
const tokenIn = (marker: string, name: string): string => {
  const at = tokens.indexOf(marker)
  assert.ok(at >= 0, `${marker} not found in tokens.css`)
  const m = new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})`).exec(tokens.slice(at))
  assert.ok(m, `${name} not found after ${marker}`)
  return m[1].toLowerCase()
}

const luminance = (hex: string) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
const contrast = (a: string, b: string) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

test('the literal accent handed to third-party widgets is the product accent', () => {
  assert.equal(ACCENT_LITERAL.toLowerCase(), tokenIn(LIGHT, '--accent'))
})

test('Clerk is themed with that accent, not a colour from an earlier palette', () => {
  assert.equal(clerkAppearance.variables.colorPrimary, ACCENT_LITERAL)
  assert.notEqual(clerkAppearance.variables.colorPrimary.toLowerCase(), '#1e6b54')
})

test('the Razorpay checkout is themed with the same accent', () => {
  const dialog = readFileSync(join(SRC, 'components', 'terminal', 'UpgradeDialog.tsx'), 'utf8')
  assert.match(dialog, /theme:\s*\{\s*color:\s*ACCENT_LITERAL\s*\}/)
  assert.doesNotMatch(dialog, /#1e6b54/i)
})

test('no source file still carries the retired green', () => {
  for (const file of ['lib/clerk-appearance.ts', 'components/terminal/UpgradeDialog.tsx', 'lib/theme.ts']) {
    assert.doesNotMatch(readFileSync(join(SRC, file), 'utf8'), /#1e6b54/i, file)
  }
})

test('the primary sign-in button takes its text colour from the accent\'s paired token', () => {
  const button = clerkAppearance.elements.formButtonPrimary
  assert.equal(button.background, 'var(--accent)')
  assert.equal(button.color, 'var(--on-accent)')
})

test('the accent keeps 3:1 against the panels of both themes, and the paired text 4.5:1 on each accent', () => {
  const lightPanel = tokenIn(LIGHT, '--p-panel')
  const darkPanel = tokenIn(DARK, '--p-panel')
  assert.ok(contrast(ACCENT_LITERAL, lightPanel) >= 3, 'accent on the light panel')
  assert.ok(contrast(ACCENT_LITERAL, darkPanel) >= 3, 'accent on the dark panel')
  // --on-accent is the panel colour of the theme, so the pairing is dark text on the dark theme's light accent.
  assert.ok(contrast(darkPanel, tokenIn(DARK, '--accent')) >= 4.5, 'dark theme: text on accent')
  assert.ok(contrast(lightPanel, tokenIn(LIGHT, '--accent')) >= 4.5, 'light theme: text on accent')
})
