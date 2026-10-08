/* A dialog that says it is modal has to behave like one.

   The keyboard-shortcuts sheet declared `aria-modal="true"` and nothing else: opening it left
   focus on the page behind it, Tab walked out of it into content a screen reader had been told
   was inert, and closing it did not put focus back. The palette, the inspectors and `ui/Dialog`
   had all been fixed for exactly this; the sheet was missed. */

import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import test from 'node:test'

import { trapTarget } from '../src/components/system/useModalFocus'

const SRC = join(__dirname, '..', 'src')

// ── the wrap-around rule ─────────────────────────────────────────────────────

test('Tab from the last control wraps to the first, and Shift+Tab from the first to the last', () => {
  const items = ['close', 'filter', 'row']
  assert.equal(trapTarget(items, 'row', false, 'panel'), 'close')
  assert.equal(trapTarget(items, 'close', true, 'panel'), 'row')
})

test('Tab inside the dialog moves normally', () => {
  const items = ['close', 'filter', 'row']
  assert.equal(trapTarget(items, 'close', false, 'panel'), null)
  assert.equal(trapTarget(items, 'filter', false, 'panel'), null)
  assert.equal(trapTarget(items, 'row', true, 'panel'), null)
})

test('Shift+Tab from the dialog itself, or from nowhere, goes to the last control', () => {
  const items = ['close', 'row']
  assert.equal(trapTarget(items, 'panel', true, 'panel'), 'row')
  assert.equal(trapTarget(items, null, true, 'panel'), 'row')
})

test('a dialog with no controls keeps focus on the dialog', () => {
  assert.equal(trapTarget([], null, false, 'panel'), 'panel')
  assert.equal(trapTarget([], 'panel', true, 'panel'), 'panel')
})

// ── every modal manages focus ────────────────────────────────────────────────

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (/\.tsx$/.test(name)) out.push(full)
  }
  return out
}

/** Dialogs that carry their own, complete focus handling, each with its own coverage. `Drawer` is the
 *  mobile navigation: it focuses its close button, wraps Tab over the visible controls, closes on
 *  Escape and returns focus to the opener. */
const OWN_FOCUS = new Set([
  'components/ui/Dialog.tsx',
  'components/system/Palette.tsx',
  'components/shell/Drawer.tsx',
])

test('every dialog sets focus on open and gives it back, by a shared hook or an audited equivalent', () => {
  const offenders: string[] = []
  for (const file of walk(SRC)) {
    const rel = relative(SRC, file).split(sep).join('/')
    const text = readFileSync(file, 'utf8')
    if (!/role="dialog"/.test(text) || OWN_FOCUS.has(rel)) continue
    // Modal: must also trap Tab. Non-modal side panel: focus in, focus back, Escape yields to a modal.
    const modal = /aria-modal=("true"|\{true\})/.test(text)
    const ok = modal ? /useModalFocus\s*[<(]/.test(text) : /use(Drawer|Modal)Focus\s*[<(]/.test(text)
    if (!ok) offenders.push(`${rel} (${modal ? 'modal' : 'non-modal'})`)
  }
  assert.deepEqual(offenders, [], 'a dialog manages neither focus nor its return')
})

test('the shortcuts sheet is wired to the hook and can receive focus', () => {
  const sheet = readFileSync(join(SRC, 'components', 'system', 'Shortcuts.tsx'), 'utf8')
  assert.match(sheet, /const panel = useModalFocus<HTMLDivElement>\(open\)/)
  assert.match(sheet, /ref=\{panel\}\s+tabIndex=\{-1\}[^>]*role="dialog"/)
})

test('the hook restores focus to the opener and removes its listener', () => {
  const hook = readFileSync(join(SRC, 'components', 'system', 'useModalFocus.ts'), 'utf8')
  assert.match(hook, /opener\.focus\(\)/)
  assert.match(hook, /removeEventListener\('keydown', onKey\)/)
})
