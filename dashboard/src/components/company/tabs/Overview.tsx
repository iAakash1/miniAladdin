'use client'

import { Activity, Profile } from '../Activity'
import ChartPanel from '../ChartPanel'
import { Card, Drivers, EvidenceCondition, Pending } from '../Panels'
import Synthesis from '../Synthesis'
import { companyHref } from '@/lib/context-commands'
import type { Analysis } from '@/lib/types'

function pct(v: number | undefined | null, digits = 1): string {
  return v === undefined || v === null || !Number.isFinite(v) ? '—' : `${v.toFixed(digits)}%`
}
function mult(v: number | undefined | null, digits = 1): string {
  return v === undefined || v === null || !Number.isFinite(v) ? '—' : `${v.toFixed(digits)}×`
}

function Fundamentals({ a }: { a: Analysis }) {
  const r = a.ratios
  const rows: Array<[string, string]> = [
    ['P/E (TTM)', mult(r?.pe_ratio ?? a.peRatio)],
    ['Price / sales', mult(r?.price_to_sales)],
    ['EV / EBITDA', mult(r?.ev_to_ebitda)],
    ['Gross margin (TTM)', pct(r?.gross_margin_ttm)],
    ['Operating margin (TTM)', pct(r?.operating_margin_ttm)],
    ['Return on equity (TTM)', pct(r?.roe_ttm)],
    ['Revenue growth (YoY)', pct(r?.revenue_growth_ttm_yoy)],
    ['Debt / equity', mult(r?.debt_to_equity, 2)],
  ]
  return (
    <Card title="Fundamentals" sub={r?.source ? `ratios · ${r.source}` : undefined} more={{ href: companyHref(a.ticker, 'financials'), label: 'Financials' }}>
      <dl className="cw-kv cw-kv--tight">
        {rows.map(([k, v]) => (
          <div key={k}><dt>{k}</dt><dd className="sys-num">{v === '—' ? <span className="sys-null">—</span> : v}</dd></div>
        ))}
      </dl>
    </Card>
  )
}

function Technical({ a }: { a: Analysis }) {
  const t = a.technicalIntelligence
  if (!t) {
    return (
      <Card title="Technical state" more={{ href: companyHref(a.ticker, 'technicals'), label: 'Technicals' }}>
        <p className="cw-muted">Not enough history was returned to read technical structure.</p>
      </Card>
    )
  }
  const regimes = [
    ['Trend', t.regimes.trend], ['Momentum', t.regimes.momentum],
    ['Volatility', t.regimes.volatility], ['Volume', t.regimes.volume],
  ] as const
  return (
    <Card title="Technical state" sub={`${t.bars} sessions · ${t.as_of}`} more={{ href: companyHref(a.ticker, 'technicals'), label: 'Technicals' }}>
      <dl className="cw-kv cw-kv--tight">
        {regimes.map(([k, r]) => (
          <div key={k} title={r.note}>
            <dt>{k}</dt>
            <dd><span className="dot" data-tone={r.tone === 'neutral' ? 'muted' : r.tone} aria-hidden /> {r.label}</dd>
          </div>
        ))}
        <div>
          <dt>Support</dt>
          <dd className="sys-num">{t.levels.support.toFixed(2)} <span className="cw-kv__sub">−{t.levels.support_distance_pct.toFixed(1)}%</span></dd>
        </div>
        <div>
          <dt>Resistance</dt>
          <dd className="sys-num">{t.levels.resistance.toFixed(2)} <span className="cw-kv__sub">+{t.levels.resistance_distance_pct.toFixed(1)}%</span></dd>
        </div>
      </dl>
    </Card>
  )
}

function Macro({ a }: { a: Analysis }) {
  const m = a.macro
  const q = a.quant
  return (
    <Card title="Macro context" sub={m.source ? `${m.source.toUpperCase()}${m.stale ? ' · stale' : ''}` : undefined} more={{ href: companyHref(a.ticker, 'macro'), label: 'Macro' }}>
      <dl className="cw-kv cw-kv--tight">
        <div><dt>Regime</dt><dd>{m.status === 'UNAVAILABLE' ? <span className="sys-null">unavailable</span> : m.status.toLowerCase()}</dd></div>
        <div><dt>Risk multiplier</dt><dd className="sys-num">{m.srm === null ? '—' : m.srm.toFixed(2)}</dd></div>
        <div><dt>10y–2y spread</dt><dd className="sys-num">{m.yieldSpread === null ? '—' : `${m.yieldSpread.toFixed(2)}%`}</dd></div>
        <div><dt>CPI (YoY)</dt><dd className="sys-num">{m.cpi === null ? '—' : `${m.cpi.toFixed(2)}%`}</dd></div>
        <div><dt>Fed funds</dt><dd className="sys-num">{m.fedRate === null ? '—' : `${m.fedRate.toFixed(2)}%`}</dd></div>
        <div><dt>Stress probability</dt><dd className="sys-num">{q?.stressProbability === null || q?.stressProbability === undefined ? '—' : `${(q.stressProbability * 100).toFixed(1)}%`}</dd></div>
      </dl>
    </Card>
  )
}

export default function Overview({ symbol, analysis, isPro, requestUpgrade }: {
  symbol: string
  analysis: Analysis | null
  isPro: boolean
  requestUpgrade: (reason?: 'limit' | 'feature') => void
}) {
  return (
    <div className="cw-overview">
      <div className="cw-grid cw-grid--main">
        <ChartPanel symbol={symbol} isPro={isPro} requestUpgrade={requestUpgrade} />
        {analysis ? <Drivers a={analysis} /> : <Pending title="Signal decomposition" rows={4} />}
      </div>
      <div className="cw-grid cw-grid--main">
        {analysis ? <Synthesis analysis={analysis} /> : <Pending title="Grounded synthesis" rows={4} />}
        {analysis ? <EvidenceCondition a={analysis} /> : <Pending title="Evidence condition" rows={4} />}
      </div>
      <div className="cw-grid cw-grid--3">
        {analysis ? <Fundamentals a={analysis} /> : <Pending title="Fundamentals" />}
        {analysis ? <Technical a={analysis} /> : <Pending title="Technical state" />}
        {analysis ? <Macro a={analysis} /> : <Pending title="Macro context" />}
      </div>
      {analysis ? (
        <div className="cw-grid cw-grid--side">
          <Activity a={analysis} linked={isPro} />
          <Profile profile={analysis.profile} />
        </div>
      ) : null}
    </div>
  )
}
