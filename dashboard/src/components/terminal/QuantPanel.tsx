'use client'

import { useState } from 'react'
import { FACTOR_LABELS } from '@/lib/history'
import type { Analysis } from '@/lib/types'

const FAMILY_LABEL: Record<string, string> = {
  momentum: 'Momentum',
  fundamental: 'Fundamental',
  news: 'News',
}

function ScorePill({ label, value }: { label: string; value: number | null }) {
  if (value === null) {
    return (
      <div>
        <span className="label" style={{ fontSize: '0.625rem' }}>{label}</span>
        <p style={{ fontSize: '0.8125rem', color: 'var(--faint)' }}>no data</p>
      </div>
    )
  }
  const color = value > 0.05 ? 'var(--pos)' : value < -0.05 ? 'var(--neg)' : 'var(--warn)'
  return (
    <div>
      <span className="label" style={{ fontSize: '0.625rem' }}>{label}</span>
      <p className="num" style={{ fontSize: '1.125rem', fontWeight: 600, color }}>
        {value > 0 ? '+' : ''}{value.toFixed(2)}
      </p>
    </div>
  )
}

/** Symmetric contribution bar: negative left, positive right of a center line. */
function ContributionBar({ value, max }: { value: number; max: number }) {
  const half = 50
  const width = Math.min(half, (Math.abs(value) / max) * half)
  const color = value >= 0 ? 'var(--pos)' : 'var(--neg)'
  return (
    <div style={{ position: 'relative', height: 6, background: 'var(--surface-2)', borderRadius: 3, flex: 1 }}>
      <span style={{ position: 'absolute', left: '50%', top: -2, bottom: -2, width: 1, background: 'var(--line-strong)' }} />
      <span
        style={{
          position: 'absolute',
          top: 0,
          bottom: 0,
          left: value >= 0 ? '50%' : `${half - width}%`,
          width: `${width}%`,
          background: color,
          borderRadius: 3,
        }}
      />
    </div>
  )
}

/**
 * Phase 5: the full audit trail of the v2 scorecard. The contribution rows
 * sum exactly to the composite — "where did this score come from?" is
 * answered mechanically, not rhetorically.
 */
export default function QuantPanel({ analysis }: { analysis: Analysis }) {
  const quant = analysis.quant
  const [showAll, setShowAll] = useState(false)
  if (!quant) return null

  const factors = quant.factors
    .filter((factor) => factor.score !== null)
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
  const visible = showAll ? factors : factors.slice(0, 6)
  const maxContribution = Math.max(0.05, ...factors.map((f) => Math.abs(f.contribution)))
  const gatePct = Math.round((1 - quant.macroGate) * 100)

  return (
    <section aria-label="Score decomposition" className="panel" style={{ padding: 'clamp(18px, 3vw, 24px)' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: 12, marginBottom: 16 }}>
        <h3 className="h-panel">Score decomposition</h3>
        <span className="num" style={{ fontSize: '0.75rem', color: 'var(--faint)' }}>
          {quant.modelVersion} · composite {quant.rawScore > 0 ? '+' : ''}{quant.rawScore.toFixed(3)}
        </span>
        {quant.regimes.map((regime) => (
          <span key={regime} className="badge badge--warn" style={{ height: 19, fontSize: '0.625rem' }}>
            {regime.replace('_', ' ')}
          </span>
        ))}
        <span className="num" style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--muted)' }}>
          risk score {quant.riskScore}/100
        </span>
      </div>

      {/* Family scores + weights */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'clamp(20px, 4vw, 44px)', marginBottom: 18 }}>
        <ScorePill label={`Momentum · w ${quant.weightsUsed.momentum ?? '—'}`} value={quant.momentumScore} />
        <ScorePill label={`Fundamental · w ${quant.weightsUsed.fundamental ?? '—'}`} value={quant.fundamentalScore} />
        <ScorePill label={`News · w ${quant.weightsUsed.news ?? '—'}`} value={quant.newsScore} />
        <div>
          <span className="label" style={{ fontSize: '0.625rem' }}>Macro gate</span>
          <p className="num" style={{ fontSize: '1.125rem', fontWeight: 600, color: gatePct > 0 ? 'var(--warn)' : 'var(--text)' }}>
            ×{quant.macroGate.toFixed(2)}
          </p>
          {gatePct > 0 && (
            <p style={{ fontSize: '0.625rem', color: 'var(--faint)' }}>−{gatePct}% off bullish score</p>
          )}
        </div>
        <div>
          <span className="label" style={{ fontSize: '0.625rem' }}>Conflict</span>
          <p className="num" style={{ fontSize: '1.125rem', fontWeight: 600, color: quant.conflictIndex > 0.15 ? 'var(--warn)' : 'var(--text)' }}>
            {quant.conflictIndex.toFixed(2)}
          </p>
        </div>
        <div>
          <span className="label" style={{ fontSize: '0.625rem' }}>Uncertainty</span>
          <p className="num" style={{ fontSize: '1.125rem', fontWeight: 600 }}>
            {(quant.uncertainty * 100).toFixed(0)}%
          </p>
          <p style={{ fontSize: '0.625rem', color: 'var(--faint)' }}>
            disp {(quant.uncertaintyComponents.dispersion ?? 0).toFixed(2)} ·
            data {(quant.uncertaintyComponents.data ?? 0).toFixed(2)} ·
            event {(quant.uncertaintyComponents.event ?? 0).toFixed(2)}
          </p>
        </div>
      </div>

      {/* Factor contributions */}
      <p className="label" style={{ fontSize: '0.625rem', marginBottom: 10 }}>
        Factor contributions (sum = composite before gate)
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {visible.map((factor) => (
          <div key={factor.name} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ width: 172, fontSize: '0.75rem', color: 'var(--muted)', flexShrink: 0 }}>
              {FACTOR_LABELS[factor.name] ?? factor.name}
              {factor.z !== null && (
                <span className="num" style={{ color: 'var(--faint)' }}> z {factor.z.toFixed(1)}</span>
              )}
            </span>
            <ContributionBar value={factor.contribution} max={maxContribution} />
            <span
              className="num"
              style={{
                width: 58,
                textAlign: 'right',
                fontSize: '0.75rem',
                color: factor.contribution >= 0 ? 'var(--pos)' : 'var(--neg)',
                flexShrink: 0,
              }}
            >
              {factor.contribution >= 0 ? '+' : ''}{factor.contribution.toFixed(3)}
            </span>
          </div>
        ))}
      </div>
      {factors.length > 6 && (
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          style={{ marginTop: 10, height: 24, fontSize: '0.6875rem' }}
          aria-expanded={showAll}
          onClick={() => setShowAll((value) => !value)}
        >
          {showAll ? 'Show top 6' : `Show all ${factors.length} factors`}
        </button>
      )}

      {/* Confidence + risk decomposition */}
      <div className="hairline-top" style={{ display: 'flex', flexWrap: 'wrap', gap: '14px 44px', marginTop: 16, paddingTop: 14 }}>
        <div>
          <p className="label" style={{ fontSize: '0.625rem', marginBottom: 6 }}>Confidence composition</p>
          <p className="num" style={{ fontSize: '0.75rem', color: 'var(--muted)', lineHeight: 1.7 }}>
            {quant.confidenceLosses.length === 0
              ? `No deductions — ${quant.confidence}%`
              : `100 ${quant.confidenceLosses.map((loss) => `− ${loss.points} (${loss.component.toLowerCase()})`).join(' ')} = ${quant.confidence}%`}
          </p>
        </div>
        <div>
          <p className="label" style={{ fontSize: '0.625rem', marginBottom: 6 }}>Risk composition</p>
          <p className="num" style={{ fontSize: '0.75rem', color: 'var(--muted)', lineHeight: 1.7 }}>
            vol {quant.riskComponents.volatility ?? '—'} · drawdown {quant.riskComponents.drawdown ?? '—'} ·
            beta {quant.riskComponents.beta ?? '—'} · srm {quant.riskComponents.srm ?? '—'}
          </p>
        </div>
        <div>
          <p className="label" style={{ fontSize: '0.625rem', marginBottom: 6 }}>Data completeness</p>
          <p className="num" style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>
            {(quant.dataCompleteness * 100).toFixed(0)}% of factors computable
          </p>
        </div>
      </div>
    </section>
  )
}
