'use client'

/**
 * One way to say "not here, and here is why".
 *
 * Three surfaces each invented their own version of this and each one reached
 * the reader as a status code: "Request failed: 404" on the performance page,
 * an HTTP 500 on covariance, a bare credential warning on paper trading. None
 * of those is a reason, and two of the three were not even faults — a
 * deployment that never received a regenerable artifact and a feature nobody
 * configured are both working as designed.
 *
 * So the backend now returns a typed state and this renders it. The split that
 * matters is between states that are *expected* — nothing to show, not
 * configured, not enough data — and states that are faults. The first kind get
 * a calm explanation; only the second kind should read as something being
 * wrong, because a reader who is told every absence is an error stops
 * believing the ones that are.
 *
 * Technical detail is available but never the headline: it goes behind a
 * disclosure, so an operator can read it and an ordinary reader is not handed
 * a reason code they cannot act on.
 */

import { Panel, Prose, StateBlock } from '@/components/system'
import type { ResearchState } from '@/components/system'

export type AvailabilityStatus =
  | 'AVAILABLE' | 'EMPTY' | 'PARTIAL' | 'STALE' | 'NOT_CONFIGURED'
  | 'INSUFFICIENT_DATA' | 'UNSUPPORTED' | 'DEPENDENCY_UNAVAILABLE'
  | 'PERMISSION_DENIED' | 'ERROR'

export interface AvailabilityPayload {
  status?: string
  message?: string | null
  reason?: string | null
  remedy?: string | null
  detail?: Record<string, unknown> | null
}

/** Expected absences read calmly; faults read as faults. */
const STATE: Record<AvailabilityStatus, ResearchState> = {
  AVAILABLE: 'live',
  EMPTY: 'recorded',
  PARTIAL: 'stale',
  STALE: 'stale',
  NOT_CONFIGURED: 'recorded',
  INSUFFICIENT_DATA: 'recorded',
  UNSUPPORTED: 'blocked',
  DEPENDENCY_UNAVAILABLE: 'unavailable',
  PERMISSION_DENIED: 'blocked',
  ERROR: 'unavailable',
}

const TITLE: Record<AvailabilityStatus, string> = {
  AVAILABLE: 'Available',
  EMPTY: 'Nothing recorded',
  PARTIAL: 'Partially available',
  STALE: 'Not current',
  NOT_CONFIGURED: 'Not configured',
  INSUFFICIENT_DATA: 'Not enough data',
  UNSUPPORTED: 'Not supported',
  DEPENDENCY_UNAVAILABLE: 'A dependency is unavailable',
  PERMISSION_DENIED: 'Not permitted',
  ERROR: 'Something went wrong',
}

export function isAvailable(payload: { status?: string } | null | undefined): boolean {
  // Absent status means a route that predates this vocabulary; treated as
  // available so older endpoints keep rendering.
  return !payload?.status || payload.status === 'AVAILABLE'
}

function normalise(status: string | undefined): AvailabilityStatus {
  return (status && status in STATE ? status : 'ERROR') as AvailabilityStatus
}

export function AvailabilityNote({ payload }: { payload: AvailabilityPayload }) {
  const status = normalise(payload.status)
  const detail = payload.detail && Object.keys(payload.detail).length ? payload.detail : null

  return (
    <StateBlock
      state={STATE[status]}
      title={TITLE[status]}
      detail={payload.reason ?? undefined}
    >
      {payload.message ? <Prose>{payload.message}</Prose> : null}
      {payload.remedy ? <Prose>{payload.remedy}</Prose> : null}
      {detail ? (
        <details className="av__detail">
          <summary>Technical detail</summary>
          <dl className="av__dl">
            {Object.entries(detail).map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</dd>
              </div>
            ))}
          </dl>
        </details>
      ) : null}
    </StateBlock>
  )
}

/** The same note inside a titled panel, for a whole workspace section. */
export function AvailabilityPanel(
  { title, payload }: { title: string; payload: AvailabilityPayload },
) {
  const status = normalise(payload.status)
  return (
    <Panel title={title} state={STATE[status]}>
      <AvailabilityNote payload={payload} />
    </Panel>
  )
}
