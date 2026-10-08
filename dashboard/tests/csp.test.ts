/* The Content-Security-Policy is a value, and the value is held to a closed list.

   A policy is only as strong as the hosts it names, and each host is added for a
   reason that is forgotten by the time it matters. So the allowlist is written
   out here, origin by origin, with what each is for; adding one means changing
   this file and saying why, and a wildcard script source, `'unsafe-eval'` or an
   inline-script allowance cannot appear without a failing test. */

import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

import { buildCsp, clerkFrontendApi, cspHeaderName, cspMode, makeNonce, scriptHash } from '../src/lib/csp'
import { THEME_SCRIPT } from '../src/lib/theme'

const SRC = join(__dirname, '..', 'src')
const read = (...p: string[]) => readFileSync(join(SRC, ...p), 'utf8')

const NONCE = 'abcDEF123+/456ghiJKL=='
const HOST = 'example-app-12.clerk.accounts.dev'
const policy = (over: Partial<Parameters<typeof buildCsp>[0]> = {}) =>
  buildCsp({ nonce: NONCE, scriptHashes: ['sha256-AAAA'], clerkFrontendApi: HOST, ...over })
const directive = (name: string, text = policy()) =>
  (text.split('; ').find((d) => d.startsWith(`${name} `)) ?? '').split(' ').slice(1)

// ── the Clerk host comes from the key ────────────────────────────────────────

test('the Clerk Frontend API host is read from the publishable key', () => {
  const key = (host: string, kind = 'test') => `pk_${kind}_${Buffer.from(`${host}$`).toString('base64').replace(/=+$/, '')}`
  assert.equal(clerkFrontendApi(key('example-app-12.clerk.accounts.dev')), 'example-app-12.clerk.accounts.dev')
  assert.equal(clerkFrontendApi(key('clerk.omnisignal.example', 'live')), 'clerk.omnisignal.example', 'a production custom domain follows the key')
})

test('a key that does not parse yields no host rather than a guessed one', () => {
  for (const bad of [undefined, '', 'sk_test_abc', 'pk_test_', 'pk_test_!!!', `pk_test_${Buffer.from('not a host$').toString('base64')}`]) {
    assert.equal(clerkFrontendApi(bad), null, String(bad))
  }
  assert.ok(!policy({ clerkFrontendApi: null }).includes('clerk.accounts.dev'))
})

// ── the policy ───────────────────────────────────────────────────────────────

test('scripts are allowed by nonce and hash, and strict-dynamic carries what they load', () => {
  const scripts = directive('script-src')
  assert.ok(scripts.includes(`'nonce-${NONCE}'`))
  assert.ok(scripts.includes("'sha256-AAAA'"))
  assert.ok(scripts.includes("'strict-dynamic'"))
})

test('there is no unsafe-eval, no inline-script allowance and no wildcard script host', () => {
  const text = policy()
  assert.doesNotMatch(text, /unsafe-eval|wasm-unsafe-eval/)
  assert.ok(!directive('script-src').includes("'unsafe-inline'"), 'scripts may run inline without a nonce')
  assert.ok(!directive('script-src').some((s) => s === '*' || s === 'https:' || s === 'http:' || s.includes('*')))
  assert.ok(!directive('connect-src').some((s) => s === '*' || s === 'https:' || s === 'http:'))
  assert.ok(!directive('frame-src').some((s) => s === '*' || s === 'https:' || s.includes('*')))
})

test('the page cannot be framed, embedded as an object, or have its base rewritten', () => {
  assert.deepEqual(directive('frame-ancestors'), ["'none'"])
  assert.deepEqual(directive('object-src'), ["'none'"])
  assert.deepEqual(directive('base-uri'), ["'self'"])
  assert.deepEqual(directive('default-src'), ["'self'"])
})

test('every non-self origin the policy names is on the closed, explained list', () => {
  const EXPLAINED: Record<string, string> = {
    [`https://${HOST}`]: 'Clerk Frontend API: the browser SDK and its requests (from the publishable key)',
    'https://challenges.cloudflare.com': 'Cloudflare Turnstile, which Clerk adds for bot protection',
    'https://checkout.razorpay.com': 'Razorpay Checkout script and frame, loaded when the upgrade dialog opens',
    'https://api.razorpay.com': 'Razorpay checkout API, frame and redirect form',
    'https://lumberjack.razorpay.com': 'Razorpay checkout telemetry',
    'https://clerk-telemetry.com': 'Clerk SDK telemetry on development instances',
    'https://*.clerk-telemetry.com': 'Clerk SDK telemetry on development instances',
    'https://img.clerk.com': 'Clerk user avatars',
  }
  const named = new Set<string>()
  for (const part of policy().split('; ')) {
    for (const source of part.split(' ').slice(1)) if (/^https:\/\//.test(source)) named.add(source)
  }
  assert.deepEqual([...named].filter((o) => !(o in EXPLAINED)), [], 'an origin is allowed with no stated reason')
  assert.deepEqual(Object.keys(EXPLAINED).filter((o) => !named.has(o)), [], 'an explained origin is no longer in the policy')
})

test('images are the one deliberately broad directive, and nothing else is', () => {
  // Publishers' own photographs can be hosted anywhere, and an image cannot run code.
  assert.ok(directive('img-src').includes('https:'))
  for (const name of ['script-src', 'style-src', 'font-src', 'connect-src', 'frame-src', 'worker-src', 'manifest-src', 'form-action']) {
    assert.ok(!directive(name).includes('https:'), `${name} allows every HTTPS host`)
  }
})

test('every fetch the client makes is same-origin, which is why connect-src needs no third party for the app', () => {
  // The audit behind the connect-src list: no client component names an
  // absolute URL to fetch. If one starts to, it needs an origin here and a line
  // in the explained list above.
  const offenders: string[] = []
  const walk = (dir: string): string[] => {
    return readdirSync(dir).flatMap((n: string) => {
      const full = join(dir, n)
      return statSync(full).isDirectory() ? walk(full) : /\.tsx?$/.test(n) ? [full] : []
    })
  }
  for (const file of walk(SRC)) {
    const text = readFileSync(file, 'utf8')
    if (!/^['"]use client['"]/m.test(text.slice(0, 200))) continue
    for (const m of text.matchAll(/\bfetch\(\s*[`'"](https?:\/\/[^`'"]+)/g)) offenders.push(`${file.slice(SRC.length + 1)}: ${m[1]}`)
  }
  assert.deepEqual(offenders, [])
})

// ── nonce, hash, mode ────────────────────────────────────────────────────────

test('a nonce is 128 random bits and differs every time', () => {
  const a = makeNonce()
  const b = makeNonce()
  assert.notEqual(a, b)
  assert.equal(Buffer.from(a, 'base64').length, 16)
  assert.doesNotMatch(a, /[<>&'" ]/, 'a nonce must survive being written into an attribute and a header')
})

test('the script hash is the SHA-256 of the exact text', async () => {
  const expected = `sha256-${createHash('sha256').update(THEME_SCRIPT).digest('base64')}`
  assert.equal(await scriptHash(THEME_SCRIPT), expected)
})

test('the root layout renders exactly the script whose hash the policy carries, and renders per request', () => {
  const layout = read('app', 'layout.tsx')
  assert.match(layout, /import \{ THEME_COLOR, THEME_SCRIPT \} from '@\/lib\/theme'/)
  assert.equal((layout.match(/dangerouslySetInnerHTML=\{\{ __html: THEME_SCRIPT \}\}/g) ?? []).length, 1)
  assert.equal((layout.match(/dangerouslySetInnerHTML/g) ?? []).length, 1, 'another inline script exists that the policy does not allow')
  assert.match(layout, /export const dynamic = 'force-dynamic'/, 'a prerendered page cannot carry a per-request nonce')
  assert.match(read('proxy.ts'), /scriptHashes: \[await themeScriptHash\(\)\]/)
})

test('an unrecognised CSP_MODE enforces; only the two named relaxations relax', () => {
  for (const v of [undefined, '', 'enforce', 'ENFORCE', 'true', 'yes', 'on', 'strict', 'report only']) assert.equal(cspMode(v), 'enforce', String(v))
  assert.equal(cspMode('report-only'), 'report-only')
  assert.equal(cspMode(' OFF '), 'off')
  assert.equal(cspHeaderName('enforce'), 'Content-Security-Policy')
  assert.equal(cspHeaderName('report-only'), 'Content-Security-Policy-Report-Only')
  assert.equal(cspHeaderName('off'), null)
})

// ── wiring ───────────────────────────────────────────────────────────────────

test('the proxy hands Next the nonce on the request and the browser the policy on the response', () => {
  const proxy = read('proxy.ts')
  assert.match(proxy, /forwarded\.set\(name, policy\)/)
  assert.match(proxy, /forwarded\.set\('x-nonce', nonce\)/)
  assert.match(proxy, /NextResponse\.next\(\{ request: \{ headers: forwarded \} \}\)/)
  assert.match(proxy, /response\.headers\.set\(name, policy\)/)
  assert.match(proxy, /'\/api\/csp-report',\n\s+'\/sign-in/, 'the violation report endpoint is behind authentication, so browsers could never reach it')
})

test('every response Clerk answers itself still carries a policy', () => {
  const proxy = read('proxy.ts')
  assert.match(proxy, /export default async function proxy\(/)
  assert.match(proxy, /if \(name && response instanceof Response && !response\.headers\.has\(name\)\)/)
})

test('no component mounts ClerkProvider without the nonce', () => {
  const offenders: string[] = []
  const walk = (dir: string): string[] => readdirSync(dir).flatMap((n: string) => {
    const full = join(dir, n)
    return statSync(full).isDirectory() ? walk(full) : /\.tsx$/.test(n) ? [full] : []
  })
  for (const file of walk(SRC)) {
    if (file.endsWith(join('components', 'auth', 'NonceClerkProvider.tsx'))) continue
    const text = readFileSync(file, 'utf8')
    if (/<ClerkProvider\b/.test(text) || /import \{[^}]*\bClerkProvider\b[^}]*\} from '@clerk\/nextjs'/.test(text)) offenders.push(file.slice(SRC.length + 1))
  }
  assert.deepEqual(offenders, [], 'ClerkProvider is used directly: its SDK script would carry no nonce and be blocked')
  const wrapper = read('components', 'auth', 'NonceClerkProvider.tsx')
  assert.match(wrapper, /\(await headers\(\)\)\.get\('x-nonce'\)/)
  assert.match(wrapper, /<ClerkProvider nonce=\{nonce\} \{\.\.\.props\} \/>/)
})

// ── development is the only mode that may evaluate strings ───────────────────

test('a production policy never allows eval, and never lets "development" in by default', () => {
  const production = policy()
  assert.ok(!production.includes('unsafe-eval'))
  assert.ok(production.includes('upgrade-insecure-requests'))
  assert.ok(!policy({ development: false }).includes('unsafe-eval'))
})

test('the development policy adds unsafe-eval for React\'s call stacks and changes nothing else that matters', () => {
  const dev = policy({ development: true })
  assert.ok(directive('script-src', dev).includes("'unsafe-eval'"))
  assert.ok(!dev.includes('upgrade-insecure-requests'), 'plain-HTTP localhost has nothing to upgrade to')
  // Everything else is the production policy, so what is tested in development is what ships.
  const strip = (text: string) => text.replace(" 'unsafe-eval'", '').replace('; upgrade-insecure-requests', '')
  assert.equal(strip(dev), strip(policy()))
  assert.ok(directive('script-src', dev).includes("'strict-dynamic'"))
})

test('only a development server asks for the development policy', () => {
  const proxy = read('proxy.ts')
  const uses = [...proxy.matchAll(/development:\s*([^\n,]+)/g)].map((m) => m[1].trim())
  assert.equal(uses.length, 2, 'both places the proxy builds a policy must say')
  for (const use of uses) assert.equal(use, "process.env.NODE_ENV === 'development'")
})
