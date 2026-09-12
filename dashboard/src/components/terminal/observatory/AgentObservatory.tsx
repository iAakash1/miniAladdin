'use client'

/**
 * One analysis run, as it actually executed.
 *
 * Every value here comes from a real graph invocation: the node names, their
 * latencies, each specialist's status and missing inputs, what reconciliation
 * counted, what validation concluded, and which branch the critic took. There
 * is no synthetic pipeline animation anywhere in this component — a fake
 * progress display in a research tool is worse than none, because it teaches a
 * reader to trust a picture that is not measuring anything.
 *
 * The decision is shown inside the pipeline rather than at the end of it, at
 * the node that produces it, because the point being demonstrated is that the
 * scoring engine decides and everything downstream explains.
 */

import { useState } from 'react'

import { AvailabilityNote, isAvailable } from '@/components/system/Availability'
import { EmptyLine, Panel, Prose, StateBlock, Status, Strip } from '@/components/system'
import { authFetch } from '@/lib/persistence'

const dash = '—'

interface AgentRow {
  agent: string
  status: string
  claims: number
  evidence: number
  missing: string[]
  warnings: string[]
  latency_ms: number
}

interface Run {
  status?: string
  message?: string | null
  reason?: string | null
  symbol: string
  run_id: string
  model_signal: string | null
  confidence: number | null
  risk_score: number | null
  data_completeness: number | null
  nodes: Array<{ node: string; latency_ms: number }>
  agents: AgentRow[]
  reconciliation: {
    claims: number
    evidence: number
    providers: number
    independent_sources: number
    agents_ok: string[]
    agents_degraded: string[]
    missing_inputs: string[]
  } | null
  validation: {
    status: string
    verified: number
    partial: number
    conflicted: number
    stale: number
    unsupported: number
    narrative_admissible: boolean
    rejected_reason: string | null
  } | null
  narrative_source: string
  critic: Record<string, unknown> | null
  warnings: string[]
  errors: string[]
  fallbacks: string[]
  graph_version: string
  agent_schema_version: string
  scoring_version: string | null
}

const AGENT_STATE: Record<string, 'live' | 'stale' | 'unavailable'> = {
  ok: 'live', partial: 'stale', unavailable: 'unavailable', error: 'unavailable',
}

/** Specialists in execution order, then the stages that follow them. */
const SPECIALISTS = ['market', 'fundamental', 'technical', 'news', 'macro']

export default function AgentObservatory() {
  const [symbol, setSymbol] = useState('')
  const [run, setRun] = useState<Run | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function go(e: React.FormEvent) {
    e.preventDefault()
    const clean = symbol.trim().toUpperCase()
    if (!clean) return
    setBusy(true)
    setError(null)
    setRun(null)
    try {
      const res = await authFetch(`/api/analysis-runs/${encodeURIComponent(clean)}`)
      if (!res.ok) setError(`The pipeline answered ${res.status}.`)
      else setRun((await res.json()) as Run)
    } catch {
      setError('The analysis pipeline could not be reached.')
    } finally {
      setBusy(false)
    }
  }

  const timing = (node: string) =>
    run?.nodes.find((n) => n.node === node)?.latency_ms ?? null

  return (
    <>
      <Panel title="Analysis run" subtitle="the pipeline as it executed">
        <Prose>
          Runs the full graph for one security and shows what each stage did.
          Every latency and status below is measured from the run — nothing here
          is simulated.
        </Prose>
        <form onSubmit={go} className="bg__search" role="search">
          <label htmlFor="obs-symbol" className="visually-hidden">Ticker symbol</label>
          <input
            id="obs-symbol"
            value={symbol}
            onChange={(ev) => setSymbol(ev.target.value)}
            placeholder="Ticker, e.g. MSFT"
            autoComplete="off"
            spellCheck={false}
          />
          <button type="submit" disabled={busy}>{busy ? 'Running…' : 'Run analysis'}</button>
        </form>
        {busy ? (
          <StateBlock state="waking" title="Executing the graph" detail="providers, agents, validation" />
        ) : null}
        {error ? <StateBlock state="unavailable" title="Pipeline unavailable" detail={error} /> : null}
        {run && !isAvailable(run) ? <AvailabilityNote payload={run} /> : null}
      </Panel>

      {run && isAvailable(run) ? (
        <>
          <Panel title={`Run ${run.run_id}`} subtitle={run.symbol}>
            <Strip
              metrics={[
                { label: 'Graph', value: run.graph_version },
                { label: 'Agent schema', value: run.agent_schema_version },
                { label: 'Scoring', value: run.scoring_version ?? dash },
                { label: 'Narrative', value: run.narrative_source },
              ]}
            />
          </Panel>

          <Panel title="Specialists" subtitle="fanned out over one evidence snapshot">
            <ol className="obs__stages">
              {SPECIALISTS.map((name) => {
                const agent = run.agents.find((a) => a.agent === name)
                return (
                  <li key={name} className="obs__stage">
                    <span className="obs__name">{name}</span>
                    <Status
                      state={agent ? AGENT_STATE[agent.status] ?? 'unknown' : 'unavailable'}
                      label={agent ? agent.status : 'not run'}
                    />
                    <span className="obs__num">
                      {agent ? `${agent.claims} claims` : dash}
                    </span>
                    <span className="obs__num">
                      {timing(name) === null ? dash : `${timing(name)!.toFixed(1)} ms`}
                    </span>
                    <span className="obs__note">
                      {agent?.missing.length ? `missing: ${agent.missing.join(', ')}` : ''}
                    </span>
                  </li>
                )
              })}
            </ol>
          </Panel>

          {run.reconciliation ? (
            <Panel title="Reconciliation" subtitle={`${timing('reconcile')?.toFixed(1) ?? dash} ms`}>
              <Strip
                metrics={[
                  { label: 'Claims', value: run.reconciliation.claims, kind: 'count' },
                  { label: 'Evidence', value: run.reconciliation.evidence, kind: 'count' },
                  { label: 'Providers', value: run.reconciliation.providers, kind: 'count' },
                  { label: 'Independent sources', value: run.reconciliation.independent_sources, kind: 'count' },
                ]}
              />
              <Prose>
                Providers and independent sources differ when vendors resell one
                upstream. Counting those twice would inflate apparent
                corroboration exactly where a reader would lean on it.
              </Prose>
              {run.reconciliation.agents_degraded.length ? (
                <Prose>Degraded this run: {run.reconciliation.agents_degraded.join(', ')}.</Prose>
              ) : null}
            </Panel>
          ) : null}

          {run.validation ? (
            <Panel title="Validation" subtitle={`${timing('validate')?.toFixed(1) ?? dash} ms`}>
              <Strip
                metrics={[
                  { label: 'Verified', value: run.validation.verified, kind: 'count' },
                  { label: 'Partial', value: run.validation.partial, kind: 'count' },
                  { label: 'Conflicted', value: run.validation.conflicted, kind: 'count' },
                  { label: 'Stale', value: run.validation.stale, kind: 'count' },
                  { label: 'Unsupported', value: run.validation.unsupported, kind: 'count' },
                ]}
              />
              {!run.validation.narrative_admissible ? (
                <StateBlock
                  state="blocked"
                  title="Narrative withheld"
                  detail={run.validation.rejected_reason ?? 'it failed validation'}
                />
              ) : null}
            </Panel>
          ) : null}

          <Panel title="Quantitative engine" subtitle={`${timing('score')?.toFixed(1) ?? dash} ms`}>
            <Prose>
              The only stage that produces a signal, and it does not compute one
              — it reads the scorecard the production engine built. Nothing
              downstream may change these four values.
            </Prose>
            <Strip
              metrics={[
                { label: 'Model signal', value: run.model_signal ?? dash },
                { label: 'Risk', value: run.risk_score, kind: 'count' },
                { label: 'Confidence', value: run.confidence, kind: 'count' },
                {
                  label: 'Data completeness',
                  value: run.data_completeness === null ? dash
                    : `${Math.round(run.data_completeness * 100)}%`,
                },
              ]}
            />
          </Panel>

          <Panel title="Critic" subtitle="optional, and cannot change a number">
            {run.critic ? (
              <dl className="av__dl">
                {Object.entries(run.critic).map(([k, v]) => (
                  <div key={k}>
                    <dt>{k}</dt>
                    <dd>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <EmptyLine label="Critic">Not recorded for this run.</EmptyLine>
            )}
          </Panel>

          {run.errors.length || run.fallbacks.length || run.warnings.length ? (
            <Panel title="What degraded">
              {run.errors.length ? <Prose>Errors: {run.errors.join('; ')}</Prose> : null}
              {run.fallbacks.length ? <Prose>Fallbacks: {run.fallbacks.join(', ')}</Prose> : null}
              {run.warnings.length ? <Prose>Warnings: {run.warnings.slice(0, 6).join('; ')}</Prose> : null}
            </Panel>
          ) : null}
        </>
      ) : null}
    </>
  )
}
