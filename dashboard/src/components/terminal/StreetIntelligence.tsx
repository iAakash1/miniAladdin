'use client'

import { fmtSigned } from '@/lib/format'
import MetricExplainer from './MetricExplainer'
import { STREET_GLOSSARY } from '@/lib/technicalGlossary'
import type { StreetIntelligence as StreetBlock, TechTone } from '@/lib/types'

const TONE_COLOR: Record<TechTone, string> = { pos: 'var(--e-pos)', neg: 'var(--e-neg)', neutral: 'var(--ink-muted)' }

/**
 * v4.5 P0-B: analyst recommendation trends, EPS-surprise history and insider
 * sentiment — deterministic readings computed server-side (Finnhub free
 * tier via the provider abstraction). Renders and explains; computes nothing.
 */
export default function StreetIntelligence({ block }: { block: StreetBlock | null }) {
  if (!block) return null
  const { recommendations: recs, surprises, insider, findings } = block

  return (
    <section aria-label="Street and insider intelligence" className="panel panel--pad">
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: 10, marginBottom: 14 }}>
        <h3 className="h-panel">Street &amp; insiders</h3>
        <span style={{ marginLeft: 'auto', fontSize: 'var(--t-meta)', color: 'var(--ink-faint)' }}>
          Analyst and insider data — not a scoring input
        </span>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'clamp(20px, 4vw, 48px)', marginBottom: 14 }}>
        {recs && (
          <div>
            <span className="sys-label">Analyst consensus</span>
            <p className="num" style={{ fontSize: 'var(--t-lead)', fontWeight: 600 }}>
              {recs.buy_ratio !== null ? `${Math.round(100 * recs.buy_ratio)}% buy` : '—'}
            </p>
 <p className="num u-meta">
              {recs.strong_buy + recs.buy} buy · {recs.hold} hold · {recs.sell + recs.strong_sell} sell
              {' · '}
              <span style={{ color: recs.trend === 'improving' ? 'var(--e-pos)' : recs.trend === 'deteriorating' ? 'var(--e-neg)' : 'var(--ink-faint)' }}>
                {recs.trend}
              </span>
            </p>
          </div>
        )}
        {surprises && (
          <div>
            <span className="sys-label">EPS surprises</span>
            <p className="num" style={{ fontSize: 'var(--t-lead)', fontWeight: 600 }}>
              {surprises.beats}/{surprises.quarters} beats
            </p>
 <p className="num u-meta">
              avg {fmtSigned(surprises.avg_surprise_pct, 2)}% vs estimates
            </p>
          </div>
        )}
        {insider && (
          <div>
            <span className="sys-label">Insider sentiment</span>
            <p className="num" style={{
              fontSize: 'var(--t-lead)', fontWeight: 600,
              color: insider.read === 'buying' ? 'var(--e-pos)' : insider.read === 'selling' ? 'var(--e-neg)' : 'var(--ink)',
            }}>
              {insider.read}
            </p>
 <p className="num u-meta">MSPR {fmtSigned(insider.mspr, 2)} · 6 months</p>
          </div>
        )}
      </div>

      {findings.length > 0 && (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 7 }}>
          {findings.map((finding) => (
            <li key={finding.text} style={{ display: 'flex', gap: 9, fontSize: 'var(--t-body)', lineHeight: 1.55, color: 'var(--ink)' }}>
              <span aria-hidden="true" style={{ flexShrink: 0, marginTop: 7, width: 6, height: 6, borderRadius: 1, background: TONE_COLOR[finding.tone] }} />
              {finding.text}
            </li>
          ))}
        </ul>
      )}

      <details className="disclosure" style={{ marginTop: 14 }}>
        <summary style={{ fontSize: 'var(--t-body)', fontWeight: 600, color: 'var(--ink-muted)' }}>
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
