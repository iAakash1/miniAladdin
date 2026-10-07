/* The search palette is a modal dialog, and a modal has obligations.

   It is the product's front door: ⌘K or `/` from anywhere. Four things were
   missing. Closing it left focus on the page's body, so a keyboard user lost
   their place on every Escape. Tab walked out of an aria-modal dialog and
   into the page behind the backdrop while the palette stayed open. Results
   arrived without being announced. And a retired model was labelled
   "unavailable" in its result rows, a different fact with a different
   tooltip. These tests read the source because the component needs a DOM. */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

const SRC = readFileSync(join(__dirname, '..', 'src', 'components', 'system', 'Palette.tsx'), 'utf8')

test('closing the palette returns focus to the control that opened it', () => {
  assert.match(SRC, /const opener = document\.activeElement instanceof HTMLElement/)
  assert.match(SRC, /if \(opener\?\.isConnected\) opener\.focus\(\)/)
  // restoring belongs in the effect's cleanup, so Escape, a click on the
  // backdrop and choosing a row all restore it
  const effect = SRC.slice(SRC.indexOf('const opener'), SRC.indexOf('// One in-flight screen request'))
  assert.match(effect, /return \(\) => \{[\s\S]*opener\?\.isConnected/)
})

test('Tab cannot leave a modal dialog that is still open', () => {
  assert.match(SRC, /aria-modal="true"/)
  assert.match(SRC, /if \(e\.key === 'Tab'\) e\.preventDefault\(\)/)
})

test('the combobox says it offers a list, and results are announced politely', () => {
  assert.match(SRC, /role="combobox"/)
  assert.match(SRC, /aria-autocomplete="list"/)
  assert.match(SRC, /role="status" aria-live="polite"/)
  assert.match(SRC, /'Searching'/)
})

test('a retired object is drawn as retired, not as unavailable', () => {
  assert.match(SRC, /retired: 'retired'/)
  assert.doesNotMatch(SRC, /retired: 'unavailable'/)
})

test('keyboard navigation and activation are all still wired', () => {
  for (const key of ['ArrowDown', 'ArrowUp', 'Enter', 'Escape']) assert.ok(SRC.includes(`'${key}'`), `${key} is not handled`)
  assert.match(SRC, /aria-activedescendant/)
})
