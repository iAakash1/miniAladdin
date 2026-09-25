import { getVercelOidcToken } from '@vercel/oidc'
import { ExternalAccountClient } from 'google-auth-library'

const TRANSPORT_HEADERS = new Set([
  'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
  'te', 'trailer', 'transfer-encoding', 'upgrade',
])
const REQUEST_BLOCKED_HEADERS = new Set([
  ...TRANSPORT_HEADERS, 'host', 'content-length',
  'x-vercel-oidc-token', 'x-serverless-authorization',
])
const RESPONSE_BLOCKED_HEADERS = new Set([
  ...TRANSPORT_HEADERS, 'content-length',
  // Node's fetch transparently decompresses upstream bodies. Forwarding the
  // original encoding after that would ask the browser to decode plain bytes.
  'content-encoding',
  // Infrastructure and application credentials are request-only. A broken
  // upstream must never reflect them into the browser response.
  'authorization', 'set-cookie', 'x-vercel-oidc-token',
  'x-serverless-authorization',
])
const MAX_BACKEND_RESPONSE_BYTES = 8 * 1024 * 1024
// The route's maxDuration is 120 s. Every attempt, and every wait between
// attempts, fits inside one budget with room left to write the response.
const PROXY_BUDGET_MS = 115_000
const CAPACITY_RETRY_BASE_MS = 250
const CAPACITY_RETRY_MAX_MS = 2_000

type CachedIdToken = { token: string; expiresAt: number }
let cachedIdToken: CachedIdToken | null = null
let tokenFlight: Promise<string> | null = null

function required(name: string): string {
  const value = process.env[name]?.trim()
  if (!value) throw new Error(`Missing server configuration: ${name}`)
  return value
}

function tokenExpiry(token: string): number {
  try {
    const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString('utf8')) as { exp?: number }
    return typeof payload.exp === 'number' ? payload.exp * 1000 : Date.now() + 45 * 60_000
  } catch {
    return Date.now() + 45 * 60_000
  }
}

async function mintCloudRunIdToken(): Promise<string> {
  const projectNumber = required('GCP_PROJECT_NUMBER')
  const poolId = required('GCP_WORKLOAD_IDENTITY_POOL_ID')
  const providerId = required('GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID')
  const serviceAccount = required('GCP_SERVICE_ACCOUNT_EMAIL')
  const audience = required('CLOUD_RUN_AUDIENCE')
  const workloadAudience = `//iam.googleapis.com/projects/${projectNumber}/locations/global/workloadIdentityPools/${poolId}/providers/${providerId}`

  const authClient = ExternalAccountClient.fromJSON({
    type: 'external_account',
    audience: workloadAudience,
    subject_token_type: 'urn:ietf:params:oauth:token-type:jwt',
    token_url: 'https://sts.googleapis.com/v1/token',
    service_account_impersonation_url:
      `https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/${encodeURIComponent(serviceAccount)}:generateAccessToken`,
    subject_token_supplier: {
      getSubjectToken: () => getVercelOidcToken(),
    },
  })
  if (!authClient) throw new Error('Unable to initialize Google external-account client')
  const access = await authClient.getAccessToken()
  if (!access.token) throw new Error('Google token exchange returned no access token')

  const response = await fetch(
    `https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/${encodeURIComponent(serviceAccount)}:generateIdToken`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${access.token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ audience, includeEmail: true }),
      cache: 'no-store',
    },
  )
  if (!response.ok) throw new Error(`Google ID-token exchange failed with status ${response.status}`)
  const body = (await response.json()) as { token?: string }
  if (!body.token) throw new Error('Google ID-token exchange returned no token')
  cachedIdToken = { token: body.token, expiresAt: tokenExpiry(body.token) }
  return body.token
}

export async function cloudRunIdToken(): Promise<string> {
  if (cachedIdToken && cachedIdToken.expiresAt - Date.now() > 5 * 60_000) {
    return cachedIdToken.token
  }
  if (!tokenFlight) {
    tokenFlight = mintCloudRunIdToken().finally(() => {
      tokenFlight = null
    })
  }
  return tokenFlight
}

function outboundHeaders(request: Request): Headers {
  const headers = new Headers()
  const blocked = connectionScopedHeaders(request.headers, REQUEST_BLOCKED_HEADERS)
  request.headers.forEach((value, key) => {
    if (!blocked.has(key.toLowerCase())) headers.set(key, value)
  })
  return headers
}

function responseHeaders(upstream: Headers): Headers {
  const headers = new Headers()
  const blocked = connectionScopedHeaders(upstream, RESPONSE_BLOCKED_HEADERS)
  upstream.forEach((value, key) => {
    if (!blocked.has(key.toLowerCase())) headers.set(key, value)
  })
  return headers
}

function connectionScopedHeaders(headers: Headers, base: Set<string>): Set<string> {
  const blocked = new Set(base)
  for (const token of (headers.get('connection') || '').split(',')) {
    const name = token.trim().toLowerCase()
    if (name) blocked.add(name)
  }
  return blocked
}

/**
 * Cloud Run's own refusal when no instance can take a request.
 *
 * The service runs one instance at concurrency one, so a page that asks for
 * ten things at once has nine of them refused — immediately, or after they
 * have queued behind a slow research run. Cloud Run writes that 429 itself;
 * the request never reached the application, which stamps X-Request-Id on
 * every response it produces. Repeating such a request cannot run anything
 * twice, whatever its method.
 */
function refusedByPlatform(upstream: Response): boolean {
  return upstream.status === 429 && !upstream.headers.has('x-request-id')
}

export async function proxyBackend(request: Request, path: string[]): Promise<Response> {
  const deadline = Date.now() + PROXY_BUDGET_MS
  const origin = required('BACKEND_ORIGIN').replace(/\/$/, '')
  const incomingUrl = new URL(request.url)
  const target = new URL(`${origin}/api/${path.map(encodeURIComponent).join('/')}`)
  target.search = incomingUrl.search

  const headers = outboundHeaders(request)
  if ((process.env.BACKEND_AUTH_MODE || 'none').toLowerCase() === 'google_oidc') {
    // Cloud Run checks this header for infrastructure identity and leaves the
    // browser's Authorization header available to Clerk application auth.
    headers.set('X-Serverless-Authorization', `Bearer ${await cloudRunIdToken()}`)
  }

  const method = request.method.toUpperCase()
  const body = method === 'GET' || method === 'HEAD' ? undefined : await request.arrayBuffer()
  let upstream: Response
  for (let attempt = 0; ; attempt += 1) {
    upstream = await fetch(target, {
      method,
      headers,
      body: body?.slice(0),
      redirect: 'manual',
      cache: 'no-store',
      signal: AbortSignal.timeout(Math.max(1_000, deadline - Date.now())),
    })
    if (!refusedByPlatform(upstream) || request.signal?.aborted) break
    // Jittered so a page's refused requests do not return in lockstep.
    const wait = Math.min(CAPACITY_RETRY_MAX_MS, CAPACITY_RETRY_BASE_MS * 2 ** attempt) * (0.5 + Math.random() / 2)
    if (Date.now() + wait + 1_000 >= deadline) break
    await upstream.arrayBuffer().catch(() => undefined)
    await new Promise((resolve) => setTimeout(resolve, wait))
  }
  // Buffer the bounded JSON payload before returning it. A cross-origin
  // ReadableStream was observed to lose its body when the Render rollback
  // connection closed after Vercel had already emitted the response headers.
  // API responses are deliberately compact (the largest registry response is
  // currently under 100 KiB), while the 120 s abort bounds request lifetime.
  const declaredLength = Number(upstream.headers.get('content-length'))
  if (Number.isFinite(declaredLength) && declaredLength > MAX_BACKEND_RESPONSE_BYTES) {
    throw new Error('Backend response exceeded the proxy size limit')
  }
  const statusHasNoBody = upstream.status === 204 || upstream.status === 205 || upstream.status === 304
  const payload = method === 'HEAD' || statusHasNoBody ? null : await upstream.arrayBuffer()
  if (payload && payload.byteLength > MAX_BACKEND_RESPONSE_BYTES) {
    throw new Error('Backend response exceeded the proxy size limit')
  }
  return new Response(payload, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders(upstream.headers),
  })
}

export function resetBackendTokenForTests(): void {
  cachedIdToken = null
  tokenFlight = null
}

export function setBackendIdTokenForTests(token: string): void {
  cachedIdToken = { token, expiresAt: Date.now() + 60 * 60_000 }
  tokenFlight = null
}
