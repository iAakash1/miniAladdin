/* Secrets stay on the server.

   Two ways a secret reaches a browser bundle: a client component imports a
   module that reads one from `process.env`, or the variable is named
   `NEXT_PUBLIC_*`, which Next inlines into every client chunk. Neither is
   caught by the type system or the build, and both are one careless import or
   rename away. This pins the boundary as it stands.

   Source-level on purpose: the built bundle was also scanned for secret-shaped
   strings and for the Clerk secret key's name (the only hit was the Clerk SDK's
   own `process.env.CLERK_SECRET_KEY` lookup, a name and not a value). */

import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import test from 'node:test'

const SRC = join(__dirname, '..', 'src')

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (/\.(ts|tsx)$/.test(name)) out.push(full)
  }
  return out
}

const FILES = walk(SRC)
const read = (f: string) => readFileSync(f, 'utf8')
const rel = (f: string) => relative(SRC, f).split(sep).join('/')

/** Server-side configuration that must never be inlined or imported into a client chunk. */
const SERVER_ENV =
  /process\.env\.(CLERK_SECRET_KEY|RAZORPAY_KEY_SECRET|GCP_[A-Z_]+|CLOUD_RUN_AUDIENCE|BACKEND_ORIGIN|BACKEND_AUTH_MODE|VERCEL_OIDC_TOKEN)\b/

test('the inventory finds the modules that read server secrets', () => {
  const readers = FILES.filter((f) => SERVER_ENV.test(read(f))).map(rel)
  // A scan that found nothing would pass every test below for the wrong reason.
  assert.ok(readers.includes('lib/backend-proxy.ts'), readers.join(', '))
  assert.ok(readers.some((r) => r.startsWith('app/payment/')), readers.join(', '))
})

test('no client component imports a module that reads a server secret', () => {
  const readers = new Set(FILES.filter((f) => SERVER_ENV.test(read(f))).map((f) => rel(f).replace(/\.(ts|tsx)$/, '')))
  const offenders: string[] = []
  for (const file of FILES) {
    const text = read(file)
    if (!/^\s*(['"])use client\1/.test(text.slice(0, 200))) continue
    for (const m of text.matchAll(/from\s+['"]@\/([^'"]+)['"]/g)) {
      if (readers.has(m[1])) offenders.push(`${rel(file)} imports ${m[1]}`)
    }
  }
  assert.deepEqual(offenders, [], 'a client bundle would pull in a secret-reading module')
})

test('only route handlers and the proxy read server secrets', () => {
  const readers = FILES.filter((f) => SERVER_ENV.test(read(f))).map(rel)
  for (const r of readers) {
    assert.ok(/(^|\/)route\.ts$/.test(r) || r === 'lib/backend-proxy.ts', `${r} reads a server secret outside a route handler`)
  }
})

const PUBLIC_ALLOWED = new Set([
  'NEXT_PUBLIC_API_URL',
  'NEXT_PUBLIC_SITE_URL',
  'NEXT_PUBLIC_BUILD_SHA', 'NEXT_PUBLIC_BUILD_REF', 'NEXT_PUBLIC_BUILD_ENV',
  'NEXT_PUBLIC_BUILD_DEPLOYMENT', 'NEXT_PUBLIC_BUILD_TIME',
  'NEXT_PUBLIC_RAZORPAY_KEY_ID',   // the publishable key id; the secret is server-side
  'NEXT_PUBLIC_LOGO_DEV_KEY',      // logo.dev publishable key
  'NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY', // pk_*: public by design; the secret is CLERK_SECRET_KEY
])

test('no NEXT_PUBLIC variable is named like a secret, and each is one we expect', () => {
  const used = new Set<string>()
  for (const file of [...FILES, join(SRC, '..', 'next.config.ts')]) {
    for (const m of read(file).matchAll(/\bNEXT_PUBLIC_[A-Z0-9_]+/g)) used.add(m[0])
  }
  assert.ok(used.size >= 5, [...used].join(', '))
  for (const name of used) {
    assert.doesNotMatch(name, /SECRET|PRIVATE|PASSWORD|TOKEN|SERVICE_ROLE/, `${name} would ship a secret to every browser`)
    // Clerk's publishable key is also read here, to derive the Clerk host the
    // Content-Security-Policy allows (src/proxy.ts); it is a public identifier.
    assert.ok(PUBLIC_ALLOWED.has(name), `${name} is new: confirm it is safe to publish, then add it here`)
  }
})

test('the Content-Security-Policy reads the Clerk publishable key and never the secret key', () => {
  for (const file of ['proxy.ts', 'lib/csp.ts']) {
    const text = read(join(SRC, file))
    assert.doesNotMatch(text, /CLERK_SECRET_KEY/, `${file} must not touch the Clerk secret key`)
  }
})
