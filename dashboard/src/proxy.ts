import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'
import { NextResponse, type NextFetchEvent, type NextRequest } from 'next/server'

import { buildCsp, clerkFrontendApi, cspHeaderName, cspMode, makeNonce, scriptHash } from '@/lib/csp'
import { THEME_SCRIPT } from '@/lib/theme'

/**
 * Public surface: the marketing site, live news (page + API), the macro
 * readout used on the landing page, auth pages and SEO files.
 * Everything else — the terminal, research/chart APIs, payments — requires auth.
 */
const isPublic = createRouteMatcher([
  '/',
  '/news',
  '/learn(.*)',
  '/api/news(.*)',
  '/api/macro',
  '/api/build',
  '/api/csp-report',
  '/sign-in(.*)',
  '/sign-up(.*)',
  '/sitemap.xml',
  '/robots.txt',
])

/* The hash of the one inline script the app writes. Computed once per isolate. */
let themeHash: Promise<string> | null = null
const themeScriptHash = () => (themeHash ??= scriptHash(THEME_SCRIPT))

/**
 * Attach the Content-Security-Policy.
 *
 * Next stamps a nonce only on markup it renders for a request, and it learns the
 * nonce from that request's CSP header - so the policy is written onto the
 * request forwarded to the page as well as onto the response the browser gets.
 * `CSP_MODE` is `enforce` (the default, and what anything unrecognised means),
 * `report-only` (the browser reports but does not block) or `off`; it exists so
 * an operator can relax the policy with an environment change, not a deploy.
 */
async function withPolicy(request: NextRequest): Promise<NextResponse | undefined> {
  const mode = cspMode(process.env.CSP_MODE)
  const name = cspHeaderName(mode)
  if (!name) return undefined

  const nonce = makeNonce()
  const policy = buildCsp({
    nonce,
    scriptHashes: [await themeScriptHash()],
    clerkFrontendApi: clerkFrontendApi(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY),
    reportUri: '/api/csp-report',
  })

  const forwarded = new Headers(request.headers)
  forwarded.set(name, policy)
  forwarded.set('x-nonce', nonce)
  const response = NextResponse.next({ request: { headers: forwarded } })
  response.headers.set(name, policy)
  return response
}

/**
 * A signed-out request to a protected API route is a 401, as JSON.
 *
 * `auth.protect()` answers it with a 404 rewrite to the not-found page, which
 * hides that the route exists and also tells a browser whose session has simply
 * lapsed that "nothing was found": the interface then said the service holds
 * nothing for the request, when the true and useful answer is "sign in". The
 * body carries no detail beyond that, so the route's existence is no more
 * visible than before - every protected path, real or not, answers the same.
 */
function unauthenticated(): NextResponse {
  return NextResponse.json(
    { detail: 'Sign in required.' },
    { status: 401, headers: { 'Cache-Control': 'no-store', 'WWW-Authenticate': 'Bearer realm="omnisignal"' } },
  )
}

const withClerk = clerkMiddleware(async (auth, req) => {
  if (!isPublic(req)) {
    if (req.nextUrl.pathname.startsWith('/api/')) {
      if (!(await auth()).userId) return unauthenticated()
    } else {
      await auth.protect()
    }
  }
  return withPolicy(req)
})

export default async function proxy(request: NextRequest, event: NextFetchEvent) {
  const response = await withClerk(request, event)
  // A request Clerk answered itself - the 404 it rewrites an unauthorised
  // terminal request to, or a redirect - never reached `withPolicy`. It still
  // gets the header, so no response leaves without one. (A rewritten page has
  // no nonce for its own scripts, and so does not hydrate under it; it is a
  // "not found" page with nothing to hydrate.)
  const name = cspHeaderName(cspMode(process.env.CSP_MODE))
  if (name && response instanceof Response && !response.headers.has(name)) {
    response.headers.set(name, buildCsp({
      nonce: makeNonce(),
      scriptHashes: [await themeScriptHash()],
      clerkFrontendApi: clerkFrontendApi(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY),
      reportUri: '/api/csp-report',
    }))
  }
  return response
}

export const config = {
  matcher: [
    '/((?!_next|api/build|robots\\.txt|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    '/api/((?!build(?:/|$)).*)',
  ],
}
