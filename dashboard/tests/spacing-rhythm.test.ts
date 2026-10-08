/* Spacing keeps one rhythm: a 4px base, with a deliberate 2px half-step.

   The stylesheets and the inline styles had drifted: 3, 5, 7, 9, 11 and 13px
   padding and gaps sat beside each other and beside the token scale
   (4, 8, 12, 16, 24, 32, 48). None of those odd values was a decision - there
   is always a multiple of 4 one pixel away - they were typed by eye, 142 of
   them, and they are why two adjacent controls would differ by a pixel for no
   reason anyone could give.

   What the product genuinely uses, in CSS and inline alike, is a 2px half-step
   between the 4px stops: 6, 10, 14, 18, 22. That is consistent, it is how the
   dense tables and chips were tuned, and it is kept - as a stated tier, not an
   accident. So the rule is "even", with 1px hairlines allowed:

     multiples of 4      the rhythm
     4n + 2              the optical half-step (6, 10, 14, 18, 22, 26, 30)
     1px                 a hairline offset
     anything odd else   an accident

   The exceptions are drawn geometry - a ring centred by a negative margin of
   half its size, an arrow glyph, a dot grid, an avatar overlap - where the
   number is a property of the shape, not of the layout. */

import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import test from 'node:test'

import { loadAllCss } from './css-scan'

const SRC = join(__dirname, '..', 'src')

const SPACING_PROP = /^(?:padding|margin)(?:-(?:top|right|bottom|left|inline|block)(?:-(?:start|end))?)?$|^(?:gap|row-gap|column-gap)$/

/** Drawn geometry: the value is a property of the shape being drawn. */
const GEOMETRY: Record<string, string> = {
  '.confirmed::after': 'a 26px ring centred by a margin of minus half its size',
  '.sys-btn--go .go-arrow::before': 'the arrow head is drawn with padding',
  '.empty-glyph': 'a 3-dot grid; the gap is the dot pitch',
  '.empty-glyph::before': 'a 3-dot grid; the gap is the dot pitch',
  '.sugg-marks .cmark': 'avatars overlap by a fixed fraction of their size',
}

const isOdd = (n: number) => Math.abs(n) !== 1 && Math.abs(n) % 2 === 1

function* oddPixels(value: string): Generator<number> {
  if (/var\(|calc\(/.test(value)) return
  for (const m of value.matchAll(/(?<![\w.])(-?\d+)px/g)) {
    const n = Number(m[1])
    if (isOdd(n)) yield n
  }
}

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (name.endsWith('.tsx')) out.push(full)
  }
  return out
}

test('no stylesheet padding, margin or gap is an odd number of pixels', () => {
  const offenders: string[] = []
  for (const rule of loadAllCss()) {
    if (rule.keyframes) continue
    if (Object.keys(GEOMETRY).some((g) => rule.selector.includes(g))) continue
    for (const [prop, value] of rule.decls) {
      if (!SPACING_PROP.test(prop)) continue
      for (const n of oddPixels(value)) offenders.push(`${rule.file.split(sep).pop()}:${rule.line} ${rule.selector.slice(0, 50)} { ${prop}: ${value} } (${n}px)`)
    }
  }
  assert.deepEqual(offenders, [], 'odd spacing: snap to the nearest multiple of 4 (or use a token)')
})

test('no inline style sets an odd padding, margin or gap', () => {
  const offenders: string[] = []
  for (const file of walk(SRC)) {
    const text = readFileSync(file, 'utf8')
    for (const style of text.matchAll(/style=\{\{([^}]*)\}\}/g)) {
      for (const decl of style[1].matchAll(/\b(padding|margin|gap|rowGap|columnGap)(Top|Right|Bottom|Left|Inline|Block)?\s*:\s*([^,}\n]+)/g)) {
        const value = decl[3]
        if (/var\(|calc\(/.test(value)) continue
        for (const num of value.matchAll(/(?<![\w.])(-?\d+)(?=\s*(?:px|['"`,\s]|$))/g)) {
          if (isOdd(Number(num[1]))) offenders.push(`${relative(SRC, file).split(sep).join('/')}: ${decl[0].trim()}`)
        }
      }
    }
  }
  assert.deepEqual(offenders, [], 'odd inline spacing: use a multiple of 4, or a token from the scale')
})

test('the exceptions are exactly the drawn geometry, and each still exists', () => {
  const selectors = loadAllCss().map((r) => r.selector)
  for (const g of Object.keys(GEOMETRY)) {
    assert.ok(selectors.some((s) => s.includes(g)), `${g} is excepted but no longer in the stylesheet: remove it from the list`)
  }
})

test('the spacing scale has no gap larger than the one before it doubled', () => {
  const tokens = readFileSync(join(SRC, 'styles', 'tokens.css'), 'utf8')
  const scale = [...tokens.matchAll(/--d-(\d):\s*(\d+)px/g)].map((m) => [Number(m[1]), Number(m[2])]).sort((a, b) => a[0] - b[0])
  assert.deepEqual(scale.map(([, px]) => px), [0, 4, 8, 12, 16, 24, 32, 48])
  for (let i = 2; i < scale.length; i++) assert.ok(scale[i][1] <= scale[i - 1][1] * 2, `--d-${scale[i][0]} jumps more than 2x`)
})
