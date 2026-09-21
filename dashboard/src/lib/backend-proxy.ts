import { getVercelOidcToken } from '@vercel/oidc'
import { ExternalAccountClient } from 'google-auth-library'

const HOP_BY_HOP = new Set([
  'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
  'te', 'trailer', 'transfer-encoding', 'upgrade', 'host', 'content-length',
  'x-vercel-oidc-token', 'x-serverless-authorization',
])

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
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) headers.set(key, value)
  })
  return headers
}

function responseHeaders(upstream: Headers): Headers {
  const headers = new Headers()
  upstream.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) headers.set(key, value)
  })
  return headers
}

export async function proxyBackend(request: Request, path: string[]): Promise<Response> {
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
  const upstream = await fetch(target, {
    method,
    headers,
    body,
    redirect: 'manual',
    cache: 'no-store',
    signal: AbortSignal.timeout(120_000),
  })
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders(upstream.headers),
  })
}

export function resetBackendTokenForTests(): void {
  cachedIdToken = null
  tokenFlight = null
}
