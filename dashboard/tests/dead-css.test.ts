/* A stylesheet rule that no markup can reach is a decision someone has to
   re-read.

   "Retire the second architecture" deleted the components behind the quant
   terminal, the model lab, the tour and the reveal cards, and left their
   styles: 381 of the 1,782 classes in the global sheets, 63KB of the 170KB
   in globals.css, several of them with their own hard-coded palette that the
   token audit had to step around. A class counts as reached when its name
   appears in a source file, or begins with a prefix a source file builds a
   name from (`fmark--${tone}`). Nothing else is allowed to stay. */

import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

const SRC = join(__dirname, '..', 'src')

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (/\.tsx?$/.test(name)) out.push(full)
  }
  return out
}

const source = walk(SRC).map((f) => readFileSync(f, 'utf8')).join('\n')
const dynamicPrefixes = new Set<string>([
  ...[...source.matchAll(/([A-Za-z][\w-]*)\$\{/g)].map((m) => m[1]),
  ...[...source.matchAll(/['"`]([A-Za-z][\w-]*)['"`]\s*\+/g)].map((m) => m[1]),
].filter((p) => p.length >= 3))
// A whole token, not a substring: `qt` sat in the sheet for weeks because
// those two letters appear inside other words.
const reached = (cls: string) =>
  new RegExp(`(?<![\\w-])${cls.replace(/[-/\\^$*+?.()|[\]{}]/g, '\\$&')}(?![\\w-])`).test(source) ||
  [...dynamicPrefixes].some((p) => cls.startsWith(p))

const strip = (s: string) => s.replace(/\/\*[\s\S]*?\*\//g, '')
const sheets = ['app/globals.css', 'styles/system.css'].map((f) => ({
  file: f,
  // comments and url(...) go: a data URI's "www.w3.org" is not a class
  css: readFileSync(join(SRC, f), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').replace(/url\([^)]*\)/g, 'url()'),
}))

test('every class the global stylesheets define can be reached from source', () => {
  const unreached: string[] = []
  for (const { file, css } of sheets) {
    const classes = new Set([...css.matchAll(/\.([A-Za-z][\w-]*)(?=[\s,.:{[>+~)]|$)/g)].map((m) => m[1]))
    for (const c of classes) if (!reached(c)) unreached.push(`${file}: .${c}`)
  }
  assert.deepEqual(unreached.sort(), [])
})

test('every keyframe is used by an animation', () => {
  const all = sheets.map((s) => s.css).join('\n') + readFileSync(join(SRC, 'styles', 'tokens.css'), 'utf8')
  const unused = [...all.matchAll(/@keyframes\s+([\w-]+)/g)]
    .map((m) => m[1])
    .filter((name) => (all.match(new RegExp(`(?<![\\w-])${name}(?![\\w-])`, 'g'))?.length ?? 0) < 2 && !source.includes(name))
  assert.deepEqual(unused, [])
})

test('no rule hard-codes a colour when the token it falls back to exists', () => {
  const fallbacks = sheets.flatMap(({ file, css }) =>
    [...css.matchAll(/var\(--(?:pos|neg|warn)\s*,\s*#[0-9a-fA-F]{3,8}\)/g)].map((m) => `${file}: ${m[0]}`))
  assert.deepEqual(fallbacks, [])
})

test('there is one fade, one pulse and one skeleton shimmer', () => {
  // `fade-in` was defined twice with different bodies, so which one ran
  // depended on stylesheet order, and the palette backdrop slid down 6px as
  // it faded in. `live-pulse` was a copy of `sys-pulse`, and Sessions drew its
  // own transform-sweep skeleton beside the system's.
  const all = sheets.map((s) => s.css).join('\n')
  const defined = [...all.matchAll(/@keyframes\s+([\w-]+)/g)].map((m) => m[1])
  const duplicates = defined.filter((n, i) => defined.indexOf(n) !== i)
  assert.deepEqual(duplicates, [])
  for (const alias of ['mkt-fade-in', 'live-pulse', 'ws-skel-sweep']) assert.ok(!defined.includes(alias), `${alias} duplicates a system animation`)
  assert.match(all, /@keyframes fade-in\s*\{\s*from\s*\{\s*opacity:\s*0\s*\}\s*to\s*\{\s*opacity:\s*1\s*\}\s*\}/)
  assert.equal((all.match(/(?<![\w-])\.fade-in\s*\{/g) ?? []).length, 1, '.fade-in is defined more than once')
})

test('no comment sits inside a selector list, where it would swallow the rule below', () => {
  // `.drawer__head,` followed by a comment and a new rule merged the two: the
  // header lost its layout and gained `outline: none`. A trailing comma means
  // the selector list is not finished, so nothing may be inserted there.
  const raw = ['app/globals.css', 'styles/system.css'].map((f) => readFileSync(join(SRC, f), 'utf8')).join('\n')
  const hits = [...raw.matchAll(/,[ \t]*\n[ \t]*\/\*[\s\S]*?\*\/[ \t]*\n[ \t]*([^\n{]*\{)/g)].map((m) => m[0].replace(/\s+/g, ' ').slice(0, 80))
  assert.deepEqual(hits, [])
})

test('every rule\'s selector list is made only of selectors', () => {
  const css = sheets.map((s) => s.css).join('\n')
  const bad = [...css.matchAll(/(^|\})\s*([^{}@]+?)\s*\{/g)]
    .map((m) => m[2])
    .filter((list) => list.split(',').some((part) => part.trim() === '' && list.trim() !== ''))
  assert.deepEqual(bad.map((b) => b.replace(/\s+/g, ' ').slice(0, 80)), [])
})

test('every animation a rule names has a keyframes definition', () => {
  const all = sheets.map((s) => s.css).join('\n') + strip(readFileSync(join(SRC, 'styles', 'tokens.css'), 'utf8'))
  const defined = new Set([...all.matchAll(/@keyframes\s+([\w-]+)/g)].map((m) => m[1]))
  const keywords = new Set(['none', 'infinite', 'both', 'forwards', 'backwards', 'alternate', 'reverse', 'normal', 'running', 'paused',
    'initial', 'inherit', 'unset', 'ease', 'ease-in', 'ease-out', 'ease-in-out', 'linear', 'step-start', 'step-end'])
  const missing: string[] = []
  for (const m of all.matchAll(/(?<![\w-])animation(?:-name)?:\s*([^;}]+)/g)) {
    const value = m[1].replace(/var\([^)]*\)|cubic-bezier\([^)]*\)|steps\([^)]*\)/g, ' ')
    for (const token of value.match(/(?<![\w.-])[a-z][\w-]*(?![\w(-])/g) ?? []) {
      if (!keywords.has(token) && !/^\d/.test(token) && !defined.has(token)) missing.push(token)
    }
  }
  assert.deepEqual([...new Set(missing)], [])
})
