/* Switching securities must never leave the previous one's data on screen.

   Every panel on the security route fetches on its own clock — the research
   fan-out takes half a minute while the price returns in under a second — so
   a reader who opens AAPL and then MSFT has several requests in flight for a
   symbol they have navigated away from. An answer that lands without being
   checked against the symbol currently on screen renders AAPL's revenue under
   MSFT's name, and nothing about it looks wrong.

   The fix used throughout is to tag each answer with the symbol it answers
   and compare at render, so a stale answer is structurally not current rather
   than merely cancelled. This asserts every fetching panel does it, because
   the guard is only worth having if it applies to the next panel too. */
import { strict as assert } from 'node:assert'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

const ROOT = new URL('../src/', import.meta.url).pathname
const PAGE = readFileSync(join(ROOT, 'app/terminal/security/page.tsx'), 'utf8')
const DIR = join(ROOT, 'components/terminal/security')

/** Panels the security route actually mounts, read from the route itself. */
const mounted = readdirSync(DIR)
  .filter((f) => f.endsWith('.tsx'))
  .filter((f) => new RegExp(`from '@/components/terminal/security/${f.replace(/\.tsx$/, '')}'`).test(PAGE))

test('the route mounts the panels this guard expects', () => {
  // If the route stops importing these, the assertions below go vacuous.
  assert.ok(mounted.length >= 8, `only ${mounted.length} panels resolved from the route`)
})

for (const file of mounted) {
  const src = readFileSync(join(DIR, file), 'utf8')
  const fetches = /useEffect\(/.test(src) && /(fetchResearch|readResource|fetch\w*\()/.test(src)
  if (!fetches) continue

  test(`${file} tags its answer with the symbol it answers`, () => {
    assert.match(src, /\bfor:\s*symbol\b/,
      `${file} stores an answer without recording which symbol it is for`)
    assert.match(src, /\.for\s*===\s*symbol/,
      `${file} does not check the answer against the symbol currently on screen`)
  })

  test(`${file} drops a reply that lands after unmount`, () => {
    assert.ok(/alive = false/.test(src) || /cancelled = true/.test(src),
      `${file} has no teardown guard, so a late reply sets state on an unmounted panel`)
  })
}

test('a panel that fetches nothing needs no tag', () => {
  /* SecurityResearch is a set of links derived from the symbol prop. It has
     no state and no request, so there is nothing to go stale — asserted so
     the guard above is not read as covering it by omission. */
  const src = readFileSync(join(DIR, 'SecurityResearch.tsx'), 'utf8')
  assert.doesNotMatch(src, /useEffect|useState/, 'SecurityResearch now holds state and is unguarded')
})
