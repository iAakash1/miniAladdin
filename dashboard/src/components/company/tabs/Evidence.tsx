'use client'

import Link from 'next/link'
import { Fragment, useEffect, useMemo, useState } from 'react'

import { Claims } from '../Claims'
import { citationIndex, sourceLabel, synthesisStatus } from '../Synthesis'
import { providerSet } from '../derive'
import SeriesIntegrityPanel from '@/components/terminal/SeriesIntegrityPanel'
import DataQuality from '@/components/terminal/security/DataQuality'
import ModelValidation from '@/components/terminal/security/ModelValidation'
import { sanitizeError } from '@/lib/providerHealth'
import { quantFetch } from '@/lib/quantApi'
import type { AiEvidenceItem, Analysis, ProvenanceInput } from '@/lib/types'

const HEALTH_TONE: Record<string, 'pos' | 'warn' | 'neg'> = { ok: 'pos', degraded: 'warn', missing: 'neg' }

const STATE_TONE: Record<string, 'pos' | 'warn' | 'neg' | 'muted' | 'info'> = {
  VERIFIED: 'pos', AGREED: 'pos',
  PARTIAL: 'warn', STALE: 'warn', SINGLE_SOURCE: 'info',
  CONFLICTED: 'neg', UNSUPPORTED: 'neg',
  UNAVAILABLE: 'muted',
}

function StateTag({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="sys-null">—</span>
  const v = value.toUpperCase()
  return <span className="ev-tag" data-tone={STATE_TONE[v] ?? 'muted'}>{v.replace(/_/g, ' ').toLowerCase()}</span>
}

function Summary({ a }: { a: Analysis }) {
  const p = a.provenance?.summary
  const vendors = providerSet(a)
  const q = a.quant
  const dataLoss = (q?.confidenceLosses ?? [])
    .filter((l) => /data|fresh/i.test(l.component))
    .reduce((s, l) => s + l.points, 0)
  const cells: Array<[string, React.ReactNode, string?]> = [
    ['Evidence quality', a.decisionQuality ? a.decisionQuality.grade.toLowerCase() : '—', a.decisionQuality?.summary],
    ['Inputs', p ? `${p.ok} ok · ${p.degraded} degraded · ${p.missing} missing` : '—'],
    ['Providers contributing', String(vendors.length), vendors.join(', ')],
    ['Data completeness', q ? `${Math.round(q.dataCompleteness * 100)}%` : '—', 'Share of the engine’s factors that could be computed'],
    ['Confidence lost to data', q ? `−${dataLoss} pts` : '—', 'Completeness and freshness deductions'],
    ['Price sources', a.consensusPrice ? `${a.consensusPrice.agreement} agree` : '—'],
  ]
  return (
    <div className="sys-strip sys-strip--wrap">
      {cells.map(([k, v, title]) => (
        <div className="sys-strip-item" key={k} title={title}>
          <span className="k">{k}</span>
          <span className="v">{v}</span>
        </div>
      ))}
    </div>
  )
}

function Inputs({ inputs }: { inputs: ProvenanceInput[] }) {
  const [open, setOpen] = useState<string | null>(null)
  return (
    <section className="sys-panel">
      <header className="sys-panel-head">
        <div className="sys-panel-head__title">
          <h2 className="sys-panel-title">Decision inputs</h2>
          <span className="sys-panel-sub">every input the engine consumed, who answered, and how well</span>
        </div>
      </header>
      <div className="sys-scroll-x">
        <table className="sys-table ev-inputs">
          <thead>
            <tr>
              <th scope="col">Input</th>
              <th scope="col">Answered by</th>
              <th scope="col">Consulted</th>
              <th scope="col">Health</th>
              <th scope="col" className="num">Confidence</th>
              <th scope="col">Age</th>
              <th scope="col">Used for</th>
            </tr>
          </thead>
          <tbody>
            {inputs.map((i) => {
              const expanded = open === i.label
              const hasDetail = Boolean(i.contributors?.length || i.note || i.detail)
              return (
                <Fragment key={i.label}>
                  <tr data-selected={expanded}>
                    <td>
                      {hasDetail ? (
                        <button
                          type="button"
                          className="ev-expand"
                          aria-expanded={expanded}
                          onClick={() => setOpen(expanded ? null : i.label)}
                        >
                          <span aria-hidden>{expanded ? '−' : '+'}</span>
                          {i.label}
                        </button>
                      ) : i.label}
                    </td>
                    <td className="ev-mono">{i.source ?? <span className="sys-null">none</span>}</td>
                    <td className="ev-mono ev-dim">{i.sources_consulted.join(', ')}</td>
                    <td><span className="ev-tag" data-tone={HEALTH_TONE[i.health] ?? 'muted'}>{i.health}</span>{i.stale ? <span className="ev-tag" data-tone="warn">stale</span> : null}</td>
                    <td className="num">{i.confidence === null ? '—' : i.confidence.toFixed(2)}</td>
                    <td className="ev-dim">{i.age ?? '—'}{i.cached ? ' · cached' : ''}</td>
                    <td className="ev-dim ev-wrap">{i.used_for.join(', ')}</td>
                  </tr>
                  {expanded ? (
                    <tr className="ev-detail">
                      <td colSpan={7}>
                        {i.detail ? <p>{i.detail}</p> : null}
                        {i.note ? <p className="sys-warn">{sanitizeError(i.note)}</p> : null}
                        {i.contributors?.length ? (
                          <table className="ev-contrib">
                            <thead>
                              <tr>
                                <th scope="col">Vendor</th>
                                <th scope="col">Outcome</th>
                                <th scope="col" className="num">Latency</th>
                                <th scope="col">Reason</th>
                              </tr>
                            </thead>
                            <tbody>
                              {i.contributors.map((c) => (
                                <tr key={c.provider}>
                                  <td className="ev-mono">{c.provider}</td>
                                  <td><span className="ev-tag" data-tone={c.ok ? 'pos' : c.status === 'not_entitled' ? 'warn' : 'neg'}>{c.ok ? 'answered' : c.status.replace(/_/g, ' ')}</span></td>
                                  <td className="num">{Math.round(c.latency_ms)} ms</td>
                                  <td className="ev-dim">{c.error ? sanitizeError(c.error) : '—'}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        ) : null}
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

interface ModelView {
  deployment_status: string
  message: string
  prediction: number | null
  model: string | null
  disclosure?: string
}

/** Whether any research model is serving this symbol. It is not part of the signal unless promoted. */
function ModelStatus({ symbol }: { symbol: string }) {
  const [view, setView] = useState<{ for: string; data: ModelView | null } | null>(null)
  useEffect(() => {
    let alive = true
    quantFetch<ModelView>(`/api/quant/symbol/${encodeURIComponent(symbol)}`)
      .then((r) => { if (alive) setView({ for: symbol, data: r.ok ? r.data : null }) })
      .catch(() => { if (alive) setView({ for: symbol, data: null }) })
    return () => { alive = false }
  }, [symbol])
  const v = view?.for === symbol ? view : null
  const served = v?.data?.deployment_status === 'PRODUCTION' && v.data.prediction !== null
  return (
    <section className="sys-panel">
      <header className="sys-panel-head">
        <div className="sys-panel-head__title">
          <h2 className="sys-panel-title">Model Lab</h2>
          <span className="sys-panel-sub">research models never set this signal unless promoted through the gates</span>
        </div>
        <Link className="cw-more" href="/terminal/lab">Open Model Lab</Link>
      </header>
      <div className="sys-panel-body cw-model">
        {!v ? (
          <span className="cw-muted">Reading deployment status…</span>
        ) : !v.data ? (
          <span className="cw-muted">Deployment status could not be read; nothing from the Model Lab is shown here.</span>
        ) : (
          <>
            <span className="ev-tag" data-tone={served ? 'pos' : 'muted'}>{served ? v.data.deployment_status.toLowerCase() : 'no validated model'}</span>
            <p className="cw-model__msg">
              {served ? <>Serving <b className="sys-num">{v.data.prediction}</b> from {v.data.model}.</> : v.data.message}
              {v.data.disclosure ? <span className="cw-model__disc"> {v.data.disclosure}</span> : null}
            </p>
          </>
        )}
      </div>
    </section>
  )
}

const FILTERS = ['all', 'verified', 'partial', 'conflicted', 'stale', 'unsupported'] as const

function Ledger({ a }: { a: Analysis }) {
  const ai = a.ai
  const status = synthesisStatus(ai)
  const index = useMemo(() => citationIndex(ai), [ai])
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>('all')
  const evidence: AiEvidenceItem[] = ai?.evidence ?? []
  const shown = evidence.filter((e) => filter === 'all' || (e.validation ?? '').toLowerCase() === filter)
  return (
    <section className="sys-panel" id="ledger" style={{ scrollMarginTop: 56 }}>
      <header className="sys-panel-head">
        <div className="sys-panel-head__title">
          <h2 className="sys-panel-title">Evidence ledger</h2>
          <span className="sys-panel-sub">the values the explanation layer was allowed to cite</span>
        </div>
        {evidence.length ? (
          <div className="sys-seg" role="group" aria-label="Filter by validation">
            {FILTERS.map((f) => (
              <button key={f} type="button" className="sys-btn" aria-pressed={filter === f} onClick={() => setFilter(f)}>{f}</button>
            ))}
          </div>
        ) : null}
      </header>
      {evidence.length ? (
        <div className="sys-scroll-x">
          <table className="sys-table sys-table--compact">
            <thead>
              <tr>
                <th scope="col" className="num">Ref</th>
                <th scope="col">Evidence id</th>
                <th scope="col">Source</th>
                <th scope="col" className="num">Value</th>
                <th scope="col">Observed</th>
                <th scope="col">Validation</th>
                <th scope="col">Reconciliation</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((e) => {
                const n = index.number(e.id)
                return (
                  <tr key={e.id}>
                    <td className="num">{n ?? <span className="ev-dim">·</span>}</td>
                    <td className="ev-mono">{e.id}</td>
                    <td className="ev-dim">{sourceLabel(e.source)}</td>
                    <td className="num ev-value" title={String(e.value)}>{String(e.value ?? '—')}{e.unit ? ` ${e.unit}` : ''}</td>
                    <td className="ev-dim ev-mono">{e.observed_at ? e.observed_at.slice(0, 10) : e.freshness ?? '—'}</td>
                    <td><StateTag value={e.validation} /></td>
                    <td><StateTag value={e.reconciliation} /></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="cw-muted cw-pad">
          {status.generated
            ? 'The explanation layer returned no evidence envelope for this run.'
            : `The explanation layer did not run for this analysis (${status.reason}), so no claims were made and none are cited.`}
        </p>
      )}
      <footer className="sys-panel-foot">
        <span>Numbered refs are the items the synthesis actually cited; unnumbered items were available but unused.</span>
      </footer>
    </section>
  )
}

export default function Evidence({ analysis: a }: { analysis: Analysis }) {
  const [track, setTrack] = useState(false)
  return (
    <div className="cw-stack">
      <Summary a={a} />
      {a.provenance ? <Inputs inputs={a.provenance.inputs} /> : null}
      <div className="cw-grid cw-grid--side">
        <Claims a={a} />
        <div className="cw-stack">
          {a.seriesIntegrity ? <SeriesIntegrityPanel integrity={a.seriesIntegrity} /> : null}
          <ModelStatus symbol={a.ticker} />
        </div>
      </div>
      <Ledger a={a} />
      <DataQuality symbol={a.ticker} />
      <section className="sys-panel">
        <header className="sys-panel-head">
          <div className="sys-panel-head__title">
            <h2 className="sys-panel-title">Signal track record</h2>
            <span className="sys-panel-sub">how the deterministic signal has scored this name historically</span>
          </div>
          {!track ? <button type="button" className="sys-btn" onClick={() => setTrack(true)}>Run backtest</button> : null}
        </header>
        {!track ? (
          <p className="cw-muted cw-pad">A per-name backtest replays the engine over this company&apos;s history. It runs on request because it is compute-heavy.</p>
        ) : null}
      </section>
      {track ? <ModelValidation ticker={a.ticker} /> : null}
      <div className="cw-links">
        <Link className="sys-btn" href={`/terminal/agents/${encodeURIComponent(a.ticker)}`}>Run the agent pipeline — claim-by-claim validation</Link>
        <Link className="sys-btn sys-btn--ghost" href={`/evidence/${encodeURIComponent(a.ticker)}`}>Open the evidence inspector</Link>
      </div>
    </div>
  )
}
