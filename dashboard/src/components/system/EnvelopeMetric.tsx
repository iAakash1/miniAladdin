/**
 * A number with its whole envelope attached.
 *
 * The backend already publishes, for each decision figure, where it came from,
 * when it was retrieved, what method produced it, and whether that value can go
 * stale. Rendering only the number throws that away and leaves the reader to
 * take a figure on trust — which is the opposite of what this product claims to
 * do.
 *
 * So the value is a control. Clicking it opens the envelope inline: status,
 * source, method, freshness, unit. Nothing is fetched to do this; the envelope
 * arrived with the number.
 */
'use client'

import { useState } from 'react'

import { Status, Value, type ResearchState } from './index'

export interface Envelope {
  value: number | string | null
  status?: string
  source?: string | null
  as_of?: string | null
  retrieved_at?: string | null
  method?: string | null
  unit?: string | null
  detail?: string | null
  freshness?: Record<string, unknown> | null
}

const STATUS_MAP: Record<string, ResearchState> = {
  live: 'live',
  recorded: 'recorded',
  stale: 'stale',
  waking: 'waking',
  unavailable: 'unavailable',
  unknown: 'unknown',
}

export function EnvelopeMetric({
  label, envelope, digits = 4, signed = false, tone = false, verdict,
}: {
  label: string
  envelope: Envelope | null | undefined
  digits?: number
  signed?: boolean
  tone?: boolean
  /**
   * Whether this value clears the threshold it is measured against. Distinct
   * from the envelope's status: one says where the number came from, the other
   * says what it concluded. A recorded number can fail, and a stale one can
   * pass — collapsing them into a single indicator loses which is which.
   */
  verdict?: 'pass' | 'fail'
}) {
  const [open, setOpen] = useState(false)

  if (!envelope) {
    return (
      <div className="env">
        <span className="env-label">{label}</span>
        <span className="sys-num sys-null">—</span>
        <span className="sys-meta">no envelope recorded</span>
      </div>
    )
  }

  const state = STATUS_MAP[envelope.status ?? 'unknown'] ?? 'unknown'
  const numeric = typeof envelope.value === 'number' ? envelope.value : null

  return (
    <div className="env" data-open={open}>
      <span className="env-label">{label}</span>
      <button
        className="env-value sys-focusable"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        title="Open this number's envelope"
      >
        {numeric !== null
          ? <Value value={numeric} digits={digits} signed={signed} tone={tone} unit={envelope.unit ?? undefined} />
          : <span className="sys-num">{String(envelope.value ?? '—')}</span>}
        <span className="env-caret" aria-hidden>{open ? '−' : '+'}</span>
      </button>
      <Status state={state} />
      {verdict ? (
        <span
          className="sys-badge"
          data-tone={verdict === 'pass' ? 'pass' : 'fail'}
          title={verdict === 'pass' ? 'Clears its threshold' : 'Does not clear its threshold'}
        >
          {verdict}
        </span>
      ) : null}

      {open ? (
        <table className="sys-table sys-table--compact env-body">
          <tbody>
            <tr><td>Status</td><td className="num" style={{ textAlign: 'left' }}>{envelope.status ?? 'unknown'}</td></tr>
            <tr><td>Unit</td><td className="num" style={{ textAlign: 'left' }}>{envelope.unit ?? '—'}</td></tr>
            <tr>
              <td>Method</td>
              <td className="num" style={{ textAlign: 'left', whiteSpace: 'normal', fontFamily: 'var(--font-sans)', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)' }}>
                {envelope.method ?? '—'}
              </td>
            </tr>
            <tr><td>Source</td><td className="num" style={{ textAlign: 'left', wordBreak: 'break-all', fontSize: 'var(--t-micro)' }}>{envelope.source ?? '—'}</td></tr>
            <tr><td>As of</td><td className="num" style={{ textAlign: 'left' }}>{envelope.as_of ?? <span className="sys-null">not dated</span>}</td></tr>
            <tr><td>Retrieved</td><td className="num" style={{ textAlign: 'left' }}>{envelope.retrieved_at?.slice(0, 19) ?? '—'}</td></tr>
            {envelope.detail ? (
              <tr>
                <td>Detail</td>
                <td className="num" style={{ textAlign: 'left', whiteSpace: 'normal', fontFamily: 'var(--font-sans)', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)' }}>
                  {envelope.detail}
                </td>
              </tr>
            ) : null}
            {envelope.status === 'recorded' ? (
              <tr>
                <td colSpan={2} style={{ whiteSpace: 'normal', fontSize: 'var(--t-micro)', color: 'var(--ink-faint)', lineHeight: 'var(--lh-body)' }}>
                  A recorded value is read from a stored artifact. It has no freshness
                  window and cannot go stale — it is what that run measured, permanently.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      ) : null}
    </div>
  )
}

export function EnvelopeGrid({
  metrics,
}: {
  metrics: { label: string; envelope: Envelope | null | undefined; digits?: number; signed?: boolean; tone?: boolean }[]
}) {
  return (
    <div className="env-grid">
      {metrics.map((m) => (
        <EnvelopeMetric key={m.label} {...m} />
      ))}
    </div>
  )
}
