'use client'

import type { Analysis, RiskLevel } from '@/lib/types'

const RISK_BADGE: Record<RiskLevel, string> = {
  LOW: 'badge--pos',
  MEDIUM: 'badge--warn',
  HIGH: 'badge--neg',
}

function FactorList({ title, items, tone }: { title: string; items: string[]; tone: 'pos' | 'neg' }) {
  if (items.length === 0) return null
  return (
    <div style={{ flex: '1 1 240px', minWidth: 0 }}>
      <p className="label" style={{ marginBottom: 8 }}>
        {title}
      </p>
      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 7 }}>
        {items.map((item) => (
          <li key={item} style={{ display: 'flex', gap: 9, fontSize: '0.8125rem', lineHeight: 1.55, color: 'var(--muted)' }}>
            <span
              aria-hidden="true"
              style={{
                flexShrink: 0,
                marginTop: 7,
                width: 6,
                height: 6,
                borderRadius: 1,
                background: tone === 'pos' ? 'var(--pos)' : 'var(--neg)',
              }}
            />
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
}

function ReasoningRow({ label, text }: { label: string; text: string }) {
  if (!text) return null
  return (
    <div style={{ padding: '10px 0', borderBottom: '1px solid var(--line)' }}>
      <p className="label" style={{ marginBottom: 5 }}>
        {label}
      </p>
      <p style={{ fontSize: '0.8125rem', lineHeight: 1.6, color: 'var(--muted)' }}>{text}</p>
    </div>
  )
}

/**
 * AI explanation panel. Recommendation, confidence and risk are the engine's
 * deterministic values (attached server-side); the model contributes only the
 * narrative. Falls back to the engine's own rationale with a clear badge when
 * the LLM is unavailable.
 */
export default function AiPanel({ analysis }: { analysis: Analysis }) {
  const ai = analysis.ai
  if (!ai) return null

  const hasReasoning =
    ai.technicalReasoning || ai.macroReasoning || ai.newsReasoning || ai.riskReasoning

  return (
    <section aria-label="AI analysis" className="panel" style={{ padding: 'clamp(18px, 3vw, 24px)' }}>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: 10,
          marginBottom: 14,
        }}
      >
        <h3 className="h-panel">Executive summary</h3>
        {ai.generated ? (
          <span className="badge badge--accent" title={ai.model ?? undefined}>
            AI-generated
          </span>
        ) : (
          <span className="badge badge--neutral">Engine rationale — AI offline</span>
        )}

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 14 }}>
          <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 6 }}>
            <span className="label" style={{ fontSize: '0.625rem' }}>
              Confidence
            </span>
            <span className="num" style={{ fontSize: '0.875rem', fontWeight: 600 }}>
              {ai.confidence}%
            </span>
          </span>
          <span className={`badge ${RISK_BADGE[ai.risk]}`}>{ai.risk.toLowerCase()} risk</span>
        </div>
      </div>

      <p
        style={{
          fontSize: '0.9375rem',
          lineHeight: 1.7,
          color: 'var(--text)',
          maxWidth: '72ch',
        }}
      >
        {ai.executiveSummary}
      </p>

      {ai.confidenceReason && (
        <p style={{ fontSize: '0.8125rem', lineHeight: 1.6, color: 'var(--muted)', marginTop: 10, maxWidth: '72ch' }}>
          <span style={{ fontWeight: 560, color: 'var(--text)' }}>Why {ai.confidence}%: </span>
          {ai.confidenceReason}
        </p>
      )}

      {(ai.keyCatalysts.length > 0 || ai.keyRisks.length > 0) && (
        <div
          className="hairline-top"
          style={{ display: 'flex', flexWrap: 'wrap', gap: '18px 40px', paddingTop: 16, marginTop: 16 }}
        >
          <FactorList title="Key catalysts" items={ai.keyCatalysts} tone="pos" />
          <FactorList title="Key risks" items={ai.keyRisks} tone="neg" />
        </div>
      )}

      {hasReasoning && (
        <details style={{ marginTop: 16 }}>
          <summary
            style={{
              cursor: 'pointer',
              fontSize: '0.8125rem',
              fontWeight: 550,
              color: 'var(--muted)',
              userSelect: 'none',
            }}
          >
            Detailed reasoning
          </summary>
          <div style={{ marginTop: 4 }}>
            <ReasoningRow label="Technicals" text={ai.technicalReasoning} />
            <ReasoningRow label="Macro" text={ai.macroReasoning} />
            <ReasoningRow label="News" text={ai.newsReasoning} />
            <ReasoningRow label="Risk" text={ai.riskReasoning} />
          </div>
        </details>
      )}

      {(ai.investmentHorizon || ai.marketOutlook) && (
        <dl style={{ margin: '14px 0 0' }}>
          {ai.investmentHorizon && (
            <div className="metric-row">
              <dt>Suggested horizon</dt>
              <dd style={{ fontFamily: 'var(--font-sans)', fontWeight: 480, textAlign: 'right', maxWidth: '60%' }}>
                {ai.investmentHorizon}
              </dd>
            </div>
          )}
          {ai.marketOutlook && (
            <div className="metric-row">
              <dt>Macro outlook</dt>
              <dd style={{ fontFamily: 'var(--font-sans)', fontWeight: 480, textAlign: 'right', maxWidth: '60%' }}>
                {ai.marketOutlook}
              </dd>
            </div>
          )}
        </dl>
      )}
    </section>
  )
}
