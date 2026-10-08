# Content Security Policy

The frontend sends a `Content-Security-Policy` on every response (2026-10-08). The
policy is built per request in `dashboard/src/proxy.ts` from
`dashboard/src/lib/csp.ts`, and `dashboard/tests/csp.test.ts` holds it to a closed
list of origins.

## The policy

| Directive | Allows | Why |
|---|---|---|
| `default-src` | `'self'` | Nothing is allowed that is not named |
| `script-src` | `'self'`, a per-response **nonce**, the **hash** of the one inline script the app writes, `'strict-dynamic'`; the Clerk Frontend API host, Cloudflare Turnstile and Razorpay Checkout as CSP2 fallbacks | Next stamps the nonce on its own scripts; the theme bootstrap is allowed by hash; `'strict-dynamic'` lets those trusted scripts load what they need. **No `'unsafe-inline'`, no `'unsafe-eval'`, no wildcard host** |
| `style-src` | `'self'`, `'unsafe-inline'` | React writes `style` attributes into server HTML and Clerk's UI injects `<style>`. Inline *style* is far weaker than inline *script* |
| `img-src` | `'self'`, `data:`, `blob:`, `https:` | The one deliberately broad directive: publishers' own article photographs can be hosted anywhere, and an image cannot run code |
| `font-src` | `'self'`, `data:` | Fonts are self-hosted (`@fontsource`) |
| `connect-src` | `'self'`, the Clerk Frontend API host, Clerk telemetry and avatars, Razorpay's checkout API and telemetry | Every `fetch` the client makes is same-origin (`/api/*` is a server-side proxy); a test fails if a client component starts fetching an absolute URL |
| `frame-src` | `'self'`, Cloudflare Turnstile, Razorpay | Clerk's bot check; the checkout frame |
| `worker-src` | `'self'`, `blob:` | Clerk |
| `object-src` / `base-uri` / `frame-ancestors` | `'none'` / `'self'` / `'none'` | No plugins; the base URL cannot be rewritten; the page cannot be framed |
| `form-action` | `'self'`, Razorpay's API | Checkout's redirect flow |
| `report-uri` | `/api/csp-report` | Violations are logged (`csp-violation`, query strings stripped) |

The Clerk host is read from the publishable key at request time, so moving to a
production Clerk instance (see `CLERK_PRODUCTION.md`) needs no edit here.

## Why every page is rendered per request

A nonce is fresh for each response, and Next can stamp one only on markup it renders
for that request. A prerendered page is the same bytes for everyone, so its inline
bootstrap scripts could not carry one and the policy would have to allow any inline
script - the thing a script policy exists to refuse. The marketing and learning
pages were the only static routes; the root layout now sets
`export const dynamic = 'force-dynamic'`.

For the same reason every `<ClerkProvider>` goes through
`components/auth/NonceClerkProvider.tsx`: Clerk writes its SDK as a plain
`<script src>` into the server HTML, and under `'strict-dynamic'` such a script runs
only if it carries the nonce. (This was found by fetching `/sign-in` and reading
the markup: without the wrapper that script had no nonce and would have been
blocked.) A test fails if `ClerkProvider` is used directly.

## Operating it

`CSP_MODE` (Vercel environment variable):

| Value | Effect |
|---|---|
| `enforce` (default; any unrecognised value also enforces) | The browser blocks what the policy forbids |
| `report-only` | The browser reports violations but blocks nothing. Use this to relax the policy if a legitimate resource turns out to be refused, then fix the policy |
| `off` | No policy |

An environment change applies to the next deployment; Vercel's instant rollback
restores the previous deployment immediately.

`next dev` is the one exception to "no `unsafe-eval`": React rebuilds call stacks with
`eval` in development, so a development server (and only `NODE_ENV=development`) adds
`'unsafe-eval'` and omits `upgrade-insecure-requests`. Everything else in the policy is the
production policy, a test holds that, and a production build never sets the flag.

To see what the policy is refusing, search the Vercel runtime logs for
`csp-violation`. Each line carries the blocked URL (origin and path only), the
violated directive and the page.

## What was verified, and what was not

Verified over HTTP against a production build: every HTML route sends the header;
the nonce is 128 bits and differs per request; every external script in the
served HTML of `/`, `/news`, `/learn`, `/sign-in` and `/sign-up` carries it; the
only inline script without one is the theme bootstrap, and the SHA-256 of its
served text equals the hash in the header; there is no `'unsafe-eval'` and no
wildcard script host; the report endpoint accepts a valid report and refuses
oversized, mistyped and malformed bodies.

**Not verified: behaviour in a real browser under enforcement.** Hydration, the
Clerk sign-in flow and the Razorpay checkout depend on the browser honouring
`'strict-dynamic'` for scripts Next and Clerk insert at runtime. That is how the
specification works and how the Clerk and Next documentation describe their
integrations, but it has not been exercised here. After a deploy, open the site,
sign in, load a company page and open the upgrade dialog; if anything fails, set
`CSP_MODE=report-only`, redeploy, and read the `csp-violation` log lines.
