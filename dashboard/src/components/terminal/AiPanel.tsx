'use client'

import type { Analysis, RiskLevel } from '@/lib/types'

const RISK_BADGE: Record<RiskLevel, string> = {
  LOW: 'badge--pos',
  MEDIUM: 'badge--warn',
  HIGH: 'badge--neg',
}

const DOT_COLOR = { pos: 'var(--pos)', neg: 'var(--neg)', neutral: 'var(--warn)' } as const

function formatSigned(value: number, digits = 3): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}`
}

function FactorList({
  title,
  items,
  tone,
}: {
  title: string
  items: string[]
  tone: 'pos' | 'neg' | 'neutral'
}) {
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
                background: DOT_COLOR[tone],
              }}
            />
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
}

function CaseColumn({ title, text, tone }: { title: string; text: string; tone: 'pos' | 'neg' }) {
  if (!text) return null
  return (
    <div style={{ flex: '1 1 260px', minWidth: 0 }}>
      <p
        className="label"
        style={{ marginBottom: 6, color: tone === 'pos' ? 'var(--pos)' : 'var(--neg)' }}
      >
        {title}
      </p>
      <p style={{ fontSize: '0.8125rem', lineHeight: 1.6, color: 'var(--text)' }}>{text}</p>
    </div>
  )
}

/** One row of the Factor attribution appendix: a deterministic subtotal
 *  (the engine's own arithmetic) beside the model's plain-English read of it. */
function ImpactRow({
  label,
  valueText,
  tone,
  narrative,
}: {
  label: string
  valueText: string
  tone: 'pos' | 'neg' | 'neutral'
  narrative: string
}) {
  if (!narrative) return null
  return (
    <div style={{ display: 'flex', gap: 14, padding: '9px 0', borderBottom: '1px solid var(--line)', alignItems: 'baseline' }}>
      <span style={{ width: 108, flexShrink: 0, fontSize: '0.75rem', fontWeight: 550, color: 'var(--text)' }}>
        {label}
      </span>
      <span
        className="num"
        style={{ width: 64, flexShrink: 0, fontSize: '0.8125rem', fontWeight: 600, color: DOT_COLOR[tone] }}
      >
        {valueText}
      </span>
      <span style={{ fontSize: '0.8125rem', lineHeight: 1.55, color: 'var(--muted)' }}>{narrative}</span>
    </div>
  )
}

function impactTone(value: number): 'pos' | 'neg' | 'neutral' {
  return value > 0.005 ? 'pos' : value < -0.005 ? 'neg' : 'neutral'
}

/**
 * Full research-report explanation layer. Recommendation, confidence, risk
 * and every factor-impact subtotal are the engine's deterministic values
 * (attached server-side, see src/services/llm_service.py); the model
 * contributes only the narrative around them. Falls back to the engine's
 * own rationale with a clear badge when the LLM is unavailable.
 *
 * Layout follows a research-report shape on purpose: verdict rationale →
 * executive summary → thesis → confidence/risk reasoning → bull/bear case →
 * catalysts/risks/watch-list are always visible (the "front page"); the
 * factor-by-factor attribution is collapsed behind a details/summary so a
 * quick read doesn't turn into a wall of text — expand it for the full
 * momentum/quality/value/PEAD/macro/news breakdown.
 */
export default function AiPanel({ analysis }: { analysis: Analysis }) {
  const ai = analysis.ai
  if (!ai) return null

  const impacts = ai.factorImpacts
  const hasAttribution =
    ai.topPositiveNarrative ||
    ai.topNegativeNarrative ||
    ai.momentumImpact ||
    ai.qualityImpact ||
    ai.valueImpact ||
    ai.peadImpact ||
    ai.macroReasoning ||
    ai.newsReasoning

  return (
    <section aria-label="Research report" className="panel" style={{ padding: 'clamp(18px, 3vw, 24px)' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10, marginBottom: 14 }}>
        <h3 className="h-panel">Research report</h3>
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

      {ai.verdictRationale && (
        <p
          style={{
            fontSize: '0.8125rem',
            fontWeight: 550,
            color: 'var(--text)',
            marginBottom: 12,
            padding: '10px 12px',
            background: 'var(--surface-2)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--r-md)',
          }}
        >
          Why {ai.recommendation}: {ai.verdictRationale}
        </p>
      )}

      <p style={{ fontSize: '0.9375rem', lineHeight: 1.7, color: 'var(--text)', maxWidth: '72ch' }}>
        {ai.executiveSummary}
      </p>

      {ai.investmentThesis && (
        <p
          style={{
            fontSize: '0.875rem',
            lineHeight: 1.65,
            color: 'var(--text)',
            maxWidth: '72ch',
            marginTop: 10,
            paddingLeft: 12,
            borderLeft: '2px solid var(--accent)',
          }}
        >
          {ai.investmentThesis}
        </p>
      )}

      {(ai.confidenceReason || ai.riskReasoning) && (
        <div className="hairline-top" style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 40px', paddingTop: 14, marginTop: 14 }}>
          {ai.confidenceReason && (
            <p style={{ fontSize: '0.8125rem', lineHeight: 1.6, color: 'var(--muted)', maxWidth: '36ch', flex: '1 1 320px' }}>
              <span style={{ fontWeight: 560, color: 'var(--text)' }}>Why {ai.confidence}%: </span>
              {ai.confidenceReason}
            </p>
          )}
          {ai.riskReasoning && (
            <p style={{ fontSize: '0.8125rem', lineHeight: 1.6, color: 'var(--muted)', maxWidth: '36ch', flex: '1 1 320px' }}>
              <span style={{ fontWeight: 560, color: 'var(--text)' }}>Why {ai.risk.toLowerCase()} risk: </span>
              {ai.riskReasoning}
            </p>
          )}
        </div>
      )}

      {(ai.bullCase || ai.bearCase) && (
        <div
          className="hairline-top"
          style={{ display: 'flex', flexWrap: 'wrap', gap: '14px 40px', paddingTop: 16, marginTop: 16 }}
        >
          <CaseColumn title="Bull case" text={ai.bullCase} tone="pos" />
          <CaseColumn title="Bear case" text={ai.bearCase} tone="neg" />
        </div>
      )}

      {(ai.keyCatalysts.length > 0 || ai.keyRisks.length > 0 || ai.thingsToWatch.length > 0) && (
        <div
          className="hairline-top"
          style={{ display: 'flex', flexWrap: 'wrap', gap: '18px 40px', paddingTop: 16, marginTop: 16 }}
        >
          <FactorList title="Key catalysts" items={ai.keyCatalysts} tone="pos" />
          <FactorList title="Key risks" items={ai.keyRisks} tone="neg" />
          <FactorList title="Things to watch" items={ai.thingsToWatch} tone="neutral" />
        </div>
      )}

      {hasAttribution && (
        <details className="disclosure" style={{ marginTop: 16 }}>
          <summary style={{ fontSize: '0.8125rem', fontWeight: 550, color: 'var(--muted)' }}>
            Factor attribution
          </summary>
          <div style={{ marginTop: 10 }}>
            {(ai.topPositiveNarrative || ai.topNegativeNarrative) && (
              <p style={{ fontSize: '0.8125rem', lineHeight: 1.6, color: 'var(--muted)', marginBottom: 10 }}>
                {ai.topPositiveNarrative}
                {ai.topPositiveNarrative && ai.topNegativeNarrative ? ' ' : ''}
                {ai.topNegativeNarrative}
              </p>
            )}
            <ImpactRow
              label="Momentum"
              valueText={formatSigned(impacts.momentum.contribution)}
              tone={impactTone(impacts.momentum.contribution)}
              narrative={ai.momentumImpact}
            />
            <ImpactRow
              label="Quality"
              valueText={formatSigned(impacts.quality.contribution)}
              tone={impactTone(impacts.quality.contribution)}
              narrative={ai.qualityImpact}
            />
            <ImpactRow
              label="Value"
              valueText={formatSigned(impacts.value.contribution)}
              tone={impactTone(impacts.value.contribution)}
              narrative={ai.valueImpact}
            />
            <ImpactRow
              label="Post-earnings drift"
              valueText={formatSigned(impacts.pead.contribution)}
              tone={impactTone(impacts.pead.contribution)}
              narrative={ai.peadImpact}
            />
            <ImpactRow
              label="Macro"
              valueText={`SRM ${analysis.macro.srm.toFixed(2)}`}
              tone={analysis.macro.srm > 1.15 ? 'neg' : analysis.macro.srm < 0.9 ? 'pos' : 'neutral'}
              narrative={ai.macroReasoning}
            />
            <ImpactRow
              label="News"
              valueText={formatSigned(impacts.news.contribution)}
              tone={impactTone(impacts.news.contribution)}
              narrative={ai.newsReasoning}
            />
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

      {ai.conclusion && (
        <p
          className="hairline-top"
          style={{
            fontSize: '0.875rem',
            lineHeight: 1.65,
            color: 'var(--text)',
            fontWeight: 480,
            maxWidth: '72ch',
            paddingTop: 16,
            marginTop: 16,
          }}
        >
          {ai.conclusion}
        </p>
      )}
    </section>
  )
}
