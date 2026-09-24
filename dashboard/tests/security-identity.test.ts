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

test('every link to a company uses the one canonical route shape', () => {
  // A second shape — /security/AAPL, ?ticker=, ?id=, or the retired
  // /terminal/security?symbol= — is a second identity model arriving by the
  // back door. The one shape is /company/{encoded ticker}.
  const offenders: string[] = []
  for (const f of SOURCES) {
    // Comments discuss routes in prose, and import paths name folders rather
    // than routes. Strip both rather than loosening the pattern, so a real
    // offender inside code is still caught.
    const src = readFileSync(f, 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/\/\/[^\n]*/g, '')
      .replace(/^import[^\n]*$/gm, '')
    for (const m of src.matchAll(/terminal\/security[^`'"\s]*/g)) {
      offenders.push(`${f.replace(ROOT, '')}: ${m[0]} — link to /company/{ticker} instead`)
    }
    for (const m of src.matchAll(/\/company\/(\$\{[^}]*\}?|[A-Za-z0-9.^-]+)/g)) {
      if (m[1].startsWith('${encodeURIComponent(')) continue
      offenders.push(`${f.replace(ROOT, '')}: /company/${m[1]}`)
    }
  }
  assert.deepEqual(offenders, [], `non-canonical company routes:\n  ${offenders.join('\n  ')}`)
})

test('the company route canonicalises the symbol it is given', () => {
  // Lowercase "aapl" from a hand-typed URL must resolve to the same object as
  // "AAPL" from the watchlist — and the retired security route must land on it.
  const page = readFileSync(join(ROOT, 'app/company/[ticker]/page.tsx'), 'utf8')
  assert.match(page, /params\.ticker \?\? ''\)\.toUpperCase\(\)/)
  const retired = readFileSync(join(ROOT, 'app/terminal/security/page.tsx'), 'utf8')
  assert.match(retired, /\.trim\(\)\.toUpperCase\(\)/)
  assert.match(retired, /redirect\(`\/company\/\$\{encodeURIComponent\(symbol\)\}/)
})

test('the local stores key on the canonical ticker', () => {
  // Watchlist and recents are keyed on the ticker alone, uppercased, so a
  // security added from one surface is recognised by every other.
  const symbols = readFileSync(join(ROOT, 'lib/symbols.ts'), 'utf8')
  const uppercased = [...symbols.matchAll(/\.trim\(\)\.toUpperCase\(\)/g)].length
  assert.ok(uppercased >= 3, 'the symbol store does not canonicalise consistently')
})

test('a vendor identifier is never rendered as identity', () => {
  // `via` names which provider resolved the ticker. It was once rendered
  // beside the ticker as though it were the listing venue — "AAPL / finnhub
  // symbol search" — which is a claim about where Apple lists that nothing
  // in the payload supports. The header takes the venue, never the resolver.
  const header = readFileSync(join(ROOT, 'components/company/CompanyHeader.tsx'), 'utf8')
  const workspace = readFileSync(join(ROOT, 'components/company/CompanyWorkspace.tsx'), 'utf8')
  assert.doesNotMatch(header, /\.via\b/, 'the header renders the resolving provider')
  assert.doesNotMatch(workspace, /identity\??\.via/, 'the resolving provider is passed into the header')
  assert.match(header, /venueLabel\(exchange\)/, 'the listing line no longer derives from the venue')
})
