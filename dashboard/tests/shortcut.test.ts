/* A shortcut is printed for the keyboard in front of the reader.

   The palette opens on Meta+K and Control+K, but six places printed "⌘K" for
   everyone — the Mac symbol, to readers on Windows and Linux whose keyboards
   have no such key. The one component that writes a chord knows the platform. */

import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import test from 'node:test'

import { chord } from '../src/components/system/Shortcut'

const SRC = join(__dirname, '..', 'src')

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (name.endsWith('.tsx')) out.push(full)
  }
  return out
}

test('a chord reads ⌘K on a Mac and Ctrl K everywhere else', () => {
  assert.equal(chord('⌘', 'K'), '⌘K')
  assert.equal(chord('Ctrl', 'K'), 'Ctrl K')
  assert.equal(chord('Ctrl', 'C'), 'Ctrl C')
})

test('the palette answers to both modifiers', () => {
  const palette = readFileSync(join(SRC, 'components', 'system', 'Palette.tsx'), 'utf8')
  assert.match(palette, /e\.metaKey \|\| e\.ctrlKey/)
})

test('no component prints the Mac command symbol as if it were everyone\'s key', () => {
  const allowed = new Set(['components/system/Shortcut.tsx', 'components/system/Shortcuts.tsx'])
  const offenders: string[] = []
  for (const file of walk(SRC)) {
    const rel = relative(SRC, file).split(sep).join('/')
    if (allowed.has(rel)) continue
    const text = readFileSync(file, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
    if (text.includes('⌘')) offenders.push(rel)
  }
  assert.deepEqual(offenders, [])
})

test('the shortcut sheet lists both forms of the command key', () => {
  const sheet = readFileSync(join(SRC, 'components', 'system', 'Shortcuts.tsx'), 'utf8')
  assert.match(sheet, /⌘K · Ctrl K/)
})

test('the search button is named by its visible text, with the shortcut declared', () => {
  const bar = readFileSync(join(SRC, 'components', 'shell', 'TopBar.tsx'), 'utf8')
  // the opening tag holds an arrow function, so read the line rather than up to the first '>'
  const button = bar.match(/<button[^\n]*className="shell-search"[^\n]*/)?.[0] ?? ''
  assert.ok(button, 'search button not found')
  assert.doesNotMatch(button, /aria-label/, 'an aria-label that differs from the visible text breaks voice control')
  assert.match(button, /aria-keyshortcuts="Control\+K Meta\+K"/)
})
