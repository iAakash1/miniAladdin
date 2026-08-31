/**
 * The single way the browser reaches the quant backend.
 *
 * ## Why this file exists — the production failure it fixes
 *
 * Every quant component previously did:
 *
 *     const API = process.env.NEXT_PUBLIC_API_URL ?? ''
 *     fetch(`${API}/api/quant/status`)
 *
 * That is a loaded gun in a hosted environment. `next.config.ts` already carries
 * a comment about the last time it went off: *"the hosting env had a stale
 * API_URL pinned to a dead Railway backend that silently overrode this."* When
 * `NEXT_PUBLIC_API_URL` names a host that no longer resolves, the browser's
 * fetch fails at the network layer and React surfaces the least useful string in
 * web development: **`TypeError: Failed to fetch`**. No status code, no origin,
 * no clue whether the backend is down, the URL is wrong, or CORS refused it.
 *
 * So the rule here is: **in the browser, always call the same origin.**
 * `next.config.ts` rewrites `/api/:path*` to the Render backend server-side,
 * which means no CORS, no cross-origin DNS, and no env var that can silently
 * redirect a user's browser at a dead host.
 *
 * `NEXT_PUBLIC_API_URL` is still honoured for local development, but only when
 * it points at localhost. A production value pointing anywhere else is ignored
 * and reported, rather than obeyed.
 *
 * ## The second half: failures must be legible
 *
 * `quantFetch` never throws a bare `TypeError`. It returns a discriminated
 * result carrying *what kind* of failure occurred — network, auth, not-found,
 * server, or malformed body — plus the URL it tried. That is what lets the UI
 * render a diagnostic panel instead of "Failed to fetch".
 */

export type QuantFailureKind =
  | 'network'
  | 'auth'
  | 'not_found'
  | 'server'
  | 'malformed'
  | 'timeout'

export interface QuantFailure {
  ok: false
  kind: QuantFailureKind
  status?: number
  path: string
  url: string
  message: string
  /** What a reader should actually do about it. */
  remedy: string
}

export interface QuantSuccess<T> {
  ok: true
  data: T
  path: string
  elapsedMs: number
}

export type QuantResult<T> = QuantSuccess<T> | QuantFailure

/** Default ceiling. Render's free tier cold-starts, so this is generous. */
const DEFAULT_TIMEOUT_MS = 30_000

/**
 * The origin browser requests go to.
 *
 * Empty string means "same origin", which is what production must always use:
 * `next.config.ts` proxies `/api/*` onward server-side. An absolute override is
 * accepted only for localhost, so a stale hosted env var cannot point real
 * users at a dead backend.
 */
export function apiBase(): string {
  const configured = (process.env.NEXT_PUBLIC_API_URL ?? '').trim()
  if (!configured) return ''

  // Server-side rendering has no cross-origin problem and no user to strand.
  if (typeof window === 'undefined') return configured.replace(/\/$/, '')

  try {
    const url = new URL(configured)
    const local =
      url.hostname === 'localhost' ||
      url.hostname === '127.0.0.1' ||
      url.hostname.endsWith('.local')
    if (local) return configured.replace(/\/$/, '')

    // Deliberately noisy: someone set this in a hosted environment, and the
    // symptom it produces (Failed to fetch) does not point back here.
    console.warn(
      `[quantApi] Ignoring NEXT_PUBLIC_API_URL="${configured}" in the browser. ` +
        'Requests use the same origin so the Next rewrite can proxy them; ' +
        'a cross-origin value here is how a stale env var takes the app down.',
    )
    return ''
  } catch {
    console.warn(`[quantApi] NEXT_PUBLIC_API_URL="${configured}" is not a URL; ignoring.`)
    return ''
  }
}

function classify(status: number): QuantFailureKind {
  if (status === 401 || status === 403) return 'auth'
  // Clerk's middleware answers an unauthenticated API request with a 404
  // rewrite (`x-clerk-auth-reason: protect-rewrite`) rather than a 401, so a
  // 404 here is ambiguous between "route missing" and "not signed in". The
  // remedy text says both rather than guessing.
  if (status === 404) return 'not_found'
  return 'server'
}

function remedyFor(kind: QuantFailureKind, path: string): string {
  switch (kind) {
    case 'network':
      return (
        'The request never reached a server. Usually the backend is asleep ' +
        '(Render free tier cold-starts) or the deployment is mid-rollout. ' +
        'Retry in a few seconds.'
      )
    case 'timeout':
      return 'The backend did not answer in time — most likely a cold start. Retry.'
    case 'auth':
      return 'Sign in again; the session was rejected.'
    case 'not_found':
      return (
        `${path} was not found. Either the session is signed out (Clerk answers ` +
        'unauthenticated API calls with a 404 rewrite, not a 401), or the ' +
        'deployed backend build predates this endpoint.'
      )
    case 'malformed':
      return 'The backend answered, but not with JSON. It is likely serving an error page.'
    default:
      return 'The backend returned an error. Check the service logs.'
  }
}

/**
 * Fetch JSON from the quant API, returning a structured result.
 *
 * Never throws for an expected failure. Callers render `failure.message` and
 * `failure.remedy` rather than a stack trace.
 */
export async function quantFetch<T>(
  path: string,
  options: { timeoutMs?: number; signal?: AbortSignal } = {},
): Promise<QuantResult<T>> {
  const url = `${apiBase()}${path}`
  const began = Date.now()
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS)

  if (options.signal) {
    if (options.signal.aborted) controller.abort()
    else options.signal.addEventListener('abort', () => controller.abort(), { once: true })
  }

  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: { accept: 'application/json' },
    })

    if (!response.ok) {
      const kind = classify(response.status)
      return {
        ok: false,
        kind,
        status: response.status,
        path,
        url,
        message: `${path} returned ${response.status} ${response.statusText}`.trim(),
        remedy: remedyFor(kind, path),
      }
    }

    const text = await response.text()
    try {
      return { ok: true, data: JSON.parse(text) as T, path, elapsedMs: Date.now() - began }
    } catch {
      return {
        ok: false,
        kind: 'malformed',
        status: response.status,
        path,
        url,
        message: `${path} returned ${response.status} but the body was not JSON`,
        remedy: remedyFor('malformed', path),
      }
    }
  } catch (error) {
    const aborted = error instanceof DOMException && error.name === 'AbortError'
    const kind: QuantFailureKind = aborted ? 'timeout' : 'network'
    return {
      ok: false,
      kind,
      path,
      url,
      // The raw TypeError message is retained but never shown alone.
      message: aborted
        ? `${path} timed out after ${options.timeoutMs ?? DEFAULT_TIMEOUT_MS}ms`
        : `${path} could not be reached (${error instanceof Error ? error.message : 'unknown'})`,
      remedy: remedyFor(kind, path),
    }
  } finally {
    clearTimeout(timer)
  }
}

/** Convenience: unwrap to data or null, keeping the failure for the caller. */
export function dataOf<T>(result: QuantResult<T>): T | null {
  return result.ok ? result.data : null
}
