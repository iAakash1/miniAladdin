/* A form that refuses to do something says so, and a failed save is visible.

   The add-position form returned without a word on a zero share count, and
   when the save request failed it cleared its busy state and showed nothing:
   a reader pressed "Add position", saw the label flicker, and had no way to
   tell whether the position existed. */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

const SRC = join(__dirname, '..', 'src')
const FORM = readFileSync(join(SRC, 'components', 'terminal', 'PositionsPanel.tsx'), 'utf8')
const STYLES = readFileSync(join(SRC, 'styles', 'system.css'), 'utf8')

test('each invalid field is named, marked invalid and explained', () => {
  for (const [field, message] of [['ticker', 'Enter a ticker.'], ['shares', 'Shares must be a number above zero.'], ['price', 'Average price must be zero or more.']]) {
    assert.ok(FORM.includes(`field: '${field}', text: '${message}'`), `${field} has no message`)
    assert.ok(FORM.includes(`aria-invalid={problem?.field === '${field}' || undefined}`), `${field} is not marked invalid`)
  }
})

test('a request that fails is reported, and editing a field clears the message', () => {
  assert.match(FORM, /if \(!created\) setProblem\(\{ field: 'save'/)
  assert.equal((FORM.match(/setProblem\(null\)/g) ?? []).length >= 4, true)
  assert.match(FORM, /role="alert"/)
})

test('the message and the invalid border are styled, without a negative margin', () => {
  assert.match(STYLES, /\.sys-input\[aria-invalid='true'\]\s*\{[^}]*border-color:\s*var\(--e-neg\)/)
  const rule = STYLES.match(/\.sys-field-error\s*\{([^}]*)\}/)?.[1] ?? ''
  assert.ok(rule, 'no .sys-field-error rule')
  assert.doesNotMatch(rule, /margin:[^;]*-/)
})

test('a detail level that could not be saved is announced, not only put in a tooltip', () => {
  const bar = readFileSync(join(SRC, 'components', 'shell', 'TopBar.tsx'), 'utf8')
  assert.match(bar, /aria-invalid=\{failed \|\| undefined\}/)
  assert.match(bar, /role="status">\{failed \? 'The preference could not be saved\.' : ''\}/)
  assert.match(STYLES, /\.shell-detail__select\[aria-invalid='true'\]\s*\{[^}]*border-color:\s*var\(--e-neg\)/)
})
