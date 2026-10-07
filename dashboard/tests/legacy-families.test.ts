/* One surface, one heading scale, one label, one field, one table.

   Five legacy class families outlived the system that replaced them, each
   drifting from it. A text field was 34px tall beside 28px buttons in one
   toolbar and 28px in the next, and 11 to 15px in type, so the palette's
   input made iOS zoom the page. Thirty-one panels set their own padding in
   nine different ways and their headings in five sizes. Labels were 11px in
   sixty-six places and 10px in thirty-eight. Tables were restyled by four
   stacked blocks of `.data-table` rules, three of which overrode the last. */

import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import test from 'node:test'

const SRC = join(__dirname, '..', 'src')
const css = (f: string) => readFileSync(join(SRC, f), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '')
const STYLES = css('app/globals.css') + css('styles/system.css')

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (name.endsWith('.tsx')) out.push(full)
  }
  return out
}

/** Every JSX opening tag, brace- and quote-aware, so an `=>` in a prop does not end it. */
function* tags(text: string): Generator<string> {
  for (let i = 0; i < text.length; i++) {
    if (text[i] !== '<' || !/[A-Za-z]/.test(text[i + 1] ?? '')) continue
    let depth = 0
    let quote: string | null = null
    let j = i
    for (; j < text.length; j++) {
      const c = text[j]
      if (quote) { if (c === quote && text[j - 1] !== '\\') quote = null }
      else if (c === '"' || c === "'" || c === '`') quote = c
      else if (c === '{') depth++
      else if (c === '}') depth--
      else if (c === '>' && depth === 0 && text[j - 1] !== '=') break
    }
    yield text.slice(i, j + 1)
    i = j
  }
}

const classes = (tag: string) => (tag.match(/className="([^"]*)"/)?.[1] ?? '').split(/\s+/).filter(Boolean)
const style = (tag: string) => tag.match(/style=\{\{([\s\S]*?)\}\}/)?.[1] ?? ''
const rel = (f: string) => relative(SRC, f).split(sep).join('/')

test('the legacy field, label and table classes are gone from markup and from the stylesheet', () => {
  const offenders: string[] = []
  for (const file of walk(SRC)) {
    for (const tag of tags(readFileSync(file, 'utf8'))) {
      for (const c of classes(tag)) if (['input', 'input--sm', 'label', 'data-table'].includes(c)) offenders.push(`${rel(file)}: ${c}`)
    }
  }
  assert.deepEqual(offenders, [])
  for (const selector of [/(^|[^\w-])\.input(?![\w-])/, /(^|[^\w-])\.label(?![\w-])/, /(^|[^\w-])\.data-table(?![\w-])/, /\.input--sm/]) {
    assert.ok(!selector.test(STYLES), `${selector} is still styled`)
  }
})

test('a panel takes its padding from a class, not from its own style', () => {
  const offenders: string[] = []
  for (const file of walk(SRC)) {
    for (const tag of tags(readFileSync(file, 'utf8'))) {
      if (classes(tag).includes('panel') && /(?<![\w-])padding\s*:/.test(style(tag))) offenders.push(`${rel(file)}: ${tag.slice(0, 80)}`)
    }
  }
  assert.deepEqual(offenders, [])
  assert.equal((STYLES.match(/\.panel--pad\s*\{/g) ?? []).length, 1, '.panel--pad is defined more than once')
  assert.match(STYLES, /\.panel--compact\s*\{/)
})

test('headings and labels take their size from a class', () => {
  const offenders: string[] = []
  for (const file of walk(SRC)) {
    for (const tag of tags(readFileSync(file, 'utf8'))) {
      const own = classes(tag)
      if ((own.includes('h-panel') || own.includes('sys-label')) && /fontSize\s*:/.test(style(tag))) offenders.push(`${rel(file)}: ${tag.slice(0, 80)}`)
    }
  }
  assert.deepEqual(offenders, [])
  for (const level of ['.h-panel--sub', '.h-panel--lg']) assert.ok(STYLES.includes(level), `${level} is missing`)
})

test('a text field is the same height as the button beside it', () => {
  const height = (selector: string) => STYLES.match(new RegExp(`${selector.replace('.', '\\.')}\\s*\\{[^}]*?(?<![\\w-])height:\\s*(\\d+)px`))?.[1]
  assert.equal(height('.sys-input'), height('.sys-btn'))
})

test('a text field takes its size from the field class, not from its own style', () => {
  // Thirteen fields set a 26, 32 or 36px height and their own type size to
  // patch over a 34px default that no longer exists. The sizes are classes now.
  const offenders: string[] = []
  for (const file of walk(SRC)) {
    if (rel(file) === 'components/terminal/memos/Memos.tsx') continue // a memo title is deliberately set in lead type
    for (const tag of tags(readFileSync(file, 'utf8'))) {
      if (!/^<(input|select)\b/.test(tag) || !classes(tag).includes('sys-input')) continue
      if (/(?<![\w-])(height|fontSize)\s*:/.test(style(tag))) offenders.push(`${rel(file)}: ${tag.slice(0, 90)}`)
    }
  }
  assert.deepEqual(offenders, [])
  assert.match(STYLES, /\.sys-input--lg\s*\{[^}]*height:\s*36px/)
})

/** The end of the JSX tag that starts at `from`, aware of braces and quotes. */
function tagEnd(text: string, from: number): number {
  let depth = 0
  let quote: string | null = null
  for (let i = from; i < text.length; i++) {
    const c = text[i]
    if (quote) { if (c === quote && text[i - 1] !== '\\') quote = null }
    else if (c === '"' || c === "'" || c === '`') quote = c
    else if (c === '{') depth++
    else if (c === '}') depth--
    else if (c === '>' && depth === 0 && text[i - 1] !== '=') return i + 1
  }
  return -1
}

test('a panel is never drawn inside another panel', () => {
  // A card inside a card inside a card is what makes a financial interface
  // read as a template. A group takes a heading (`Section`), not a surface.
  const nested: string[] = []
  for (const file of walk(SRC)) {
    const text = readFileSync(file, 'utf8')
    const stack: Array<{ name: string; surface: boolean }> = []
    for (const m of text.matchAll(/<\/?([A-Za-z][\w.]*)/g)) {
      const end = tagEnd(text, m.index!)
      if (end < 0) continue
      const tag = text.slice(m.index!, end)
      const name = m[1]
      if (tag.startsWith('</')) {
        const at = stack.map((s) => s.name).lastIndexOf(name)
        if (at >= 0) stack.length = at
        continue
      }
      const surface = name === 'Panel' || classes(tag).some((c) => c === 'sys-panel' || c === 'panel')
      // an empty or loading state drawn inside a panel is the panel's content, not a second surface
      if (surface && stack.some((s) => s.surface)) nested.push(`${rel(file)}:${text.slice(0, m.index!).split('\n').length}`)
      if (!tag.trimEnd().endsWith('/>')) stack.push({ name, surface })
    }
  }
  assert.deepEqual(nested, [])
})
