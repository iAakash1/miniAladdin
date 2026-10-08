/* One grammar for state and for verdict.

   Two chip designs coexisted: the system's outlined `.sys-badge` and a filled
   legacy `.badge` with its own colours, size and typeface, used by eleven
   files and re-tuned by hand with inline heights (17, 19, 20, 24, 26) so no
   two looked alike. A third, `.pal-badge`, had no CSS at all: four screens
   rendered an unstyled glyph where the palette draws a bordered square.
   Retired models were drawn as "unavailable" and a paper order as "recorded",
   so their tooltips described a different fact.

   Provenance is `Status` (a dot and a word). A conclusion is `Badge` (an
   outlined chip, five tones). Nothing else draws either. */

import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import test from 'node:test'

const SRC = join(__dirname, '..', 'src')
const read = (f: string) => readFileSync(f, 'utf8')
const code = (f: string) => read(f).replace(/\/\*[\s\S]*?\*\//g, '')
const SYSTEM = code(join(SRC, 'styles', 'system.css'))
const GLOBALS = code(join(SRC, 'app', 'globals.css'))
const INDEX = read(join(SRC, 'components', 'system', 'index.tsx'))
/* The state tables are plain TypeScript, not part of the client module, so a
   server component can read the same words the chip carries. */
const MEANING = read(join(SRC, 'components', 'system', 'state-meaning.ts'))

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (/\.tsx?$/.test(name)) out.push(full)
  }
  return out
}

const rel = (f: string) => relative(SRC, f).split(sep).join('/')
const staticClassTokens = (file: string) => {
  const tokens: string[] = []
  for (const m of read(file).matchAll(/className=(?:"([^"]*)"|'([^']*)'|\{`([^`$]*)`\})/g)) {
    tokens.push(...(m[1] ?? m[2] ?? m[3] ?? '').split(/\s+/).filter(Boolean))
  }
  return tokens
}

const states = (() => {
  const union = MEANING.match(/export type ResearchState =([\s\S]*?)\n\nexport const STATE_TITLE/)
  assert.ok(union, 'ResearchState union not found')
  return [...union[1].matchAll(/'([a-z]+)'/g)].map((m) => m[1])
})()

test('the status vocabulary covers live, stale, unavailable, experimental, retired, paper, production, error, warning and info', () => {
  for (const wanted of ['live', 'stale', 'unavailable', 'experimental', 'retired', 'paper', 'production', 'error', 'warning', 'info']) {
    assert.ok(states.includes(wanted), `Status has no "${wanted}" state`)
  }
})

test('every status has a tooltip, a label and a style', () => {
  const title = MEANING.match(/const STATE_TITLE[^{]*\{([\s\S]*?)\n\}/)?.[1] ?? ''
  const label = MEANING.match(/const STATE_LABEL[^{]*\{([\s\S]*?)\n\}/)?.[1] ?? ''
  const missing: string[] = []
  for (const s of states) {
    if (!new RegExp(`\\b${s}:\\s*'`).test(title)) missing.push(`${s}: tooltip`)
    if (!new RegExp(`\\b${s}:\\s*'`).test(label)) missing.push(`${s}: label`)
    // waking is drawn by the loading line, unknown is the base style
    if (!['waking', 'unknown'].includes(s) && !SYSTEM.includes(`.sys-status[data-state='${s}']`)) missing.push(`${s}: css`)
  }
  assert.deepEqual(missing, [])
})

test('a status does not borrow another status to look right', () => {
  // A retired model is not "unavailable" and a paper order is not "recorded":
  // the tooltip would describe a different fact.
  const borrowed: string[] = []
  for (const file of walk(SRC)) {
    const text = read(file)
    if (/case 'retired':\s*return 'unavailable'/.test(text)) borrowed.push(`${rel(file)}: retired -> unavailable`)
    if (/status === 'retired' \? 'unavailable'/.test(text)) borrowed.push(`${rel(file)}: retired -> unavailable`)
    if (/<Status state="recorded" label="paper/i.test(text)) borrowed.push(`${rel(file)}: paper -> recorded`)
  }
  assert.deepEqual(borrowed, [])
})

test('there is one chip family: nothing uses the legacy .badge classes', () => {
  const offenders: string[] = []
  for (const file of walk(SRC)) {
    for (const t of staticClassTokens(file)) {
      if (t === 'badge' || t.startsWith('badge--') || t === 'pal-badge') offenders.push(`${rel(file)}: ${t}`)
    }
  }
  assert.deepEqual(offenders, [])
  assert.ok(!/(^|[^\w-])\.badge\b/.test(GLOBALS + SYSTEM), 'the legacy .badge rules are still in the stylesheet')
})

test('a chip is never re-sized by hand', () => {
  const offenders: string[] = []
  for (const file of walk(SRC)) {
    for (const m of read(file).matchAll(/<Badge\b[^>]*style=/g)) offenders.push(`${rel(file)}: ${m[0]}`)
  }
  assert.deepEqual(offenders, [])
})

test('every tone a Badge can take is styled', () => {
  const tones = INDEX.match(/export type Tone =([^\n]*)/)?.[1].match(/'([a-z]+)'/g)?.map((t) => t.slice(1, -1)) ?? []
  assert.deepEqual([...tones].sort(), ['fail', 'info', 'muted', 'pass', 'warn'])
  for (const tone of tones) assert.ok(SYSTEM.includes(`.sys-badge[data-tone='${tone}']`), `no style for tone ${tone}`)
})

test('every static sys-* and pal-* class a component names exists in the stylesheet', () => {
  const css = SYSTEM + GLOBALS
  const defined = (cls: string) => new RegExp(`\\.${cls.replace(/[-]/g, '\\-')}(?![\\w-])`).test(css)
  const missing = new Set<string>()
  for (const file of walk(SRC)) {
    for (const t of staticClassTokens(file)) {
      if (/^(sys|pal)-[a-z0-9_-]+$/.test(t) && !defined(t)) missing.add(`${t}  (${rel(file)})`)
    }
  }
  assert.deepEqual([...missing].sort(), [])
})
