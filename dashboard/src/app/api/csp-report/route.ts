/**
 * Receives Content-Security-Policy violation reports and logs a summary.
 *
 * Browsers post a report when the policy blocks something (or, in `report-only`
 * mode, would have). This is how an operator learns that a legitimate resource is
 * being refused - the failure mode of a policy that cannot be tried in every
 * browser before it ships - without anyone having to open a console.
 *
 * It is public and unauthenticated, because the browser sends reports without
 * credentials, so it is deliberately small: one method, a size cap, a fixed set
 * of fields, nothing stored, no echo of the body.
 */

export const runtime = 'nodejs'

const MAX_BYTES = 8 * 1024
const FIELDS = [
  'document-uri', 'documentURL', 'blocked-uri', 'blockedURL', 'violated-directive',
  'effective-directive', 'effectiveDirective', 'original-policy', 'disposition', 'source-file',
  'sourceFile', 'line-number', 'lineNumber', 'status-code',
] as const

/** Strip a URL to its origin and path: a query string can carry a token. */
function scrub(value: unknown): string {
  if (typeof value !== 'string') return ''
  const text = value.slice(0, 300)
  try {
    const url = new URL(text)
    return `${url.origin}${url.pathname}`
  } catch {
    return text.replace(/[\r\n]+/g, ' ')
  }
}

export async function POST(request: Request) {
  const type = request.headers.get('content-type') ?? ''
  if (!/json|csp-report/i.test(type)) return new Response(null, { status: 415 })
  const length = Number(request.headers.get('content-length') ?? 0)
  if (length > MAX_BYTES) return new Response(null, { status: 413 })

  let body: unknown
  try {
    const text = await request.text()
    if (text.length > MAX_BYTES) return new Response(null, { status: 413 })
    body = JSON.parse(text)
  } catch {
    return new Response(null, { status: 400 })
  }

  // The legacy `report-uri` shape wraps one report; the Reporting API sends an array.
  const reports = Array.isArray(body) ? body : [body]
  for (const item of reports.slice(0, 5)) {
    const raw = (item as { 'csp-report'?: Record<string, unknown>; body?: Record<string, unknown> } | null) ?? {}
    const report = raw['csp-report'] ?? raw.body ?? {}
    const summary: Record<string, string> = {}
    for (const field of FIELDS) {
      if (field in report) summary[field] = field === 'original-policy' ? '[policy]' : scrub(report[field])
    }
    console.warn('csp-violation', JSON.stringify(summary))
  }
  return new Response(null, { status: 204 })
}
