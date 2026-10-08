/**
 * Content-Security-Policy for the OmniSignal frontend.
 *
 * Pure functions, no I/O, so the policy is a value a test can read.
 *
 * ## What the application actually loads
 *
 * Audited from source, not guessed:
 *
 *  - **Scripts**: Next's own chunks (same origin); one inline bootstrap the app
 *    writes (`THEME_SCRIPT`, allowed by hash); Clerk's browser SDK, loaded from
 *    the instance's Frontend API host by a script Next already trusts; Cloudflare
 *    Turnstile, which Clerk adds for bot protection; and Razorpay Checkout,
 *    inserted by the upgrade dialog only when it opens.
 *  - **Network**: every `fetch` is same-origin (`/api/*` is a server-side proxy;
 *    nothing in a client component calls a third party), plus Clerk's Frontend API
 *    and telemetry, and Razorpay's checkout API.
 *  - **Frames**: Turnstile and Razorpay Checkout.
 *  - **Images**: the app's own, `data:` and `blob:` for generated marks, Logo.dev
 *    and Parqet (company logos), Google's favicon service (a fallback), Clerk's
 *    avatars, and publishers' own article photographs, which can be any HTTPS
 *    host - the one place this policy is deliberately broad.
 *  - **Fonts**: self-hosted (`@fontsource`), so same origin and `data:`.
 *
 * ## What is not allowed, and why that matters
 *
 *  - No `'unsafe-eval'`: nothing in production needs it.
 *  - No `'unsafe-inline'` for scripts: scripts are allowed by nonce (Next stamps
 *    it on its own) and the single authored inline script by hash, and
 *    `'strict-dynamic'` lets those trusted scripts load what they need.
 *  - No wildcard host for scripts, connections or frames. Clerk's host comes from
 *    the publishable key, so moving to a production Clerk instance needs no edit.
 *  - `object-src 'none'`, `base-uri 'self'`, `frame-ancestors 'none'`.
 *
 * `style-src` keeps `'unsafe-inline'`: React writes `style` attributes into the
 * server HTML and Clerk's UI injects `<style>` elements. Inline *style* injection
 * is far weaker than inline *script* injection, and it is the documented
 * requirement of both.
 */

export type CspMode = 'enforce' | 'report-only' | 'off'

export interface CspInput {
  /** A fresh base64 nonce for this response. */
  nonce: string
  /** Base64 SHA-256 of each inline script the app itself writes. */
  scriptHashes: readonly string[]
  /** The Clerk Frontend API host (`example.clerk.accounts.dev`), or null if unknown. */
  clerkFrontendApi: string | null
  /** Where violations are posted, if reporting is on. */
  reportUri?: string
}

/** The Frontend API host a Clerk publishable key names, or null for a key that does not parse. */
export function clerkFrontendApi(publishableKey: string | undefined): string | null {
  const m = /^pk_(?:test|live)_([A-Za-z0-9+/_-]+={0,2})$/.exec(publishableKey ?? '')
  if (!m) return null
  try {
    const decoded = atob(m[1].replace(/-/g, '+').replace(/_/g, '/'))
    const host = decoded.replace(/\$$/, '')
    return /^[a-z0-9.-]+\.[a-z]{2,}$/i.test(host) ? host.toLowerCase() : null
  } catch {
    return null
  }
}

/** A fresh nonce: 128 bits from the platform's CSPRNG, base64-encoded. */
export function makeNonce(): string {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  return btoa(String.fromCharCode(...bytes))
}

/** `'sha256-...'` source-list entry for an inline script's exact text. */
export async function scriptHash(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
  return `sha256-${btoa(String.fromCharCode(...new Uint8Array(digest)))}`
}

const RAZORPAY_SCRIPT = 'https://checkout.razorpay.com'
const RAZORPAY_API = 'https://api.razorpay.com'
const RAZORPAY_TELEMETRY = 'https://lumberjack.razorpay.com'
const TURNSTILE = 'https://challenges.cloudflare.com'
const CLERK_TELEMETRY = ['https://clerk-telemetry.com', 'https://*.clerk-telemetry.com']
const CLERK_IMAGES = 'https://img.clerk.com'

export function buildCsp(input: CspInput): string {
  const clerkHost = input.clerkFrontendApi ? `https://${input.clerkFrontendApi}` : null

  const directives: Record<string, string[]> = {
    'default-src': ["'self'"],
    'script-src': [
      "'self'",
      `'nonce-${input.nonce}'`,
      ...input.scriptHashes.map((h) => `'${h}'`),
      // Honoured only by a browser without 'strict-dynamic' (CSP2); a modern
      // browser ignores host sources here and trusts what the nonce'd scripts load.
      ...(clerkHost ? [clerkHost] : []),
      TURNSTILE,
      RAZORPAY_SCRIPT,
      "'strict-dynamic'",
    ],
    'style-src': ["'self'", "'unsafe-inline'"],
    'img-src': ["'self'", 'data:', 'blob:', 'https:'],
    'font-src': ["'self'", 'data:'],
    'connect-src': [
      "'self'",
      ...(clerkHost ? [clerkHost] : []),
      ...CLERK_TELEMETRY,
      CLERK_IMAGES,
      RAZORPAY_API,
      RAZORPAY_TELEMETRY,
    ],
    'frame-src': ["'self'", TURNSTILE, RAZORPAY_API, RAZORPAY_SCRIPT],
    'worker-src': ["'self'", 'blob:'],
    'manifest-src': ["'self'"],
    'media-src': ["'self'", 'blob:', 'data:'],
    'object-src': ["'none'"],
    'base-uri': ["'self'"],
    'form-action': ["'self'", RAZORPAY_API],
    'frame-ancestors': ["'none'"],
  }

  const parts = Object.entries(directives).map(([name, sources]) => `${name} ${[...new Set(sources)].join(' ')}`)
  parts.push('upgrade-insecure-requests')
  if (input.reportUri) parts.push(`report-uri ${input.reportUri}`)
  return parts.join('; ')
}

/** The header that carries the policy in a given mode, or null when it is off. */
export function cspHeaderName(mode: CspMode): string | null {
  return mode === 'off' ? null : mode === 'report-only' ? 'Content-Security-Policy-Report-Only' : 'Content-Security-Policy'
}

/** The deployment's mode. Anything unrecognised enforces: failing open is the wrong default. */
export function cspMode(value: string | undefined): CspMode {
  const v = (value ?? '').trim().toLowerCase()
  return v === 'off' || v === 'report-only' ? v : 'enforce'
}
