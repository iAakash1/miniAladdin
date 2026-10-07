/* A figure reads the same whoever is looking at it.

   The shared formatters name their locale ('en-US'), but nineteen call sites
   used `toLocaleString()` and three used `Intl.NumberFormat(undefined)`, which
   take the viewer's. The same count printed "1,234,567" on one screen and
   "12,34,567" on another for a reader whose browser is set to en-IN, and a
   date rendered in the reader's own time zone beside timestamps that are all
   UTC. Where the page is rendered on the server first, the server's locale
   and the browser's also disagree, which is what a hydration warning is. */

import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
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

const hits = (pattern: RegExp) => {
  const found: string[] = []
  for (const file of walk(SRC)) {
    const text = readFileSync(file, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
    for (const m of text.matchAll(pattern)) found.push(`${relative(SRC, file).split(sep).join('/')}: ${m[0]}`)
  }
  return found
}

test('no number or date is formatted in the viewer\'s locale', () => {
  assert.deepEqual(hits(/\.toLocale(?:Date|Time)?String\(\s*(?:undefined\s*|\[\]\s*)?[,)]/g), [])
  assert.deepEqual(hits(/Intl\.(?:NumberFormat|DateTimeFormat)\(\s*undefined/g), [])
})

test('a system health check time is shown in UTC, like every other timestamp', () => {
  const board = readFileSync(join(SRC, 'components', 'terminal', 'system', 'SystemHealthBoard.tsx'), 'utf8')
  assert.match(board, /formatTimestamp\(health\.checked_at\)\} UTC/)
})
