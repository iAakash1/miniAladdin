/* One security, one identity, whichever door you came through.

   A reader reaching AAPL from search, from the watchlist, from a recents
   list, from a sector table, from a paper position or from a comparison must
   arrive at the same object. If two doors produce two identities, the
   watchlist stops recognising what the search opened. */
import { strict as assert } from 'node:assert'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

const ROOT = new URL('../src/', import.meta.url).pathname

const walk = (dir: string): string[] =>
  readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? walk(join(dir, e.name))
      : /\.tsx?$/.test(e.name) ? [join(dir, e.name)] : [])

const SOURCES = [...walk(join(ROOT, 'components')), ...walk(join(ROOT, 'lib'))]

test('every link to a security uses the one canonical route shape', () => {
  // A second shape — /security/AAPL, or ?ticker=, or ?id= — is a second
  // identity model arriving by the back door.
  const offenders: string[] = []
  for (const f of SOURCES) {
    // Comments discuss routes in prose — "pointed at /terminal/security." —
    // and a sentence-ending period is not a route segment. Strip comments
    // rather than loosening the pattern, so a real offender inside code is
    // still caught.
    const src = readFileSync(f, 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/\/\/[^\n]*/g, '')
    for (const m of src.matchAll(/terminal\/security[^`'"\s]*/g)) {
      const href = m[0]
      if (href === 'terminal/security' || href.startsWith('terminal/security?symbol=')) continue
      // An anchor onto the same page is not a different identity.
      if (href.startsWith('terminal/security?symbol=') || href.includes('#sec-')) continue
      offenders.push(`${f.replace(ROOT, '')}: ${href}`)
    }
  }
  assert.deepEqual(offenders, [], `non-canonical security routes:\n  ${offenders.join('\n  ')}`)
})

test('the security route canonicalises the symbol it is given', () => {
  // Lowercase "aapl" from a hand-typed URL must resolve to the same object as
  // "AAPL" from the watchlist.
  const page = readFileSync(join(ROOT, 'app/terminal/security/page.tsx'), 'utf8')
  assert.match(page, /params\.symbol \?\? ''\)\.toUpperCase\(\)/)
})

test('the local stores key on the canonical ticker', () => {
  // Watchlist and recents are keyed on the ticker alone, uppercased, so a
  // security added from one surface is recognised by every other.
  const symbols = readFileSync(join(ROOT, 'lib/symbols.ts'), 'utf8')
  const uppercased = [...symbols.matchAll(/\.trim\(\)\.toUpperCase\(\)/g)].length
  assert.ok(uppercased >= 3, 'the symbol store does not canonicalise consistently')
})

test('a vendor identifier is never rendered as identity', () => {
  // `via` names which provider resolved the ticker. It was briefly rendered
  // beside the ticker as though it were the listing venue — "AAPL / finnhub
  // symbol search" — which is a claim about where Apple lists that nothing
  // in the payload supports.
  const view = readFileSync(join(ROOT, 'components/terminal/security/SecurityView.tsx'), 'utf8')
  assert.match(view, /identitySource/, 'the identity provider is not named as provenance')
  // The listing line may show the venue; it must not show the provider.
  const listing = view.slice(view.indexOf('inst__listing'), view.indexOf('inst__quote'))
  assert.doesNotMatch(listing, /identitySource/,
    'the resolving provider is rendered inside the listing line')
})
