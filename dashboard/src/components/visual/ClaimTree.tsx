import type { ReactNode } from 'react'

import EntityMark from './EntityMark'
import { providerDomain } from '@/lib/identity'

export type EvidenceState =
  | 'AGREED' | 'SINGLE_SOURCE' | 'CONFLICTED' | 'STALE' | 'UNAVAILABLE'
  | 'VERIFIED' | 'PARTIAL' | 'UNSUPPORTED' | 'MISSING'

export interface Observation {
  provider: string
  value: ReactNode
  /** Omitted when the source does not say how this one reading compares. */
  state?: EvidenceState
  note?: string | null
}

export interface Claim {
  id: string
  label: string
  /** The reconciled value, when the claim has one. */
  value?: ReactNode
  state: EvidenceState
  detail?: ReactNode
  observations: Observation[]
}

const TONE: Record<EvidenceState, 'pos' | 'info' | 'warn' | 'neg' | 'muted'> = {
  AGREED: 'pos', VERIFIED: 'pos', SINGLE_SOURCE: 'info', PARTIAL: 'warn', STALE: 'warn',
  CONFLICTED: 'neg', UNSUPPORTED: 'neg', UNAVAILABLE: 'muted', MISSING: 'muted',
}

function State({ value }: { value: EvidenceState }) {
  return <span className="ev-tag" data-tone={TONE[value]}>{value.replace(/_/g, ' ').toLowerCase()}</span>
}

/**
 * Claims with the observations behind them, drawn as a tree. A reconciled
 * value never hides its inputs: each provider's own reading sits on a branch
 * beneath it, so agreement and disagreement are both visible.
 */
export default function ClaimTree({ claims }: { claims: Claim[] }) {
  return (
    <ul className="ctree">
      {claims.map((c) => (
        <li key={c.id} className="ctree-claim" data-tone={TONE[c.state]}>
          <div className="ctree-head">
            <span className="ctree-label">{c.label}</span>
            {c.value !== undefined ? <span className="ctree-value sys-num">{c.value}</span> : null}
            <State value={c.state} />
          </div>
          {c.detail ? <p className="ctree-detail">{c.detail}</p> : null}
          {c.observations.length ? (
            <ul className="ctree-obs">
              {c.observations.map((o) => (
                <li key={o.provider} className="ctree-ob">
                  <EntityMark domain={providerDomain(o.provider)} label={o.provider} size={16} />
                  <span className="ctree-provider">{o.provider}</span>
                  <span className="ctree-obval sys-num">{o.value}</span>
                  {o.state ? <State value={o.state} /> : <span />}
                  {o.note ? <span className="ctree-note">{o.note}</span> : null}
                </li>
              ))}
            </ul>
          ) : null}
        </li>
      ))}
    </ul>
  )
}
