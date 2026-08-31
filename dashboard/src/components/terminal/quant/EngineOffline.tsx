'use client'

/**
 * The panel that replaces `TypeError: Failed to fetch`.
 *
 * A research terminal that fails opaquely is worse than one that fails loudly:
 * the reader cannot tell whether the model is broken, the data is missing, or
 * the network hiccuped — and the three call for completely different reactions.
 *
 * So a failure renders as a status board with the endpoint that was tried, the
 * classification, the last time anything succeeded, and what to do about it.
 * Everything shown here comes from `QuantFailure`, which the API client builds;
 * this component invents nothing.
 */

import { StatusPill } from '@/components/ui/DataMarks'
import type { QuantFailure } from '@/lib/quantApi'

const KIND_LABEL: Record<string, string> = {
  network: 'UNREACHABLE',
  timeout: 'TIMED OUT',
  auth: 'NOT AUTHENTICATED',
  not_found: 'ENDPOINT NOT FOUND',
  server: 'BACKEND ERROR',
  malformed: 'BAD RESPONSE',
}

export default function EngineOffline({
  failure,
  title = 'Quant engine',
  lastSuccess,
  onRetry,
}: {
  failure: QuantFailure
  title?: string
  /** ISO timestamp of the last successful call, if the caller tracks one. */
  lastSuccess?: string | null
  onRetry?: () => void
}) {
  return (
    <div className="qe">
      <div className="qe__head">
        <div>
          <span className="label">{title}</span>
          <strong className="qe__state">OFFLINE</strong>
        </div>
        <StatusPill tone="neg" label={KIND_LABEL[failure.kind] ?? 'UNAVAILABLE'} />
      </div>

      <dl className="qe__rows">
        <div>
          <dt>Reason</dt>
          <dd>{failure.message}</dd>
        </div>
        <div>
          <dt>Endpoint</dt>
          <dd className="num">{failure.path}</dd>
        </div>
        {failure.status !== undefined && (
          <div>
            <dt>HTTP status</dt>
            <dd className="num">{failure.status}</dd>
          </div>
        )}
        <div>
          <dt>Last success</dt>
          <dd className="num">{lastSuccess ?? 'none this session'}</dd>
        </div>
        <div>
          <dt>Suggested action</dt>
          <dd>{failure.remedy}</dd>
        </div>
      </dl>

      {onRetry && (
        <button type="button" className="btn btn--sm" onClick={onRetry}>
          Retry
        </button>
      )}

      <p className="body-copy u-note qe__note">
        The research evidence on this page is read from committed experiment
        artifacts and does not depend on the inference service. A model being
        unreachable does not invalidate a result that was already measured.
      </p>
    </div>
  )
}
