'use client'

/**
 * One claim, and the evidence it actually rests on.
 *
 * The audit surface listed each claim with its evidence handles rendered as
 * text — "EV-003, EV-007" — and that is where traceability stopped. The whole
 * architectural assertion is that every sentence reduces to measured values a
 * reader can check, and a handle nobody can follow does not discharge it. It
 * reads as provenance while providing none, which is worse than showing
 * nothing: it invites the trust without earning it.
 *
 * So the handles resolve here, against the evidence records from the same
 * response, and three distinctions are kept that a careless drawer collapses:
 *
 *   **Observed is not fetched.** When the world was in this state and when we
 *   asked are different facts, and conflating them is how a figure cached
 *   three days ago gets presented as current. Both are shown, always, and the
 *   gap between them is named when it is large.
 *
 *   **Cited-and-missing is not uncited.** A claim with no evidence handles is
 *   making an unsupported statement. A claim citing a handle that is not in
 *   the payload is a defect in the pipeline — the claim believes it has
 *   support that did not arrive. Silently dropping the second produces a
 *   drawer that looks like the first, and hides a real fault.
 *
 *   **Absent is not zero.** A record whose value did not arrive says so.
 */

import { useEffect } from 'react'

import { EmptyLine, Prose, Status, type ResearchState } from '@/components/system'

export interface EvidenceRecord {
  evidence_id: string
  agent: string
  provider: string
  capability: string
  field: string
  value: unknown
  unit: string | null
  currency: string | null
  observed_at: string | null
  fetched_at: string
  stale: boolean
}

export interface Claim {
  claim_id: string
  agent: string
  claim_type: string
  statement: string
  evidence_ids: string[]
  numeric_value?: number | null
  unit?: string | null
  as_of?: string | null
  validation_status: string
  validation_note: string | null
}

const STATE: Record<string, ResearchState> = {
  VERIFIED: 'live',
  PARTIAL: 'stale',
  STALE: 'stale',
  CONFLICTED: 'blocked',
  UNSUPPORTED: 'unavailable',
}

/** Days between two ISO timestamps, or null when either is unusable. */
function ageDays(observed: string | null, fetched: string): number | null {
  if (!observed) return null
  const a = Date.parse(observed)
  const b = Date.parse(fetched)
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null
  return (b - a) / 86_400_000
}

/** A measured value, rendered without pretending an absent one is anything. */
function renderValue(value: unknown, unit: string | null, currency: string | null): string {
  if (value === null || value === undefined) return 'not reported'
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return 'not a finite number'
    const shown = Math.abs(value) >= 1000 ? value.toLocaleString() : String(value)
    if (unit === 'percent') return `${shown}%`
    if (unit === 'fraction') return `${(value * 100).toFixed(2)}%`
    if (unit === 'usd') return `${currency ?? 'USD'} ${shown}`
    return unit ? `${shown} ${unit}` : shown
  }
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return String(value)
}

function Record({ record }: { record: EvidenceRecord }) {
  const age = ageDays(record.observed_at, record.fetched_at)
  return (
    <div className="ci__record" data-stale={record.stale ? 'true' : undefined}>
      <div className="ci__record-head">
        <code className="ci__id">{record.evidence_id}</code>
        {record.stale ? <Status state="stale" label="STALE" /> : null}
      </div>
      <table className="sys-table sys-table--compact ci__fields">
        <tbody>
          <tr>
            <th scope="row">Value</th>
            <td>{renderValue(record.value, record.unit, record.currency)}</td>
          </tr>
          <tr>
            <th scope="row">Field</th>
            <td><code>{record.field}</code></td>
          </tr>
          <tr>
            <th scope="row">Source</th>
            <td>{record.provider} · {record.capability}</td>
          </tr>
          <tr>
            {/* Two rows, never one. When the world was in this state. */}
            <th scope="row">Observed</th>
            <td>{record.observed_at ?? 'not stated by the provider'}</td>
          </tr>
          <tr>
            {/* And when we asked. */}
            <th scope="row">Retrieved</th>
            <td>
              {record.fetched_at}
              {age !== null && age >= 1
                ? ` · ${age.toFixed(age >= 10 ? 0 : 1)} days after it was observed`
                : ''}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}

export default function ClaimInspector({
  claim, evidence, onClose,
}: {
  claim: Claim
  /** Every evidence record from the run, for resolving this claim's handles. */
  evidence: EvidenceRecord[]
  onClose: () => void
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const byId = new Map(evidence.map((e) => [e.evidence_id, e]))
  const resolved = claim.evidence_ids.map((id) => byId.get(id)).filter((e): e is EvidenceRecord => Boolean(e))
  // Kept, not discarded. A handle that does not resolve is the pipeline saying
  // a claim believes it has support that never arrived.
  const dangling = claim.evidence_ids.filter((id) => !byId.has(id))

  return (
    <aside className="sys-drawer" role="dialog" aria-modal="false" aria-label="Claim evidence">
      <header className="sys-drawer-head">
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="sys-lead">{claim.statement}</div>
          <div className="sys-meta">
            {claim.agent} · {claim.claim_type} · <code>{claim.claim_id}</code>
          </div>
        </div>
        <Status state={STATE[claim.validation_status] ?? 'unknown'} label={claim.validation_status} />
        <button className="sys-btn" onClick={onClose} aria-label="Close claim inspector">esc</button>
      </header>

      <div className="sys-drawer-body">
        {claim.validation_note ? (
          <section>
            <div className="sys-label">Validator</div>
            <Prose>{claim.validation_note}</Prose>
          </section>
        ) : null}

        <section>
          <div className="sys-label">
            Evidence ({resolved.length}
            {dangling.length ? ` resolved, ${dangling.length} missing` : ''})
          </div>

          {claim.evidence_ids.length === 0 ? (
            <EmptyLine label="No evidence">
              This claim cites nothing. It is a statement the pipeline made
              without a measured value behind it, which is why the validator
              does not mark such claims verified.
            </EmptyLine>
          ) : null}

          {resolved.map((record) => <Record key={record.evidence_id} record={record} />)}

          {dangling.length ? (
            <div className="ci__dangling">
              <Status state="unavailable" label="UNRESOLVED" />
              <Prose>
                {dangling.length === 1 ? 'This handle was cited but ' : 'These handles were cited but '}
                did not arrive in the run: {dangling.map((id) => <code key={id}>{id}</code>).reduce<React.ReactNode[]>(
                  (acc, el, i) => (i === 0 ? [el] : [...acc, ', ', el]), [],
                )}. The claim believes it has support that is not present — a
                fault in the pipeline rather than in the security.
              </Prose>
            </div>
          ) : null}
        </section>

        <section>
          <div className="sys-label">Reading this</div>
          <Prose>
            Observed is when the world was in this state; retrieved is when we
            asked. A large gap between them means the figure is real and old,
            which is different from wrong and different from current.
          </Prose>
        </section>
      </div>
    </aside>
  )
}
