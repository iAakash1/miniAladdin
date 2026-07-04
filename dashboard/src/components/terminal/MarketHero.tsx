'use client'

import { useMemo } from 'react'
import Metric from '@/components/ui/Metric'
import {
  type DashboardData,
  heroSummary,
  marketTrend,
  quickSignals,
  regimeLabel,
  signalConfidence,
} from '@/lib/dashboardInsights'
import { fmtNum, fmtPctRaw } from '@/lib/format'

const BADGE_TONE: Record<string, string> = { pos: 'badge--pos', neg: 'badge--neg', warn: 'badge--warn', neutral: 'badge--neutral' }

/**
 * The dashboard's single entry point: "what is happening in the market
 * right now?" Regime, a deterministic three-sentence summary, six primary
 * metrics in large type, and five quick-glance signal badges — everything
 * else on the page is progressive disclosure below this.
 */
export default function MarketHero({ data }: { data: DashboardData }) {
  const { regime, signals, confidence, summary, trend, vix, fed, cpi } = useMemo(() => {
    const regime = regimeLabel(data.macro.regime)
    const signals = quickSignals(data)
    return {
      regime,
      signals,
      confidence: signalConfidence(signals),
      summary: heroSummary(data),
      trend: marketTrend(data.breadth.indexes),
      vix: data.breadth.indexes.find((index) => index.symbol === 'VIX'),
      fed: data.macro.cards.find((c) => c.id === 'FEDFUNDS'),
      cpi: data.macro.cards.find((c) => c.id === 'CPIAUCSL'),
    }
  }, [data])

  return (
    <section aria-labelledby="hero-h" className="card dash-hero">
      <h2 id="hero-h" className="visually-hidden">Market overview</h2>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 14 }}>
        <span className={`badge ${BADGE_TONE[regime.tone]}`} style={{ fontSize: '0.75rem', height: 26, padding: '0 12px' }}>
          {regime.label.toUpperCase()}
        </span>
        {data.macro.regime.recession_warning && (
          <span className="badge badge--neg">Recession watch</span>
        )}
      </div>

      {summary && (
        <p style={{ fontSize: '0.9375rem', color: 'var(--muted)', lineHeight: 1.65, maxWidth: '68ch', marginBottom: 22 }}>
          {summary}
        </p>
      )}

      <div className="dash-hero__metrics">
        <Metric
          label="SRM"
          value={fmtNum(data.macro.regime.risk_multiplier ?? null, 2)}
          size="lg"
          tone={regime.tone}
        />
        <Metric
          label="VIX"
          value={vix ? fmtNum(vix.price, 1) : '—'}
          size="lg"
          change={vix?.change_1d != null ? `${vix.change_1d > 0 ? '+' : ''}${vix.change_1d}% 1d` : undefined}
          tone={vix?.change_1d != null ? (vix.change_1d > 0 ? 'warn' : 'pos') : 'neutral'}
        />
        <Metric label="Fed" value={fed ? fmtPctRaw(fed.value) : '—'} size="lg" />
        <Metric
          label="Inflation"
          value={cpi ? fmtPctRaw(cpi.value) : '—'}
          size="lg"
          tone={cpi ? (cpi.direction === 'down' ? 'pos' : cpi.direction === 'up' ? 'warn' : 'neutral') : 'neutral'}
        />
        <Metric
          label="Trend"
          value={trend.label}
          size="lg"
          change={trend.changePct != null ? `${trend.changePct > 0 ? '+' : ''}${trend.changePct}% 1w` : undefined}
          tone={trend.label === 'Up' ? 'pos' : trend.label === 'Down' ? 'neg' : 'neutral'}
        />
        <Metric
          label="Confidence"
          value={`${confidence}%`}
          size="lg"
          tone={confidence >= 70 ? 'pos' : confidence <= 40 ? 'neg' : 'warn'}
        />
      </div>

      {signals.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 20 }} aria-label="Quick signals">
          {signals.map((signal) => (
            <span
              key={signal.id}
              className={`badge ${BADGE_TONE[signal.tone]}`}
              title={signal.explain}
            >
              {signal.label} · {signal.value}
            </span>
          ))}
        </div>
      )}
    </section>
  )
}
