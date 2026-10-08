/* An effect that fetches and then sets state must be able to tell its answer is
   no longer wanted.

   The sessions search applied every reply as it arrived. Type "ab", then "abc":
   the reply for "ab" can land second, and the list shows matches for a word the
   box no longer holds. Nothing looks wrong, which is the problem. Every other
   effect in the app already carries a flag, a sequence number or an abort signal;
   this keeps it that way by failing the build on the next one that does not. */

import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import test from 'node:test'

const SRC = join(__dirname, '..', 'src')

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (name.endsWith('.tsx')) out.push(full)
  }
  return out
}

/** The text of each `useEffect(() => { ... })` callback. */
function effects(text: string): Array<{ body: string; line: number }> {
  const found: Array<{ body: string; line: number }> = []
  for (const m of text.matchAll(/useEffect\(\(\) => \{/g)) {
    let depth = 1
    let i = (m.index ?? 0) + m[0].length
    while (i < text.length && depth > 0) {
      if (text[i] === '{') depth++
      else if (text[i] === '}') depth--
      i++
    }
    found.push({ body: text.slice(m.index, i), line: text.slice(0, m.index).split('\n').length })
  }
  return found
}

const FETCHES = /\b(fetch\(|readResource|authFetch|fetch[A-Z]\w*\(|search\w*\(|list\w*\()/
const APPLIES = /\bset[A-Z]\w*\(/
const AWAITS = /\.then\(|await /
const GUARDED = /\b(alive|live|cancelled|canceled|ignore|stale|mounted|aborted|active|current)\b|AbortController|signal|inFlight|seq\b/

test('every effect that fetches and sets state carries a staleness guard', () => {
  const unguarded: string[] = []
  for (const file of walk(SRC)) {
    for (const { body, line } of effects(readFileSync(file, 'utf8'))) {
      if (FETCHES.test(body) && APPLIES.test(body) && AWAITS.test(body) && !GUARDED.test(body)) {
        unguarded.push(`${relative(SRC, file).split(sep).join('/')}:${line} ${body.replace(/\s+/g, ' ').slice(0, 90)}`)
      }
    }
  }
  assert.deepEqual(unguarded, [], 'a reply can arrive after it stopped being wanted: add an `alive` flag, a sequence, or an AbortController')
})
