'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

import type { ResearchState } from '@/components/system'
import { fetchMacroClient } from '@/lib/api'
import { type Observed, failed, observed } from '@/lib/observation'
import { summarize, type VendorSnapshot } from '@/lib/providerHealth'
import { readResource } from '@/lib/resource'
import type { Macro } from '@/lib/types'

type Tone = 'pos' | 'warn' | 'neg' | 'muted' | 'info'

interface QuantStatus {
  production?: number | null
}

/** Each study's manifest records whether it read the holdout. */
interface ResearchRecord {
  experiments?: Array<{ holdout_touched?: boolean }>
}

interface Governance {
  production: number | null
  /** Recorded, not verified: untouched is not the same claim as sealed. */
  holdout: 'untouched' | 'spent' | null
}

const STATE_TONE: Record<ResearchState, Tone> = {
  live: 'pos', production: 'pos', recorded: 'muted', stale: 'warn', waking: 'info',
  unavailable: 'muted', blocked: 'warn', experimental: 'info', candidate: 'info', unknown: 'muted',
}

/**
 * A polled read. A failed refresh never keeps the old value in the place a
 * current one would sit: it becomes `last-observed`, carrying the time it was
 * actually read, and the strip says so.
 */
function useRead<T>(load: () => Promise<T>, every: number): Observed<T> | null {
  const [read, setRead] = useState<Observed<T> | null>(null)
  useEffect(() => {
    let alive = true
    const run = () => {
      load()
        .then((value) => { if (alive) setRead(observed(value)) })
        .catch((e: Error) => { if (alive) setRead((prev) => failed(prev, e.message)) })
    }
    run()
    const timer = window.setInterval(run, every)
    return () => { alive = false; window.clearInterval(timer) }
  }, [load, every])
  return read
}

function clock(at: string | null): string {
  if (!at) return ''
  const d = new Date(at)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

/** The fact for a read that is not current, or null when it is. */
function notCurrent<T>(read: Observed<T> | null, render: (v: T) => string): { tone: Tone; value: string } | null {
  if (!read) return { tone: 'muted', value: 'reading…' }
  if (read.state === 'observed') return null
  if (read.state === 'last-observed' && read.value !== null) {
    return { tone: 'muted', value: `unavailable · last seen ${render(read.value)}, ${clock(read.at)}` }
  }
  return { tone: 'muted', value: 'status unavailable' }
}

const loadProviders = () =>
  readResource<{ providers?: Record<string, VendorSnapshot[]> }>('/api/providers/health', 'snapshot')
// /api/quant/status carries no holdout reading. The research record does —
// per study, the same flags Quant Lab lists — and is read from the same cache.
const loadGovernance = async (): Promise<Governance> => {
  const [status, record] = await Promise.all([
    readResource<QuantStatus>('/api/quant/status', 'snapshot'),
    readResource<ResearchRecord>('/api/quant/research-history', 'artifact').catch(() => null),
  ])
  const studies = record?.experiments ?? []
  return {
    production: status.production ?? null,
    holdout: studies.length === 0 ? null : studies.some((e) => e.holdout_touched === true) ? 'spent' : 'untouched',
  }
}
const loadMacro = () => fetchMacroClient().then((m) => {
  if (!m) throw new Error('macro unavailable')
  return m
})

function Fact({ tone, label, value, href, title }: {
  tone: Tone
  label: string
  value: string
  href?: string
  title?: string
}) {
  const body = (
    <>
      <span className="dot" data-tone={tone} aria-hidden />
      <span className="status-fact__label">{label}</span>
      <span className="status-fact__value">{value}</span>
    </>
  )
  return href ? (
    <Link href={href} className="status-fact" title={title}>{body}</Link>
  ) : (
    <span className="status-fact" title={title}>{body}</span>
  )
}

export default function StatusBar({ pageFacts }: {
  pageFacts?: Array<{ label: string; state: ResearchState; detail?: string }>
}) {
  const providers = useRead(loadProviders, 60_000)
  const governance = useRead(loadGovernance, 60_000)
  const macro = useRead<Macro>(loadMacro, 300_000)

  const providerLine = (p: { providers?: Record<string, VendorSnapshot[]> }) => {
    const sm = p.providers ? summarize(p.providers) : null
    if (!sm) return null
    return {
      tone: (sm.failing ? 'neg' : sm.constrained ? 'warn' : 'pos') as Tone,
      value: [
        `${sm.configured} of ${sm.vendors} configured`,
        sm.failing ? `${sm.failing} failing` : null,
        sm.constrained ? `${sm.constrained} constrained` : null,
      ].filter(Boolean).join(' · '),
    }
  }
  const p = providers?.state === 'observed' ? providers.value : null
  const providerFact = notCurrent(providers, (v) => providerLine(v)?.value ?? 'no vendors')
    ?? (p ? providerLine(p) : null)
    ?? { tone: 'muted' as Tone, value: 'status unavailable' }

  const macroLine = (m: Macro) => `${m.status.toLowerCase()}${m.source ? ` · ${m.source.toUpperCase()}` : ''}`
  const m = macro?.state === 'observed' ? macro.value : null
  const macroFact = notCurrent(macro, macroLine) ?? (
    !m || m.status === 'UNAVAILABLE'
      ? { tone: 'muted' as Tone, value: 'regime unavailable' }
      : {
        tone: (m.stale ? 'warn' : m.status === 'STABLE' || m.status === 'NORMAL' ? 'pos' : 'warn') as Tone,
        value: `${macroLine(m)}${m.stale ? ' · stale' : ''}`,
      })

  const governanceLine = (g: Governance) => [
    g.production && g.production > 0 ? `${g.production} model${g.production === 1 ? '' : 's'} promoted` : 'no model promoted',
    g.holdout === null ? 'holdout state not reported' : `holdout ${g.holdout}`,
  ].join(' · ')
  const g = governance?.state === 'observed' ? governance.value : null
  const governanceFact = notCurrent(governance, governanceLine) ?? (
    !g
      ? { tone: 'muted' as Tone, value: 'status unavailable' }
      : { tone: (g.holdout === 'spent' ? 'warn' : 'info') as Tone, value: governanceLine(g) })

  const build = (process.env.NEXT_PUBLIC_BUILD_SHA ?? 'unknown').slice(0, 7)

  return (
    <footer className="shell-status" aria-label="System status">
      <Fact label="Providers" href="/terminal/providers" {...providerFact}
        title="Data vendors configured in this deployment and their current health" />
      <Fact label="Macro" href="/terminal/market" {...macroFact}
        title="Macro regime from FRED — it gates the momentum sleeve of every signal" />
      <Fact label="Governance" href="/terminal/evidence" {...governanceFact}
        title="Model promotion state. The deterministic engine does not depend on it." />
      {pageFacts?.map((f) => (
        <Fact key={f.label} tone={STATE_TONE[f.state]} label={f.label} value={f.detail ?? f.state} />
      ))}
      <span className="status-build" title="Frontend build">build {build}</span>
    </footer>
  )
}
