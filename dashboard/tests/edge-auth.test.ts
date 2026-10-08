/* A signed-out API call is a 401 with a JSON body, not a "not found" page.

   `auth.protect()` answers an unauthenticated request with a 404 rewrite to the
   HTML not-found page. That hides that a route exists, but it also tells a tab
   whose session has simply lapsed that nothing was found, so the interface said
   "the service holds nothing for this request" instead of "sign in". The proxy
   now answers protected `/api/*` calls itself, with the same body for every
   path, real or invented, so route existence is no more visible than before. */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

import { describeFailure } from '../src/lib/failure'
import { ResourceError } from '../src/lib/resource'

const SRC = join(__dirname, '..', 'src')
const proxy = readFileSync(join(SRC, 'proxy.ts'), 'utf8')

test('a signed-out request to a protected API route is a 401 answered by the proxy', () => {
  assert.match(proxy, /if \(req\.nextUrl\.pathname\.startsWith\('\/api\/'\)\) \{\s*if \(!\(await auth\(\)\)\.userId\) return unauthenticated\(\)/)
  assert.match(proxy, /status: 401/)
  assert.match(proxy, /'WWW-Authenticate': 'Bearer realm="omnisignal"'/)
  assert.match(proxy, /'Cache-Control': 'no-store'/, 'a 401 must never be cached and replayed to a signed-in user')
})

test('the 401 body is the same for every path and says nothing about the route', () => {
  const body = /NextResponse\.json\(\s*(\{[^}]*\})/.exec(proxy)?.[1] ?? ''
  assert.equal(body.replace(/\s+/g, ' '), "{ detail: 'Sign in required.' }")
})

test('pages are still protected by Clerk, which redirects a document request to sign-in', () => {
  assert.match(proxy, /\} else \{\s*await auth\.protect\(\)/)
})

test('the public routes are unchanged and the report endpoint is among them', () => {
  const list = /createRouteMatcher\(\[([\s\S]*?)\]\)/.exec(proxy)?.[1] ?? ''
  const entries = [...list.matchAll(/'([^']+)'/g)].map((m) => m[1])
  assert.deepEqual(entries, [
    '/', '/news', '/learn(.*)', '/api/news(.*)', '/api/macro', '/api/build', '/api/csp-report',
    '/sign-in(.*)', '/sign-up(.*)', '/sitemap.xml', '/robots.txt',
  ])
})

test('the interface says "sign in" for a 401 and does not say "nothing found"', () => {
  const failure = describeFailure(new ResourceError('/api/watchlists', 401, 'Sign in required.'), 'watchlists')
  assert.equal(failure.title, 'Sign-in required')
  assert.doesNotMatch(failure.detail, /holds nothing|No .* found/i)
  const missing = describeFailure(new ResourceError('/api/x', 404, 'missing'), 'thing')
  assert.match(missing.title, /No thing found/)
})

test('a research run that ended on a 401 or a 503 is not described as an unknown symbol', () => {
  const state = readFileSync(join(SRC, 'components', 'company', 'SignalState.tsx'), 'utf8')
  assert.match(state, /run\.code === 404 \? 'No provider recognized this symbol\.'/)
  assert.match(state, /run\.code === 401 \? 'Your session ended/)
  assert.match(state, /run\.code === 503 \? 'The price providers did not answer\. This is an outage, not a missing symbol\./)
})
