/* Text is readable on every surface it is set on, in both themes.

   Computed from the token file, so a colour change that breaks contrast fails
   here and not in a review. Found by this check: dark-theme text selection was
   white on the blue accent (2.9:1); the landing page's primary button set
   near-black text on the mid-blue light accent (3.4:1); the company-page
   disclaimer and the build id in the status bar used the disabled ink
   (2.1 to 2.9:1); and the light theme's faint ink and warning amber sat just
   under 4.5:1 on its sunken and hover surfaces. */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

const SRC = join(__dirname, '..', 'src')
const strip = (s: string) => s.replace(/\/\*[\s\S]*?\*\//g, '')
const TOKENS = strip(readFileSync(join(SRC, 'styles', 'tokens.css'), 'utf8'))
const SYSTEM = strip(readFileSync(join(SRC, 'styles', 'system.css'), 'utf8'))
const GLOBALS = strip(readFileSync(join(SRC, 'app', 'globals.css'), 'utf8'))

function block(selector: RegExp): string {
  const m = selector.exec(TOKENS)
  assert.ok(m, `no block for ${selector}`)
  let depth = 1
  let i = m.index + m[0].length
  while (depth) { const c = TOKENS[i++]; depth += (c === '{' ? 1 : 0) - (c === '}' ? 1 : 0) }
  return TOKENS.slice(m.index + m[0].length, i - 1)
}
const declarations = (b: string) => Object.fromEntries([...b.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]))

const DARK = declarations(block(/:root\s*\{/))
const LIGHT = { ...DARK, ...declarations(block(/:root\[data-theme='light'\]\s*\{/)) }

function resolve(theme: Record<string, string>, name: string, depth = 0): string | undefined {
  const v = theme[name]
  if (v === undefined || depth > 8) return undefined
  const ref = /^var\((--[\w-]+)\)$/.exec(v)
  return ref ? resolve(theme, ref[1], depth + 1) : v
}

type RGBA = { rgb: [number, number, number]; a: number }
function parse(v: string | undefined): RGBA | undefined {
  if (!v) return undefined
  const hex = /^#([0-9a-f]{3,8})$/i.exec(v)
  if (hex) {
    let h = hex[1]
    if (h.length <= 4) h = [...h].map((c) => c + c).join('')
    return { rgb: [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as [number, number, number], a: h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1 }
  }
  const fn = /^rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$/.exec(v)
  if (fn) {
    const a = fn[4] === undefined ? 1 : fn[4].endsWith('%') ? parseFloat(fn[4]) / 100 : parseFloat(fn[4])
    return { rgb: [Number(fn[1]), Number(fn[2]), Number(fn[3])], a }
  }
  return undefined
}
const channel = (x: number) => { const c = x / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4 }
const luminance = ([r, g, b]: number[]) => 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
function contrast(fg: RGBA, bg: RGBA): number {
  const top = fg.a < 1 ? fg.rgb.map((c, i) => Math.round(c * fg.a + bg.rgb[i] * (1 - fg.a))) : fg.rgb
  const [a, b] = [luminance(top), luminance(bg.rgb)].sort((x, y) => y - x)
  return (a + 0.05) / (b + 0.05)
}
const color = (theme: Record<string, string>, name: string) => {
  const c = parse(resolve(theme, name))
  assert.ok(c, `${name} does not resolve to a colour`)
  return c
}

const SURFACES = ['--p-base', '--p-panel', '--p-raised', '--p-sunken', '--p-hover', '--p-overlay']
const TEXT = ['--ink', '--ink-muted', '--ink-faint', '--accent', '--accent-strong', '--e-pos', '--e-neg', '--e-warn', '--e-null']

for (const [name, theme] of [['dark', DARK], ['light', LIGHT]] as const) {
  test(`${name} theme: every text colour clears 4.5:1 on every surface`, () => {
    const low: string[] = []
    for (const t of TEXT) for (const s of SURFACES) {
      const ratio = contrast(color(theme, t), color(theme, s))
      if (ratio < 4.5) low.push(`${t} on ${s}: ${ratio.toFixed(2)}`)
    }
    assert.deepEqual(low, [])
  })

  test(`${name} theme: text set on an accent fill clears 4.5:1`, () => {
    assert.ok(contrast(color(theme, '--on-accent'), color(theme, '--accent')) >= 4.5)
  })
}

test('the disabled ink is only used for things that are disabled or decorative', () => {
  // It is 2.1 to 2.9:1 by design. As the colour of text a reader needs, it is a defect.
  const readable = /(?:^|\n)([^{}]*)\{[^{}]*\bcolor:\s*var\(--ink-disabled\)[^{}]*\}/g
  const offenders = [...(SYSTEM + GLOBALS).matchAll(readable)].map((m) => m[1].trim().replace(/\s+/g, ' '))
    .filter((sel) => !/(:disabled|\[disabled\]|\[aria-disabled|__sep|::before|::after|__none|\.sys-null)/.test(sel))
  assert.deepEqual(offenders, [])
})

test('no rule hard-codes the colour of text on an accent fill', () => {
  const bad = [...(SYSTEM + GLOBALS).matchAll(/([^{}]+)\{[^{}]*background:\s*var\(--accent\)[^{}]*\bcolor:\s*#[0-9a-f]{3,8}[^{}]*\}/gi)]
    .map((m) => m[1].trim().replace(/\s+/g, ' '))
  assert.deepEqual(bad, [])
  assert.match(GLOBALS, /::selection\s*\{[^}]*color:\s*var\(--on-accent\)/)
})
