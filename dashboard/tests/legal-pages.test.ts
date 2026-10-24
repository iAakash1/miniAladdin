/* The legal pages: reachable without signing in, linked from where a visitor
   looks for them, and free of invented facts.

   The pages are only as good as their claims, so the claims that are easiest
   to get wrong are checked against the code: the FRED notice is the backend's
   wording, the routes are public, and no contact address, company or
   governing law appears that the project has not actually established. */
import { strict as assert } from 'node:assert'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

import { FRED_NOTICE, LEGAL_LAST_UPDATED, legalDate } from '../src/lib/legal'

const ROOT = join(__dirname, '..')
const SRC = join(ROOT, 'src')
const read = (...p: string[]) => readFileSync(join(...p), 'utf8')
const terms = read(SRC, 'app', '(site)', 'terms', 'page.tsx')
const privacy = read(SRC, 'app', '(site)', 'privacy', 'page.tsx')

test('both pages exist under the public site layout and name themselves', () => {
  for (const page of ['terms', 'privacy']) {
    assert.ok(existsSync(join(SRC, 'app', '(site)', page, 'page.tsx')), page)
  }
  assert.match(terms, /title: 'Terms and Conditions'/)
  assert.match(privacy, /title: 'Privacy notice'/)
})

test('they are public, listed in the sitemap, and linked from the footer and the sign-in screen', () => {
  const proxy = read(SRC, 'proxy.ts')
  assert.match(proxy, /'\/terms',\s*'\/privacy',/)
  const sitemap = read(SRC, 'app', 'sitemap.ts')
  assert.match(sitemap, /\/terms`/)
  assert.match(sitemap, /\/privacy`/)
  const footer = read(SRC, 'components', 'marketing', 'SiteFooter.tsx')
  assert.match(footer, /href: '\/terms'/)
  assert.match(footer, /href: '\/privacy'/)
  const auth = read(SRC, 'components', 'marketing', 'AuthShell.tsx')
  assert.match(auth, /href="\/terms"/)
  assert.match(auth, /href="\/privacy"/)
})

test('every in-page link points at a section that exists', () => {
  const ids = (src: string) => new Set([...src.matchAll(/id: '([a-z-]+)'/g)].map((m) => m[1]))
  const termsIds = ids(terms)
  const privacyIds = ids(privacy)
  for (const [, page, anchor] of [...terms.matchAll(/href="\/(terms|privacy)#([a-z-]+)"/g), ...privacy.matchAll(/href="\/(terms|privacy)#([a-z-]+)"/g)]) {
    assert.ok((page === 'terms' ? termsIds : privacyIds).has(anchor), `/${page}#${anchor}`)
  }
  const footer = read(SRC, 'components', 'marketing', 'SiteFooter.tsx')
  for (const [, anchor] of footer.matchAll(/href="\/terms#([a-z-]+)"/g)) assert.ok(termsIds.has(anchor), anchor)
})

test('the terms carry the clauses the project depends on', () => {
  for (const phrase of [
    /independently developed, experimental software and financial-research project/,
    /not investment advice/i,
    /does not claim ownership of third-party material/,
    /does not by itself give you a right to copy, redistribute/,
    /No return, level of accuracy, risk reduction, predictive performance or investment outcome is guaranteed/,
    /Nothing in these Terms excludes or limits any liability that cannot be excluded/,
  ]) assert.match(terms.replace(/\s+/g, ' '), phrase)
})

test('no invented contact, entity, jurisdiction or placeholder', () => {
  for (const [name, src] of [['terms', terms], ['privacy', privacy]] as const) {
    assert.doesNotMatch(src, /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}/, `${name}: an email address nobody has published`)
    assert.doesNotMatch(src, /\b(Inc\.|LLC|Ltd\.?|Pvt\.?|Private Limited|GmbH)\b/, `${name}: a legal entity that does not exist`)
    assert.doesNotMatch(src, /governed by the laws of|exclusive jurisdiction/i, `${name}: a governing-law choice the owner has not made`)
    assert.doesNotMatch(src, /\b(TODO|TBD|lorem|ipsum|\[company\]|\[address\]|example\.com)\b/i, `${name}: a placeholder`)
    assert.doesNotMatch(src, /\bwe guarantee\b|\bguaranteed (returns?|accuracy|profits?)\b/i, `${name}: a guarantee`)
    assert.doesNotMatch(src, /\bindemnif/i, `${name}: an indemnity nobody has reviewed`)
  }
})

test('the FRED notice is the wording the backend catalog carries, and the footer shows it', () => {
  const catalog = read(ROOT, '..', 'src', 'providers', 'catalog.py')
  const flat = catalog.replace(/"\s*\n\s*"/g, '')
  assert.ok(flat.includes(FRED_NOTICE), 'src/providers/catalog.py FRED_NOTICE differs')
  assert.match(read(SRC, 'components', 'marketing', 'SiteFooter.tsx'), /\{FRED_NOTICE\}/)
  assert.match(terms, /\{FRED_NOTICE\}/)
})

test('the last-updated date is a real calendar date and is printed in words', () => {
  assert.match(LEGAL_LAST_UPDATED, /^\d{4}-\d{2}-\d{2}$/)
  assert.ok(!Number.isNaN(Date.parse(`${LEGAL_LAST_UPDATED}T00:00:00Z`)))
  assert.equal(legalDate('2026-10-25'), 'October 25, 2026')
})
