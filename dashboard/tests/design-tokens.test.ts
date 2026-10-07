/* The design tokens are the single source of truth, so a reference to one that
   does not exist has to fail loudly.

   `var(--x)` with no definition and no fallback is not an error in CSS: the
   declaration is simply invalid at computed-value time and the property falls
   back to its initial value. Two of those shipped unnoticed. `--surface-1` was
   the background of every cell in the Quant Lab grids, which draw their
   hairlines with `gap: 1px; background: var(--line)`, so with the cell fill
   gone the cells took the separator's colour. `--s-1/2/3` were spacing tokens
   that never existed (spacing is `--d-*`), so the admin diagnostics list had no
   margin, gap or padding. Neither raises anything. Only a check can see them. */

import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import test from 'node:test'

const SRC = join(__dirname, '..', 'src')

function walk(dir: string, exts: RegExp, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, exts, out)
    else if (exts.test(name)) out.push(full)
  }
  return out
}

const CSS = walk(SRC, /\.css$/)
const SOURCES = walk(SRC, /\.(tsx?|css)$/)
const read = (f: string) => readFileSync(f, 'utf8')
const rel = (f: string) => relative(SRC, f).split(sep).join('/')
/** A stylesheet's code without its comments, so prose can never match a rule. */
const code = (f: string) => read(f).replace(/\/\*[\s\S]*?\*\//g, '')

/** Every custom property defined anywhere: in a stylesheet, as an inline-style
 *  key, or through setProperty. */
function definedProperties(): Set<string> {
  const defined = new Set<string>()
  for (const file of SOURCES) {
    const text = read(file)
    // A declaration, not the tail of a class name: `.qc__key--gap::before`
    // once counted as a definition of --gap, which was never defined.
    for (const m of text.matchAll(/(?<![\w-])(--[\w-]+)\s*:(?!:)/g)) defined.add(m[1])
    for (const m of text.matchAll(/['"`](--[\w-]+)['"`]\s*:/g)) defined.add(m[1])
    for (const m of text.matchAll(/setProperty\(\s*['"`](--[\w-]+)/g)) defined.add(m[1])
  }
  return defined
}

test('the stylesheets define a real token set', () => {
  const defined = definedProperties()
  assert.ok(CSS.length >= 3, 'stylesheets not found')
  for (const token of ['--p-base', '--ink', '--rule', '--accent', '--e-pos', '--e-neg', '--d-3', '--r-md', '--t-body']) {
    assert.ok(defined.has(token), `${token} is not defined`)
  }
})

test('no var(--x) refers to a custom property that is not defined and has no fallback', () => {
  const defined = definedProperties()
  const offenders = new Map<string, Set<string>>()
  for (const file of SOURCES) {
    for (const m of read(file).matchAll(/var\(\s*(--[\w-]+)\s*([,)])/g)) {
      const [, name, after] = m
      if (after === ',') continue // has a fallback
      if (!defined.has(name)) {
        if (!offenders.has(name)) offenders.set(name, new Set())
        offenders.get(name)!.add(rel(file))
      }
    }
  }
  const report = [...offenders].map(([name, files]) => `${name} in ${[...files].join(', ')}`)
  assert.deepEqual(report, [], 'an undefined token makes the whole declaration invalid')
})

/* ── the scales ───────────────────────────────────────────────────────────────

   A token set only holds if values off the scale are refused. Before this was
   enforced the stylesheets and inline styles carried 55 distinct font sizes
   (11.5px and 12.5px among them), a dozen weights (430, 470, 550, 560, 590,
   620, 650), 31 letter-spacings and 11 transition durations, around tokens that
   already existed. About 30 declarations were below the 10px token floor,
   including the eyebrow on every page header and the navigation key hints.

   Raw values are allowed only where a token cannot express them: fluid sizes
   (`clamp`, `em`, `%`), circles, hairlines, and the named hero sizes. SVG text
   is excluded from the size rule because its CSS pixels are user units scaled
   by the chart's viewBox, not screen pixels; it is reviewed with the charts. */

const STYLESHEETS = CSS.filter((f) => !/tokens\.css$/.test(f))
const TSX = SOURCES.filter((f) => /\.tsx$/.test(f))
const SVG_TEXT_RULE = /gfocus__edge-label|pchart__tag-text|pchart__tick|\brt-t|\brt-x/

function rules(file: string): Array<{ selector: string; body: string }> {
  return [...code(file).matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({ selector: m[1].trim(), body: m[2] }))
}

const HERO_SIZES = new Set(['34px', '4rem', '1.875rem'])

test('every CSS font-size is a type token, a fluid size, or a named hero size', () => {
  const bad: string[] = []
  for (const file of STYLESHEETS) {
    for (const { selector, body } of rules(file)) {
      if (SVG_TEXT_RULE.test(selector)) continue
      for (const m of body.matchAll(/(?<![-\w])font-size:\s*([^;!]+)/g)) {
        const v = m[1].trim()
        if (/^var\(--t-[\w-]+\)$/.test(v) || /^(clamp|calc|min|max)\(/.test(v) || /(em|%)$/.test(v) && !/rem$/.test(v)) continue
        if (v === 'inherit' || v === '0' || HERO_SIZES.has(v)) continue
        bad.push(`${rel(file)}: ${selector.replace(/\s+/g, ' ').slice(-48)} { font-size: ${v} }`)
      }
    }
  }
  assert.deepEqual(bad, [], 'off-scale font size: use a --t-* token')
})

test('every font shorthand uses a type token, apart from SVG text and the report title', () => {
  const bad: string[] = []
  for (const file of STYLESHEETS) {
    for (const { selector, body } of rules(file)) {
      if (SVG_TEXT_RULE.test(selector) || /\.rp-title h1/.test(selector)) continue
      for (const m of body.matchAll(/(?<![-\w])font:\s*(?:(?:italic|oblique|normal|small-caps|bold|\d{3})\s+)*([^\s/;]+)/g)) {
        if (/^(inherit|initial|unset)$/.test(m[1])) continue // sets no size
        if (/^(clamp|calc|min|max)\(/.test(m[1]) || /^\d*\.?\d+(em|%)$/.test(m[1])) continue // fluid or relative
        if (!/^var\(--t-[\w-]+\)$/.test(m[1])) bad.push(`${rel(file)}: ${selector.replace(/\s+/g, ' ').slice(-48)} { font: … ${m[1]} }`)
      }
    }
  }
  assert.deepEqual(bad, [])
})

test('nothing sets text below the 10px token floor', () => {
  const micro = Number(/--t-micro:\s*(\d+)px/.exec(read(join(SRC, 'styles', 'tokens.css')))?.[1] ?? NaN)
  assert.equal(micro, 10)
  const small: string[] = []
  for (const file of [...STYLESHEETS, ...TSX]) {
    for (const m of (file.endsWith('.css') ? code(file) : read(file)).matchAll(/(?:font-size:|fontSize:)\s*['"]?(\d*\.?\d+)(px|rem)?['"]?/g)) {
      const px = Number(m[1]) * (m[2] === 'rem' ? 16 : 1)
      if (px > 0 && px < 10 && m[2] !== undefined) small.push(`${rel(file)}: ${m[0]}`)
    }
  }
  // The only sub-10 sizes left are SVG text, whose units are scaled by the chart.
  assert.deepEqual(small.filter((s) => !/charts\.tsx/.test(s)), [])
})

test('font weights come from a four-step scale', () => {
  const bad: string[] = []
  for (const file of [...STYLESHEETS, ...TSX]) {
    for (const m of (file.endsWith('.css') ? code(file) : read(file)).matchAll(/(?:font-weight:|fontWeight:)\s*(\d{3})\b/g)) {
      if (!['400', '500', '600', '700'].includes(m[1])) bad.push(`${rel(file)}: ${m[0]}`)
    }
  }
  assert.deepEqual(bad, [])
})

test('letter-spacing is a token, zero, or one of the named display values', () => {
  const allowed = new Set(['0', '0.02em', '0.16em', '0.22em', '-0.045em', 'normal', 'inherit', '0.002em'])
  const bad: string[] = []
  for (const file of [...STYLESHEETS, ...TSX]) {
    for (const m of (file.endsWith('.css') ? code(file) : read(file)).matchAll(/(?:letter-spacing:\s*|letterSpacing:\s*['"])([^;'"}!]+)/g)) {
      const v = m[1].trim()
      if (v.startsWith('var(--tracking-') || allowed.has(v)) continue
      if (/[{(?:]/.test(v)) continue // computed
      bad.push(`${rel(file)}: letter-spacing ${v}`)
    }
  }
  assert.deepEqual(bad, [])
})

test('border-radius uses the radius tokens, apart from circles, pills and hairlines', () => {
  const bad: string[] = []
  for (const file of STYLESHEETS) {
    for (const m of code(file).matchAll(/border-radius:\s*([^;!}]+)/g)) {
      const v = m[1].trim()
      if (v.includes('var(--r-') || ['50%', '0', '1px', '999px', 'inherit', '0 1px 1px 0'].includes(v)) continue
      if (/^(\d+px\s*){2,4}$/.test(v) || /^(5|10|14)px$/.test(v)) continue // asymmetric and one-off shapes
      bad.push(`${rel(file)}: border-radius ${v}`)
    }
  }
  assert.deepEqual(bad, [])
})

test('transitions use the motion tokens: no literal durations, no bare easing', () => {
  const bad: string[] = []
  for (const file of STYLESHEETS) {
    for (const m of code(file).matchAll(/(?<![-\w])transition:\s*([^;{}]+)/g)) {
      const v = m[1]
      for (const d of v.matchAll(/(?<![\w.-])(\d+)ms\b/g)) {
        if (Number(d[1]) <= 320) bad.push(`${rel(file)}: transition ${v.trim()}`)
      }
      if (/(?<![\w-])(ease|ease-in|ease-out|ease-in-out|linear)(?![\w-])/.test(v) && !/none/.test(v)) bad.push(`${rel(file)}: transition ${v.trim()}`)
    }
  }
  assert.deepEqual([...new Set(bad)], [])
})

test('there is one easing curve: the legacy names are aliases of it', () => {
  const globals = read(join(SRC, 'app', 'globals.css'))
  assert.match(globals, /--ease-state:\s*var\(--ease\)/)
  assert.match(read(join(SRC, 'styles', 'tokens.css')), /--ease-out:\s*var\(--ease\)/)
})

/* A stray parenthesis does not fail a unit test or the type checker; it fails
   the production build, and only if someone runs it. A bulk edit of the
   stylesheets left `var(--t-med))` in six places, which is how this check came
   to exist. Cheap enough to run with everything else. */
test('every declaration in the stylesheets has balanced parentheses', () => {
  const bad: string[] = []
  for (const file of CSS) {
    const text = read(file).replace(/\/\*[\s\S]*?\*\//g, '')
    for (const m of text.matchAll(/([\w-]+)\s*:\s*([^;{}]+)[;}]/g)) {
      const open = (m[2].match(/\(/g) ?? []).length
      const close = (m[2].match(/\)/g) ?? []).length
      if (open !== close) bad.push(`${rel(file)}: ${m[1]}: ${m[2].trim().slice(0, 70)}`)
    }
  }
  assert.deepEqual(bad, [])
})
