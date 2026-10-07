/* The search palette is a modal dialog, and a modal has obligations.

   It is the product's front door: ⌘K or `/` from anywhere. Four things were
   missing. Closing it left focus on the page's body, so a keyboard user lost
   their place on every Escape. Tab walked out of an aria-modal dialog and
   into the page behind the backdrop while the palette stayed open. Results
   arrived without being announced. And a retired model was labelled
   "unavailable" in its result rows, a different fact with a different
   tooltip. These tests read the source because the component needs a DOM. */

import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
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

const read = (...p: string[]) => readFileSync(join(__dirname, '..', 'src', ...p), 'utf8')

test('the inspector panels take focus when they open and give it back when they close', () => {
  const hook = read('components', 'system', 'useDrawerFocus.ts')
  assert.match(hook, /panel\.current\?\.focus\(\)/)
  assert.match(hook, /if \(opener\?\.isConnected\) opener\.focus\(\)/)
  for (const file of ['Inspector.tsx', 'MetricInspector.tsx']) {
    const src = read('components', 'system', file)
    assert.match(src, /useDrawerFocus</, `${file} does not use the hook`)
    assert.match(src, /ref=\{panel\} tabIndex=\{-1\}/, `${file} never lets the panel take focus`)
    assert.doesNotMatch(src, /addEventListener\('keydown'/, `${file} still has its own Escape listener`)
  }
})

test('Escape in an inspector yields to a modal dialog above it', () => {
  // The palette and the inspector both listen on window; one press used to
  // close the palette and the panel beneath it.
  const hook = read('components', 'system', 'useDrawerFocus.ts')
  assert.match(hook, /document\.querySelector\('\[aria-modal="true"\]'\)/)
  assert.match(read('components', 'system', 'Palette.tsx'), /aria-modal="true"/)
})

test('a graph node and a selectable row can be operated from the keyboard and say what they are', () => {
  const graph = read('components', 'system', 'GraphView.tsx')
  assert.match(graph, /role=\{onSelect \? 'button' : undefined\}/)
  assert.match(graph, /aria-pressed=\{onSelect \? isSelected : undefined\}/)
  assert.match(graph, /e\.key === 'Enter' \|\| e\.key === ' '/)
  const table = read('components', 'system', 'index.tsx')
  assert.match(table, /e\.key === 'Enter' \|\| e\.key === ' '/)
  assert.match(table, /aria-current=\{onSelect && selectedKey === key \? 'true' : undefined\}/)
})

test('a failed search is not reported as an empty one', () => {
  const src = read('components', 'system', 'Palette.tsx')
  assert.match(src, /current\.error\s*\n?\s*(?:\/\/.*\n\s*)*\?\s*'Search is unavailable/)
  assert.match(src, /'Search unavailable'/)
  assert.match(src, /Nothing matches “\$\{q\}”\. Try a ticker/)
})

test('icons are drawn at three sizes: 12, 14 and 16', () => {
  const sizes = new Set<number>()
  const walk = (dir: string) => {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name)
      if (statSync(full).isDirectory()) walk(full)
      else if (name.endsWith('.tsx')) {
        for (const m of readFileSync(full, 'utf8').matchAll(/<Icon\b[^>]*\bsize=\{(\d+)\}/g)) sizes.add(Number(m[1]))
      }
    }
  }
  walk(join(__dirname, '..', 'src'))
  assert.deepEqual([...sizes].sort((a, b) => a - b).filter((n) => ![12, 14, 16].includes(n)), [])
})
