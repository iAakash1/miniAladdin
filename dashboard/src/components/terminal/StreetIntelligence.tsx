'use client'

import MetricExplainer from './MetricExplainer'
import { STREET_GLOSSARY } from '@/lib/technicalGlossary'
import type { StreetIntelligence as StreetBlock, TechTone } from '@/lib/types'

const TONE_COLOR: Record<TechTone, string> = { pos: 'var(--pos)', neg: 'var(--neg)', neutral: 'var(--muted)' }

/**
 * v4.5 P0-B: analyst recommendation trends, EPS-surprise history and insider
 * sentiment — deterministic readings computed server-side (Finnhub free
 * tier via the provider abstraction). Renders and explains; computes nothing.
 */
export default function StreetIntelligence({ block }: { block: StreetBlock | null }) {
  if (!block) return null
  const { recommendations: recs, surprises, insider, findings } = block

  return (
    <section aria-label="Street and insider intelligence" className="panel" style={{ padding: 'clamp(18px, 3vw, 24px)' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: 10, marginBottom: 14 }}>
        <h3 className="h-panel">Street &amp; insiders</h3>
        <span style={{ marginLeft: 'auto', fontSize: '0.6875rem', color: 'var(--faint)' }}>
          Analyst and insider data — not a scoring input
        </span>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'clamp(20px, 4vw, 48px)', marginBottom: 14 }}>
        {recs && (
          <div>
            <span className="label" style={{ fontSize: '0.625rem' }}>Analyst consensus</span>
            <p className="num" style={{ fontSize: '1.0625rem', fontWeight: 600 }}>
              {recs.buy_ratio !== null ? `${Math.round(100 * recs.buy_ratio)}% buy` : '—'}
            </p>
            <p className="num" style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>
              {recs.strong_buy + recs.buy} buy · {recs.hold} hold · {recs.sell + recs.strong_sell} sell
              {' · '}
              <span style={{ color: recs.trend === 'improving' ? 'var(--pos)' : recs.trend === 'deteriorating' ? 'var(--neg)' : 'var(--faint)' }}>
                {recs.trend}
              </span>
            </p>
          </div>
        )}
        {surprises && (
          <div>
            <span className="label" style={{ fontSize: '0.625rem' }}>EPS surprises</span>
            <p className="num" style={{ fontSize: '1.0625rem', fontWeight: 600 }}>
              {surprises.beats}/{surprises.quarters} beats
            </p>
            <p className="num" style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>
              avg {surprises.avg_surprise_pct >= 0 ? '+' : ''}{surprises.avg_surprise_pct}% vs estimates
            </p>
          </div>
        )}
        {insider && (
          <div>
            <span className="label" style={{ fontSize: '0.625rem' }}>Insider sentiment</span>
            <p className="num" style={{
              fontSize: '1.0625rem', fontWeight: 600,
              color: insider.read === 'buying' ? 'var(--pos)' : insider.read === 'selling' ? 'var(--neg)' : 'var(--text)',
            }}>
              {insider.read}
            </p>
            <p className="num" style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>MSPR {insider.mspr >= 0 ? '+' : ''}{insider.mspr} · 6 months</p>
          </div>
        )}
      </div>

      {findings.length > 0 && (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 7 }}>
          {findings.map((finding) => (
            <li key={finding.text} style={{ display: 'flex', gap: 9, fontSize: '0.8125rem', lineHeight: 1.55, color: 'var(--text)' }}>
              <span aria-hidden="true" style={{ flexShrink: 0, marginTop: 7, width: 6, height: 6, borderRadius: 1, background: TONE_COLOR[finding.tone] }} />
              {finding.text}
            </li>
          ))}
        </ul>
      )}

      <details className="disclosure" style={{ marginTop: 14 }}>
        <summary style={{ fontSize: '0.8125rem', fontWeight: 550, color: 'var(--muted)' }}>
          Learn more about these readings
        </summary>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'clamp(20px, 4vw, 44px)', marginTop: 14 }}>
          {Object.values(STREET_GLOSSARY).map((entry) => (
            <div key={entry.label} style={{ maxWidth: 320 }}>
              <MetricExplainer entry={entry} />
            </div>
          ))}
        </div>
      </details>
    </section>
  )
}
