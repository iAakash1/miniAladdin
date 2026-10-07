/* A chart is drawn at the size it is shown, so what it says can be read and
   what the pointer touches is what the reader means.

   The plots were laid out in a fixed 640-unit viewBox stretched to
   `width="100%"` inside a fixed height. An SVG keeps its aspect ratio, so a
   panel wider than 640 got the drawing centred with empty bands either side
   while the pointer maths assumed it filled the element — the crosshair
   named a different observation than the one under the cursor. A panel
   narrower than 640 shrank the drawing with its labels: 9px axis text came
   out near 5px on a phone, under the 10px floor the stylesheet enforces for
   every other piece of text. */

import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import test from 'node:test'

const SRC = join(__dirname, '..', 'src')
const CHARTS = readFileSync(join(SRC, 'components', 'system', 'charts.tsx'), 'utf8')

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (/\.tsx?$/.test(name)) out.push(full)
  }
  return out
}

test('no chart is laid out in a fixed-width coordinate space', () => {
  assert.doesNotMatch(CHARTS, /const W = 640/)
  const widths = [...CHARTS.matchAll(/const W = (\w+)/g)].map((m) => m[1])
  assert.ok(widths.length >= 4, 'expected the time series, drawdown, histogram and scatter to set W')
  for (const w of widths) assert.ok(['width', 'canvas'].includes(w) || /gutter/.test(w), `W is "${w}"`)
})

test('every chart that sets W from a measurement attaches the measuring ref', () => {
  const measured = CHARTS.match(/= useChartWidth\(\)/g)?.length ?? 0
  const attached = CHARTS.match(/(?:ref=\{measure\})/g)?.length ?? 0
  assert.equal(measured, 4, 'time series, drawdown, histogram and scatter measure themselves')
  assert.equal(attached, 4, 'each measuring chart attaches the ref to an element')
})

test('the width hook uses a callback ref, so a chart that starts empty still measures', () => {
  assert.match(CHARTS, /const attach = useCallback\(\(el: Element \| null\)/)
  assert.match(CHARTS, /new ResizeObserver\(measure\)/)
  assert.match(CHARTS, /observer\.current\?\.disconnect\(\)/)
})

test('pointer x maps onto the plot with no scaling between them', () => {
  const body = CHARTS.slice(CHARTS.indexOf('const indexAt'), CHARTS.indexOf('return (', CHARTS.indexOf('const indexAt')))
  assert.match(body, /\/ rect\.width\) \* W/)
})

test('axis text is drawn at the type floor, in a single named size', () => {
  assert.doesNotMatch(CHARTS, /fontSize=\{9\}/)
  assert.match(CHARTS, /const AXIS_FONT = 10/)
  assert.ok((CHARTS.match(/fontSize=\{AXIS_FONT\}/g)?.length ?? 0) >= 10)
})

test('no component sets a numeric font size below the 10px floor', () => {
  const offenders: string[] = []
  for (const file of walk(SRC)) {
    const text = readFileSync(file, 'utf8')
    for (const m of text.matchAll(/fontSize[=:]\s*\{?\s*(\d+(?:\.\d+)?)\s*\}?/g)) {
      if (Number(m[1]) < 10) offenders.push(`${relative(SRC, file).split(sep).join('/')}: ${m[0]}`)
    }
  }
  assert.deepEqual(offenders, [])
})

test('a chip sized to its text uses the glyph width of the size it is drawn at', () => {
  assert.doesNotMatch(CHARTS, /\* 5\.[46]\b/)
  assert.match(CHARTS, /const GLYPH = 6\.1/)
})
