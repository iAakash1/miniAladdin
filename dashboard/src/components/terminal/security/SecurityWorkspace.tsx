/**
 * Security research workspace.
 *
 * Sections rather than a scroll of cards, because the questions a researcher
 * asks about a name are separable: what it is, how it has moved, what risk it
 * carries, what this system predicts about it, and where all of that came from.
 *
 * The prediction section is the one that needs care. The research book is not
 * armed, so a prediction is a research output and never an instruction. The
 * deployment status travels with it on every render, and where no model is
 * promoted the section says so rather than showing a number with a quiet
 * caveat somewhere below.
 */
'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'

import { Sparkline, TimeSeries } from '@/components/system/charts'
import { Panel, Section, StateBlock, Status, Strip, Value, type ResearchState } from '@/components/system'
import { recordVisit } from '@/lib/research/history'
import Disclosure, { type FilingsBlock, type Headline } from './Disclosure'
import Fundamentals from './Fundamentals'

interface SymbolView {
  symbol: string
  deployment_status: string
  message?: string
  prediction: number | null
  model: string | null
  disclosure?: string
}

interface PricePoint { date: string; close: number; volume: number }

interface Analysis {
  ticker?: string
  companyName?: string
  sector?: string | null
  marketCap?: string | null
  price?: number
  return5d?: number
  return21d?: number
  volatility?: number
  sharpe?: number
  sortino?: number
  maxDrawdown?: number
  rsi?: number
  beta?: number | null
  peRatio?: number | null
  forwardPe?: number | null
  eps?: number | null
  week52High?: number | null
  week52Low?: number | null
  analystTarget?: number | null
  sentimentScore?: number | null
  sentimentLabel?: string | null
  headlineCount?: number
  headlines?: Headline[]
  filings?: FilingsBlock | null
  ratios?: Record<string, number | undefined> | null
  technicalIntelligence?: Record<string, unknown> | null
  streetIntelligence?: Record<string, unknown> | null
  mode?: string
}

type Tab = 'overview' | 'market' | 'fundamentals' | 'risk' | 'research' | 'disclosure' | 'relationships' | 'data'

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'market', label: 'Market' },
  { id: 'fundamentals', label: 'Fundamentals' },
  { id: 'risk', label: 'Risk' },
  { id: 'research', label: 'Research' },
  { id: 'disclosure', label: 'Disclosure' },
  { id: 'relationships', label: 'Relationships' },
  { id: 'data', label: 'Data' },
]

const n = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

function deploymentState(status: string): ResearchState {
  if (status === 'SERVING') return 'production'
  if (status === 'NO_MODEL') return 'unavailable'
  return 'unknown'
}

export default function SecurityWorkspace({ symbol }: { symbol: string }) {
  const [view, setView] = useState<SymbolView | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [prices, setPrices] = useState<PricePoint[] | null>(null)
  const [failures, setFailures] = useState<string[]>([])
  const [tab, setTab] = useState<Tab>('overview')

  useEffect(() => {
    recordVisit({ kind: 'security', id: symbol, label: symbol })
  }, [symbol])

  useEffect(() => {
    let alive = true
    const fail = (what: string) => (e: Error) => { if (alive) setFailures((p) => [...p, `${what}: ${e.message}`]) }
    const get = (url: string) => fetch(url).then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))

    get(`/api/quant/symbol/${encodeURIComponent(symbol)}`).then((d) => alive && setView(d)).catch(fail('prediction'))
    get(`/api/research/${encodeURIComponent(symbol)}`).then((d) => alive && setAnalysis(d)).catch(fail('research'))
    get(`/api/chart/${encodeURIComponent(symbol)}?period=1y`)
      .then((d) => { if (alive) setPrices(Array.isArray(d?.points) ? d.points : Array.isArray(d) ? d : null) })
      .catch(fail('prices'))
    return () => { alive = false }
  }, [symbol])

  const closes = useMemo(() => (prices ?? []).map((p) => p.close), [prices])

  const identity = (
    <Panel title="Identity" state="recorded">
      <table className="sys-table sys-table--compact">
        <tbody>
          <tr><td>Ticker</td><td className="num" style={{ fontFamily: 'var(--font-mono)' }}>{symbol}</td></tr>
          <tr><td>Name</td><td className="num" style={{ textAlign: 'left' }}>{analysis?.companyName ?? '—'}</td></tr>
          <tr><td>Sector</td><td className="num" style={{ textAlign: 'left' }}>{analysis?.sector ?? '—'}</td></tr>
          <tr><td>Market cap</td><td className="num" style={{ textAlign: 'left' }}>{analysis?.marketCap ?? '—'}</td></tr>
        </tbody>
      </table>
      <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-micro)', color: 'var(--ink-faint)', lineHeight: 'var(--lh-body)' }}>
        A ticker is not a permanent identity. It can be reassigned after a
        delisting, so a ticker-keyed history is only as trustworthy as the
        dataset&apos;s survivorship classification.
      </p>
    </Panel>
  )

  return (
    <>
      <Strip metrics={[
        { label: 'Price', value: n(analysis?.price), digits: 2 },
        { label: '5d return', value: n(analysis?.return5d), digits: 4, signed: true, tone: true },
        { label: '21d return', value: n(analysis?.return21d), digits: 4, signed: true, tone: true },
        { label: 'Volatility', value: n(analysis?.volatility), digits: 4, unit: 'ann.' },
        { label: 'Sharpe', value: n(analysis?.sharpe), digits: 3, signed: true, tone: true },
        { label: 'Max drawdown', value: n(analysis?.maxDrawdown), digits: 4, tone: true },
        { label: 'Beta', value: n(analysis?.beta), digits: 3 },
      ]} />

      <div className="sys-seg" role="tablist" aria-label="Security views">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className="sys-btn" onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'overview' ? (
        <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}>
          {identity}
          <Panel title="Trailing year" subtitle={prices ? `${prices.length} sessions` : undefined}>
            {prices?.length ? (
              <TimeSeries
                series={[{ name: 'close', points: prices.map((p) => ({ x: p.date, y: p.close })), color: 'var(--ink)' }]}
                unit="close, unadjusted unless the source says otherwise"
                height={170}
              />
            ) : <StateBlock state={failures.some((f) => f.startsWith('prices')) ? 'unavailable' : 'waking'} title="No price series" />}
          </Panel>
          <Panel title="Valuation">
            <table className="sys-table sys-table--compact">
              <tbody>
                <tr><td>P/E</td><td className="num"><Value value={n(analysis?.peRatio)} digits={2} /></td></tr>
                <tr><td>Forward P/E</td><td className="num"><Value value={n(analysis?.forwardPe)} digits={2} /></td></tr>
                <tr><td>EPS</td><td className="num"><Value value={n(analysis?.eps)} digits={2} /></td></tr>
                <tr><td>52w high</td><td className="num"><Value value={n(analysis?.week52High)} digits={2} /></td></tr>
                <tr><td>52w low</td><td className="num"><Value value={n(analysis?.week52Low)} digits={2} /></td></tr>
                <tr><td>Analyst target</td><td className="num"><Value value={n(analysis?.analystTarget)} digits={2} /></td></tr>
              </tbody>
            </table>
            <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-micro)', color: 'var(--ink-faint)', lineHeight: 'var(--lh-body)' }}>
              These are current vendor values, not point-in-time. They describe the
              company today and cannot be used to reconstruct what was known on a
              past date.
            </p>
          </Panel>
        </div>
      ) : null}

      {tab === 'market' ? (
        <>
          <Panel title="Price" subtitle={prices ? `${prices.length} sessions` : undefined}>
            {prices?.length ? (
              <TimeSeries
                series={[{ name: 'close', points: prices.map((p) => ({ x: p.date, y: p.close })), color: 'var(--ink)' }]}
                unit="close"
                height={260}
              />
            ) : <StateBlock state="unavailable" title="No price series" />}
          </Panel>
          <Panel title="Volume">
            {prices?.length ? (
              <TimeSeries
                series={[{ name: 'volume', points: prices.map((p) => ({ x: p.date, y: p.volume })), color: 'var(--ink-muted)' }]}
                unit="shares"
                height={150}
              />
            ) : <StateBlock state="unavailable" title="No volume series" />}
          </Panel>
        </>
      ) : null}

      {tab === 'fundamentals' ? (
        <Fundamentals
          ratios={analysis?.ratios}
          technicals={analysis?.technicalIntelligence as never}
          street={analysis?.streetIntelligence as never}
        />
      ) : null}

      {tab === 'risk' ? (
        <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}>
          <Panel title="Dispersion and drawdown">
            <table className="sys-table sys-table--compact">
              <tbody>
                <tr><td>Volatility</td><td className="num"><Value value={n(analysis?.volatility)} digits={4} unit="ann." /></td></tr>
                <tr><td>Sharpe</td><td className="num"><Value value={n(analysis?.sharpe)} digits={4} signed tone /></td></tr>
                <tr><td>Sortino</td><td className="num"><Value value={n(analysis?.sortino)} digits={4} signed tone /></td></tr>
                <tr><td>Max drawdown</td><td className="num"><Value value={n(analysis?.maxDrawdown)} digits={4} tone /></td></tr>
                <tr><td>Beta</td><td className="num"><Value value={n(analysis?.beta)} digits={4} /></td></tr>
              </tbody>
            </table>
            <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-micro)', color: 'var(--ink-faint)', lineHeight: 'var(--lh-body)' }}>
              Single-name figures over the trailing window the research pipeline
              used. The portfolio-level measures in Risk are computed on the book,
              not summed from these.
            </p>
          </Panel>
          <Panel title="Price path">
            {closes.length ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--d-2)' }}>
                <Sparkline values={closes} width={280} height={54} />
                <span className="sys-meta">trailing close, {closes.length} sessions</span>
              </div>
            ) : <StateBlock state="unavailable" title="No series" />}
          </Panel>
        </div>
      ) : null}

      {tab === 'research' ? (
        <Panel
          title="Model output"
          subtitle={view?.model ?? undefined}
          state={view ? deploymentState(view.deployment_status) : 'waking'}
        >
          {!view ? (
            <StateBlock state="waking" title="Reading the model view" />
          ) : view.prediction === null ? (
            <StateBlock
              state="unavailable"
              title="No prediction is served for this name"
              detail={view.message ?? 'No model is promoted, so the product does not serve a prediction. Nothing is shown in its place.'}
            />
          ) : (
            <>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--d-3)', marginBottom: 'var(--d-3)' }}>
                <span className="sys-title"><Value value={view.prediction} digits={6} signed /></span>
                <Status state={deploymentState(view.deployment_status)} label={view.deployment_status} />
              </div>
              <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)', maxWidth: '84ch' }}>
                {view.disclosure ?? view.message}
              </p>
            </>
          )}
          <p style={{ margin: 'var(--d-3) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-faint)', lineHeight: 'var(--lh-body)', maxWidth: '84ch' }}>
            A prediction here is a research output in rank units, not an
            instruction and not a return. The deployment status is shown beside it
            on every render rather than as a caveat further down the page.
          </p>
          <div style={{ display: 'flex', gap: 'var(--d-2)', marginTop: 'var(--d-3)', flexWrap: 'wrap' }}>
            <Link href={`/terminal/calibration?symbol=${encodeURIComponent(symbol)}`} className="sys-btn" style={{ textDecoration: 'none' }}>
              Is the score calibrated?
            </Link>
            <Link href={`/terminal/relationships?symbol=${encodeURIComponent(symbol)}`} className="sys-btn" style={{ textDecoration: 'none' }}>
              What does it connect to?
            </Link>
            <Link href="/terminal/evidence" className="sys-btn" style={{ textDecoration: 'none' }}>
              Can the model be trusted?
            </Link>
          </div>
        </Panel>
      ) : null}

      {tab === 'disclosure' ? (
        <Disclosure filings={analysis?.filings} headlines={analysis?.headlines} symbol={symbol} />
      ) : null}

      {tab === 'relationships' ? (
        <Panel title="Relationships" subtitle="typed, with provider and confidence">
          <p style={{ margin: '0 0 var(--d-3)', fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)', maxWidth: '84ch' }}>
            Every relationship this company has is a provider assertion carrying a
            confidence and a validity window, not a measurement. The graph is
            traversable — each neighbour opens its own connections.
          </p>
          <Link href={`/terminal/relationships?symbol=${encodeURIComponent(symbol)}`} className="sys-btn" style={{ textDecoration: 'none' }}>
            Open the relationship graph for {symbol}
          </Link>
        </Panel>
      ) : null}

      {tab === 'data' ? (
        <>
          <Panel title="Source" state={analysis ? 'live' : 'unavailable'}>
            <table className="sys-table sys-table--compact">
              <tbody>
                <tr><td>Pipeline mode</td><td className="num">{analysis?.mode ?? '—'}</td></tr>
                <tr><td>Headlines</td><td className="num"><Value value={n(analysis?.headlineCount)} digits={0} /></td></tr>
                <tr><td>Sentiment</td><td className="num">{analysis?.sentimentLabel ?? '—'}</td></tr>
                <tr><td>Price points</td><td className="num"><Value value={prices?.length ?? null} digits={0} /></td></tr>
              </tbody>
            </table>
          </Panel>
          <Panel title="What is and is not point-in-time">
            <Section title="Point-in-time">
              <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
                The price and corporate-action history behind the research
                pipeline. Its classification is published in the Data workspace.
              </p>
            </Section>
            <Section title="Not point-in-time">
              <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
                Valuation ratios, analyst targets and sentiment on this page are
                current vendor values. They describe today and cannot reconstruct
                what was known on a past date, which is why no factor is built
                from them.
              </p>
            </Section>
          </Panel>
        </>
      ) : null}

      {failures.length ? (
        <Panel title="Unavailable" state="unavailable">
          <ul style={{ margin: 0, paddingLeft: 'var(--d-4)', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)' }}>
            {failures.map((f) => <li key={f}>{f}</li>)}
          </ul>
          <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-micro)', color: 'var(--ink-faint)' }}>
            Sections that depend on these render their unavailable state rather than a substitute value.
          </p>
        </Panel>
      ) : null}
    </>
  )
}
