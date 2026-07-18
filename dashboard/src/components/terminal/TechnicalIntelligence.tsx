'use client'

import MetricExplainer from './MetricExplainer'
import Tooltip from '@/components/ui/Tooltip'
import { TECHNICAL_GLOSSARY } from '@/lib/technicalGlossary'
import { fmtPrice } from '@/lib/format'
import type { TechnicalIntelligence as TechBlock, TechRegime, TechTone } from '@/lib/types'

const TONE_COLOR: Record<TechTone, string> = {
  pos: 'var(--pos)',
  neg: 'var(--neg)',
  neutral: 'var(--muted)',
}
const TONE_BADGE: Record<TechTone, string> = {
  pos: 'badge--pos',
  neg: 'badge--neg',
  neutral: 'badge--neutral',
}

function RegimeCell({ title, regime }: { title: string; regime: TechRegime }) {
  return (
    <div>
      <p className="label" style={{ fontSize: '0.625rem', marginBottom: 6 }}>{title}</p>
      <span className={`badge ${TONE_BADGE[regime.tone]}`}>{regime.label}</span>
      <p style={{ fontSize: '0.6875rem', color: 'var(--faint)', marginTop: 6, lineHeight: 1.5 }}>
        {regime.note}
      </p>
    </div>
  )
}

/**
 * v4.5 Technical Intelligence: the deterministic technical read computed
 * server-side from the same OHLCV frame the scoring engine consumed. This
 * component renders and explains — it computes nothing. Every indicator
 * carries a quick tooltip and a full Learn More entry (technicalGlossary),
 * so no number appears without its meaning.
 */
export default function TechnicalIntelligence({ block }: { block: TechBlock | null }) {
  if (!block) return null
  const { regimes, indicators, levels, findings } = block

  return (
    <section aria-label="Technical intelligence" className="panel" style={{ padding: 'clamp(18px, 3vw, 24px)' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: 10, marginBottom: 16 }}>
        <h3 className="h-panel">Technical intelligence</h3>
        <span className="num" style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>
          {block.bars} sessions · as of {block.as_of}
        </span>
        <span style={{ marginLeft: 'auto', fontSize: '0.6875rem', color: 'var(--faint)' }}>
          Computed from price history — not a scoring input
        </span>
      </div>

      {/* Regimes: the four-question summary */}
      <div className="terminal-grid-four" style={{ marginBottom: 18 }}>
        <RegimeCell title="Trend" regime={regimes.trend} />
        <RegimeCell title="Momentum" regime={regimes.momentum} />
        <RegimeCell title="Volatility" regime={regimes.volatility} />
        <RegimeCell title="Volume" regime={regimes.volume} />
      </div>

      {/* Findings: deterministic sentences, most load-bearing first */}
      <ul style={{ listStyle: 'none', margin: '0 0 18px', padding: 0, display: 'flex', flexDirection: 'column', gap: 7 }}>
        {findings.map((finding) => (
          <li key={finding.text} style={{ display: 'flex', gap: 9, fontSize: '0.8125rem', lineHeight: 1.55, color: 'var(--text)' }}>
            <span
              aria-hidden="true"
              style={{ flexShrink: 0, marginTop: 7, width: 6, height: 6, borderRadius: 1, background: TONE_COLOR[finding.tone] }}
            />
            {finding.text}
          </li>
        ))}
      </ul>

      {/* Levels */}
      <p className="num" style={{ fontSize: '0.75rem', color: 'var(--muted)', marginBottom: 16 }}>
        Support {fmtPrice(levels.support)} ({levels.support_distance_pct}% below price)
        {' · '}Resistance {fmtPrice(levels.resistance)} ({levels.resistance_distance_pct}% above)
        {' · '}{levels.lookback_days}-day swing window
        <Tooltip label="How support and resistance are computed">
          <p style={{ margin: 0 }}>{TECHNICAL_GLOSSARY.levels.short}</p>
        </Tooltip>
      </p>

      {/* Indicator table */}
      <div style={{ overflowX: 'auto' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Indicator</th>
              <th scope="col">Reading</th>
              <th scope="col">Detail</th>
              <th scope="col">State</th>
            </tr>
          </thead>
          <tbody>
            {indicators.map((row) => {
              const entry = TECHNICAL_GLOSSARY[row.key]
              return (
                <tr key={row.key}>
                  <td style={{ fontWeight: 550, whiteSpace: 'nowrap' }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      {row.label}
                      {entry && (
                        <Tooltip label={`What is ${entry.label}`}>
                          <p style={{ margin: 0 }}>{entry.short}</p>
                        </Tooltip>
                      )}
                    </span>
                  </td>
                  <td className="num">{row.value}</td>
                  <td style={{ color: 'var(--muted)', fontSize: '0.8125rem' }}>{row.detail}</td>
                  <td>
                    <span style={{ fontSize: '0.8125rem', fontWeight: 550, color: TONE_COLOR[row.tone] }}>
                      {row.state}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Learn More: the full education layer, collapsed by default */}
      <details className="disclosure" style={{ marginTop: 16 }}>
        <summary style={{ fontSize: '0.8125rem', fontWeight: 550, color: 'var(--muted)' }}>
          Learn more about these indicators
        </summary>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'clamp(20px, 4vw, 44px)', marginTop: 14 }}>
          {indicators.map((row) => {
            const entry = TECHNICAL_GLOSSARY[row.key]
            if (!entry) return null
            return (
              <div key={row.key} style={{ maxWidth: 320 }}>
                <MetricExplainer entry={entry} value={row.value} valueTone={row.tone} />
              </div>
            )
          })}
          <div style={{ maxWidth: 320 }}>
            <MetricExplainer entry={TECHNICAL_GLOSSARY.levels} />
          </div>
        </div>
      </details>
    </section>
  )
}
