import { sanitizeError } from './providerHealth'
import { ResourceError } from './resource'

export interface Failure {
  title: string
  detail: string
  /** The underlying message with URLs removed, for an optional disclosure. */
  technical: string | null
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

/**
 * A failed read in the reader's terms. The status decides the wording —
 * busy, not entitled, signed out, not found, or unavailable — and the raw
 * message is kept only as a sanitised technical detail, never as the headline.
 */
export function describeFailure(error: unknown, what: string): Failure {
  const raw = error instanceof Error ? error.message : null
  const technical = raw ? (sanitizeError(raw) ?? '').slice(0, 240) || null : null
  const status = error instanceof ResourceError ? error.status : null
  // A vendor's throttling never reaches the browser as an HTTP 429: the
  // backend retries it and reports it inside the evidence. A 429 here is the
  // research server itself refusing for lack of capacity, after the proxy has
  // already retried it.
  if (status === 429) {
    return { title: `${cap(what)} delayed`, detail: 'The research server is busy with other requests. Try again shortly.', technical }
  }
  if (status === 401) {
    return { title: 'Sign-in required', detail: `${cap(what)} needs a signed-in session.`, technical }
  }
  if (status === 403) {
    return { title: `${cap(what)} not entitled`, detail: 'This deployment or plan does not include this data.', technical }
  }
  if (status === 404) {
    return { title: `No ${what} found`, detail: 'The service answered and holds nothing for this request.', technical }
  }
  return {
    title: `${cap(what)} temporarily unavailable`,
    detail: 'The service did not answer. Other research remains available.',
    technical,
  }
}

/**
 * A raw error message as one short sentence a reader can use. Status codes and
 * transport failures become plain words; anything long, structured or
 * URL-bearing is replaced rather than shown.
 */
export function readerError(message?: string | null): string {
  const m = message ?? ''
  const status = Number(/\b([45]\d\d)\b/.exec(m)?.[1] ?? NaN)
  if (status === 429) return 'The research server is busy with other requests'
  if (status === 401) return 'A signed-in session is required'
  if (status === 403) return 'This deployment does not include this data'
  if (status === 404) return 'The service holds nothing for this request'
  if (status >= 500) return 'The service did not answer'
  if (/failed to fetch|networkerror|network error|load failed|aborted/i.test(m)) return 'The service could not be reached'
  const clean = sanitizeError(m)
  return clean && clean.length <= 120 && !/[{}<>\[\]]/.test(clean) ? clean.replace(/\.$/, '') : 'The service did not answer'
}
