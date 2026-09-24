'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

import type { ResearchRun } from './useCompany'
import { providerSet, signalTone, verdictWord } from './derive'
import { FREE_DAILY_LIMIT } from '@/lib/usage'
import type { Analysis } from '@/lib/types'

const GRADE_TONE: Record<string, 'pos' | 'info' | 'warn' | 'neg'> = {
  STRONG: 'pos', ACCEPTABLE: 'info', WEAK: 'warn', INSUFFICIENT: 'neg',
}
const RISK_TONE: Record<string, 'pos' | 'warn' | 'neg'> = { LOW: 'pos', MEDIUM: 'warn', HIGH: 'neg' }

const RISK_LABEL: Record<string, string> = {
  downside_dev: 'downside deviation', tail_risk: 'tail risk', drawdown: 'drawdown state',
  vol_regime: 'volatility regime', beta: 'beta', idiosyncratic: 'idiosyncratic share',
  liquidity: 'liquidity', macro: 'macro', sector: 'sector',
}

function ordinal(n: number): string {
  const r = Math.round(n)
  const s = ['th', 'st', 'nd', 'rd']
  const v = r % 100
  return `${r}${s[(v - 20) % 10] ?? s[v] ?? s[0]}`
}

function Cell({ label, children, sub, tone }: {
  label: string
  children: React.ReactNode
  sub?: React.ReactNode
  tone?: 'pos' | 'neg' | 'warn' | 'info' | 'muted'
}) {
  return (
    <div className="sig-cell" data-tone={tone}>
      <span className="sig-cell__k">{label}</span>
      <span className="sig-cell__v">{children}</span>
      {sub ? <span className="sig-cell__s">{sub}</span> : null}
    </div>
  )
}

function Elapsed({ since }: { since: number }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(t)
  }, [])
  return <span className="sys-num">{Math.max(0, Math.round((now - since) / 1000))}s</span>
}

/** The six deterministic readings of a completed run. */
export function SignalGrid({ a }: { a: Analysis }) {
  const q = a.quant
  const tone = signalTone(a.riskAdjusted)
  const losses = [...(q?.confidenceLosses ?? [])].sort((x, y) => y.points - x.points)
  const topRisk = [...(q?.riskComponents ?? [])].sort((x, y) => y.contribution - x.contribution)[0]
  const p = a.provenance?.summary
  const vendors = providerSet(a)
  const cp = a.consensusPrice
  const si = a.seriesIntegrity
  const conflicts = (a.statements?.conflicts.length ?? 0) + (a.profile?.conflicts?.length ?? 0)
    + (cp?.conflict ? 1 : 0) + (si?.conflict_count ? 1 : 0)
  const dq = a.decisionQuality

  return (
    <div className="sig-grid">
      <Cell
        label="Signal"
        tone={tone}
        sub={q ? (
          <>
            {a.verdict !== a.riskAdjusted ? `raw ${verdictWord(a.verdict)}, dampened · ` : 'raw signal agrees · '}
            score <span className="sys-num">{q.rawScore >= 0 ? '+' : ''}{q.rawScore.toFixed(2)}</span>
            {' · '}momentum gate <span className="sys-num">×{q.macroGate.toFixed(2)}</span>
          </>
        ) : 'scorecard not returned for this run'}
      >
        <span className="sig-verdict" data-tone={tone}>{verdictWord(a.riskAdjusted)}</span>
      </Cell>

      <Cell
        label="Confidence"
        sub={losses.length
          ? losses.slice(0, 2).map((l) => `−${l.points} ${l.component.toLowerCase()}`).join(' · ')
          : 'no deductions recorded'}
      >
        {a.engineConfidence !== null
          ? <><span className="sys-num">{a.engineConfidence}</span><span className="sig-unit">/100</span></>
          : <span className="sys-null">—</span>}
      </Cell>

      <Cell
        label="Risk"
        tone={a.riskLevel ? RISK_TONE[a.riskLevel] : undefined}
        sub={topRisk ? `largest: ${RISK_LABEL[topRisk.name] ?? topRisk.name}, ${ordinal(topRisk.percentile)} pct` : undefined}
      >
        {q ? <><span className="sys-num">{q.riskScore}</span><span className="sig-unit">/100</span></> : null}
        {a.riskLevel ? <span className="sig-level">{a.riskLevel.toLowerCase()}</span> : null}
        {!q && !a.riskLevel ? <span className="sys-null">—</span> : null}
      </Cell>

      <Cell
        label="Evidence quality"
        tone={dq ? GRADE_TONE[dq.grade] : undefined}
        sub={dq ? (dq.reasons.length ? dq.reasons.join(', ').replace(/_/g, ' ').toLowerCase() : dq.summary) : 'not graded for this run'}
      >
        {dq ? dq.grade.toLowerCase() : <span className="sys-null">—</span>}
      </Cell>

      <Cell
        label="Inputs"
        tone={p ? (p.missing ? 'warn' : p.degraded ? 'info' : 'pos') : undefined}
        sub={`${vendors.length} provider${vendors.length === 1 ? '' : 's'} contributed${a.elapsedSeconds !== null ? ` · ${a.elapsedSeconds.toFixed(1)}s run` : ''}`}
      >
        {p ? (
          <span className="sig-inputs">
            <span><b className="sys-num">{p.ok}</b> ok</span>
            <span><b className="sys-num">{p.degraded}</b> degraded</span>
            <span><b className="sys-num">{p.missing}</b> missing</span>
          </span>
        ) : <span className="sys-null">—</span>}
      </Cell>

      <Cell
        label="Provider agreement"
        tone={conflicts ? 'warn' : cp && cp.provider_count > 1 ? 'pos' : 'muted'}
        sub={si && si.providers.length > 1
          ? `history ${si.agreement_pct.toFixed(1)}% agree over ${si.shared_sessions} sessions`
          : 'price history from one provider'}
      >
        {cp ? (
          cp.provider_count > 1
            ? <><span className="sys-num">{cp.agreeing}/{cp.provider_count}</span><span className="sig-unit">price sources agree</span></>
            : <span className="sig-level">single source</span>
        ) : <span className="sys-null">—</span>}
        {conflicts ? <span className="sig-flag">{conflicts} conflict{conflicts === 1 ? '' : 's'}</span> : null}
      </Cell>
    </div>
  )
}

export default function SignalState({ run, onRetry, onUpgrade }: {
  run: ResearchRun
  onRetry: () => void
  onUpgrade: () => void
}) {
  const a = run.status === 'ready' ? run.analysis : null
  return (
    <section className="sig" aria-label="Deterministic analysis">
      <header className="sig-head">
        <span className="sig-head__k">System output</span>
        <span className="sig-head__note">
          Deterministic engine{a?.quant?.modelVersion ? ` ${a.quant.modelVersion}` : ''} · no model or LLM sets these values
        </span>
        <span className="sig-head__end">
          {run.status === 'ready' && a?.provenance?.generated_at
            ? <>computed {new Date(a.provenance.generated_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</>
            : null}
          <Link href="/terminal/methodology" className="sig-link">How it is computed</Link>
        </span>
      </header>

      {run.status === 'ready' ? <SignalGrid a={run.analysis} /> : null}

      {run.status === 'waiting' || run.status === 'running' ? (
        <div className="sig-progress" role="status" aria-live="polite">
          <div className="sig-progress__line">
            <span className="sig-progress__bar" aria-hidden />
            <span>
              {run.status === 'waiting' ? 'Establishing session' : 'Building research'}
              {run.status === 'running' ? <> · <Elapsed since={run.startedAt} /></> : null}
            </span>
          </div>
          <p className="sig-progress__note">
            Scoring, provider reconciliation, SEC retrieval and the grounded explanation run
            server-side against every configured provider — typically 20 to 60 seconds. Price and
            history above are already live.
          </p>
          <div className="sig-grid sig-grid--skeleton" aria-hidden>
            {Array.from({ length: 6 }, (_, i) => (
              <div className="sig-cell" key={i}>
                <span className="sys-skeleton" style={{ width: 70, height: 8 }} />
                <span className="sys-skeleton" style={{ width: 90, height: 18, marginTop: 6 }} />
                <span className="sys-skeleton" style={{ width: '80%', height: 8, marginTop: 6 }} />
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {run.status === 'limited' ? (
        <div className="sig-state">
          <p className="sig-state__title">Daily research limit reached</p>
          <p className="sig-state__detail">
            Free accounts run {FREE_DAILY_LIMIT} full analyses a day. Price and history above stay
            live; your Research log keeps every run you have already made.
          </p>
          <div className="sig-state__actions">
            <button type="button" className="sys-btn sys-btn--primary" onClick={onUpgrade}>Upgrade</button>
            <Link className="sys-btn" href="/terminal/vault">Open research log</Link>
          </div>
        </div>
      ) : null}

      {run.status === 'error' ? (
        <div className="sig-state" data-tone="neg">
          <p className="sig-state__title">The research run did not complete</p>
          <p className="sig-state__detail">
            {run.code === 404 ? 'No provider recognised this symbol.' : 'An upstream provider or the research service failed before a result was produced.'}
            {' '}No partial signal is shown in its place.
          </p>
          <details className="sig-state__diag">
            <summary>Diagnostics</summary>
            <code>{run.code ? `HTTP ${run.code} · ` : ''}{run.message.slice(0, 240)}</code>
          </details>
          <div className="sig-state__actions">
            <button type="button" className="sys-btn" onClick={onRetry}>Retry</button>
          </div>
        </div>
      ) : null}
    </section>
  )
}
