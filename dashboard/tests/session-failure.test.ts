/* A failed read of your investigations is not "you have none".

   `listSessions` and `searchSessions` swallowed a failed response into `[]` and
   `{ sessions: [], notes: [] }` - the exact answers to "no investigations yet"
   and "nothing matches". The screen's own failure branch (`setFailed(true)`) sat
   behind a `.catch` that therefore could never run, so an outage showed the
   first-run empty state. And a failed search left the results null, which the
   screen reads as "still searching". Separately, search replies were applied
   without checking they were still wanted, so a slow answer for "ab" could land
   after the answer for "abc". */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

const SRC = join(__dirname, '..', 'src')
const read = (...p: string[]) => readFileSync(join(SRC, ...p), 'utf8')

test('a failed sessions request throws, so the caller can say so', () => {
  const lib = read('lib', 'sessions.ts')
  const list = /export async function listSessions[\s\S]*?\n\}/.exec(lib)?.[0] ?? ''
  const search = /export async function searchSessions[\s\S]*?\n\}/.exec(lib)?.[0] ?? ''
  for (const [name, body] of [['listSessions', list], ['searchSessions', search]] as const) {
    assert.match(body, /if \(!res\.ok\) throw new Error/, `${name} does not throw on a failed response`)
    assert.doesNotMatch(body, /if \(!res\.ok\) return/, `${name} still returns data for a failed response`)
  }
})

test('the view has a failure state for the list and a different one for search', () => {
  const view = read('components', 'terminal', 'SessionsView.tsx')
  assert.match(view, /\.catch\(\(\) => setFailed\(true\)\)/)
  assert.match(view, /const \[searchFailed, setSearchFailed\] = useState\(false\)/)
  assert.match(view, /searchFailed \? 'search unavailable'/)
})

test('a search reply is applied only while its query is still the one in the box', () => {
  const view = read('components', 'terminal', 'SessionsView.tsx')
  const effect = /useEffect\(\(\) => \{\s*const term = query\.trim\(\)[\s\S]*?\}, \[query\]\)/.exec(view)?.[0] ?? ''
  assert.match(effect, /let alive = true/)
  assert.match(effect, /if \(alive\) setHits\(found\)/)
  assert.match(effect, /return \(\) => \{ alive = false; clearTimeout\(timer\) \}/)
})

test('an investigation whose contents were not read is never described as empty', () => {
  const view = read('components', 'terminal', 'SessionsView.tsx')
  // Three cases the screen used to fold into one: read and empty, read failed, not asked for.
  assert.match(view, /Record<string, Substance \| null>/)
  assert.match(view, /full \? readSubstance\(full\) : null/)
  assert.doesNotMatch(view, /readSubstance\(full\) : EMPTY/)
  assert.match(view, /if \(s === null\) return \{ tone: 'muted', label: 'Not loaded' \}/)
  assert.match(view, /read === null\s*\?\s*<span className="ws-card__blank">Contents not loaded/)
  // The "Empty" claim is reachable only for contents that were read.
  assert.doesNotMatch(view, /\? EMPTY : EMPTY|detail\[s\.id\] \?\? EMPTY/)
})
