'use client'

/**
 * The traceability surface: one security's claims and whether they hold up.
 *
 * This is where the architecture's central assertion is checkable by hand. A
 * sentence the product shows about a security should reduce to claims here,
 * and each claim to the evidence handles beside it. A claim marked
 * UNSUPPORTED or CONFLICTED is the system reporting that one of its own
 * statements did not survive checking — which is the behaviour worth showing
 * an operator, so failures are rendered first rather than filtered out.
 */

import { useState } from 'react'

import { DataTable } from '@/components/system/DataTable'
import { EmptyLine, Panel, Prose, StateBlock, Status, Strip } from '@/components/system'
import { authFetch } from '@/lib/persistence'

interface Claim {
  claim_id: string
  agent: string
  claim_type: string
  statement: string
  evidence_ids: string[]
  validation_status: string
  validation_note: string | null
}

interface AgentRow {
  agent: string
  status: string
  claims: unknown[]
  missing: string[]
  warnings: string[]
  latency_ms: number
}

interface Report {
  status: string
  verified: number
  partial: number
  conflicted: number
  stale: number
  unsupported: number
  narrative_admissible: boolean
  rejected_reason: string | null
  findings: Array<{ claim_id: string; status: string; rule: string; detail: string }>
}

interface Payload {
  symbol: string
  status: string
  detail?: string
  model_signal: string | null
  confidence: number | null
  risk_score: number | null
  validation: Report
  agents: AgentRow[]
  claims: Claim[]
  evidence: unknown[]
  agent_schema_version: string
}

const STATE: Record<string, 'live' | 'stale' | 'unavailable' | 'blocked'> = {
  VERIFIED: 'live',
  PARTIAL: 'stale',
  STALE: 'stale',
  CONFLICTED: 'unavailable',
  UNSUPPORTED: 'blocked',
}

export default function EvidenceAudit() {
  const [symbol, setSymbol] = useState('')
  const [data, setData] = useState<Payload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function run(e: React.FormEvent) {
    e.preventDefault()
    const clean = symbol.trim().toUpperCase()
    if (!clean) return
    setBusy(true)
    setError(null)
    setData(null)
    try {
      const res = await authFetch(`/api/agents/${encodeURIComponent(clean)}/validation`)
      if (!res.ok) {
        setError(`The evidence pipeline answered ${res.status}.`)
      } else {
        setData((await res.json()) as Payload)
      }
    } catch {
      setError('The evidence pipeline could not be reached.')
    } finally {
      setBusy(false)
    }
  }

  // Failures first: a passing claim is unremarkable, a refused one is the
  // reason this page exists.
  const ordered = data?.claims
    ? [...data.claims].sort((a, b) => {
        const rank = (s: string) => (s === 'VERIFIED' ? 1 : 0)
        return rank(a.validation_status) - rank(b.validation_status)
      })
    : []

  return (
    <Panel title="Evidence audit" subtitle="claims, sources and whether they hold up">
      <Prose>
        Runs the agent pipeline for one security and shows every claim it made
        with the evidence supporting it. Nothing here decides anything — the
        signal is the scoring engine&apos;s and travels alongside.
      </Prose>

      <form onSubmit={run} className="bg__search" role="search">
        <label htmlFor="audit-symbol" className="visually-hidden">Ticker symbol</label>
        <input
          id="audit-symbol"
          value={symbol}
          onChange={(ev) => setSymbol(ev.target.value)}
          placeholder="Ticker, e.g. MSFT"
          autoComplete="off"
          spellCheck={false}
        />
        <button type="submit" disabled={busy}>{busy ? 'Running…' : 'Audit'}</button>
      </form>

      {error ? <StateBlock state="unavailable" title="Pipeline unavailable" detail={error} /> : null}

      {data && data.status !== 'ok' ? (
        <StateBlock
          state="unavailable"
          title={`No evidence for ${data.symbol}`}
          detail={data.detail ?? 'no provider answered'}
        />
      ) : null}

      {data && data.status === 'ok' ? (
        <>
          <Strip
            metrics={[
              { label: 'Model signal', value: data.model_signal ?? '—' },
              { label: 'Validation', value: data.validation.status },
              { label: 'Claims', value: data.claims.length, kind: 'count' },
              { label: 'Evidence', value: data.evidence.length, kind: 'count' },
            ]}
          />
          <Strip
            metrics={[
              { label: 'Verified', value: data.validation.verified, kind: 'count' },
              { label: 'Partial', value: data.validation.partial, kind: 'count' },
              { label: 'Conflicted', value: data.validation.conflicted, kind: 'count' },
              { label: 'Stale', value: data.validation.stale, kind: 'count' },
              { label: 'Unsupported', value: data.validation.unsupported, kind: 'count' },
            ]}
          />

          {!data.validation.narrative_admissible ? (
            <StateBlock
              state="blocked"
              title="Narrative withheld"
              detail={data.validation.rejected_reason ?? 'it failed validation'}
            >
              <Prose>
                The generated explanation did not survive checking, so the
                deterministic summary is served instead. A narrative that fails
                validation is withheld rather than shown with a footnote.
              </Prose>
            </StateBlock>
          ) : null}

          <DataTable
            rows={data.agents}
            rowKey={(a) => a.agent}
            density="compact"
            filterPlaceholder="filter agents"
            empty="No agent reported."
            columns={[
              { key: 'agent', header: 'Agent', sort: (a) => a.agent, render: (a) => a.agent },
              { key: 'status', header: 'Status', sort: (a) => a.status, render: (a) => a.status },
              {
                key: 'claims', header: 'Claims', numeric: true,
                sort: (a) => a.claims.length, render: (a) => a.claims.length,
              },
              {
                key: 'missing', header: 'Missing inputs',
                text: (a) => a.missing.join(' '),
                sort: (a) => a.missing.length,
                render: (a) => <span className="xp__why">{a.missing.join(', ') || '—'}</span>,
              },
              {
                key: 'latency', header: 'Latency', unit: 'ms', numeric: true,
                sort: (a) => a.latency_ms, render: (a) => a.latency_ms.toFixed(1),
              },
            ]}
          />

          {ordered.length === 0 ? (
            <EmptyLine label="Claims">No agent made a claim about this security.</EmptyLine>
          ) : (
            <ul className="bg__reasons">
              {ordered.map((c) => (
                <li key={c.claim_id} className="bg__reason">
                  <span className="bg__reason-label">
                    <Status state={STATE[c.validation_status] ?? 'unknown'} label={c.validation_status} />
                    {' '}{c.statement}
                  </span>
                  <span className="bg__reason-detail">
                    {c.agent} · {c.evidence_ids.join(', ') || 'no evidence'}
                    {c.validation_note ? ` · ${c.validation_note}` : ''}
                  </span>
                </li>
              ))}
            </ul>
          )}

          <Prose>Schema {data.agent_schema_version}</Prose>
        </>
      ) : null}
    </Panel>
  )
}
