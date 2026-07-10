'use client'

import type { ReactNode } from 'react'
import Tooltip from '@/components/ui/Tooltip'
import type { MetricEntry } from '@/lib/metricGlossary'

const TONE_COLOR = { pos: 'var(--pos)', neg: 'var(--neg)', neutral: 'var(--text)' } as const

function ExplainRow({ label, text, tone }: { label: string; text: string; tone?: 'pos' | 'neg' }) {
  if (!text) return null
  return (
    <div>
      <p className="label" style={{ fontSize: '0.625rem', marginBottom: 3, color: tone ? TONE_COLOR[tone] : undefined }}>
        {label}
      </p>
      <p style={{ fontSize: '0.75rem', lineHeight: 1.55, color: 'var(--muted)' }}>{text}</p>
    </div>
  )
}

/**
 * One metric on the Validation page: live value (server-computed, never
 * calculated here) + a quick-glance Tooltip + a full "Explain" disclosure
 * covering definition, formula, interpretation, good/bad, typical range,
 * why OmniSignal uses it, and references. The glossary content itself
 * (dashboard/src/lib/metricGlossary.ts) is static, authored, standard
 * finance/statistics reference material — not computed and not
 * ticker-specific.
 */
export default function MetricExplainer({
  entry,
  value,
  valueTone = 'neutral',
}: {
  entry: MetricEntry
  /** Omit (or pass undefined/"") for metrics that are a whole visualization
   *  rather than a single headline number — e.g. confusion matrix, calibration. */
  value?: ReactNode
  valueTone?: 'pos' | 'neg' | 'neutral'
}) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <span className="label" style={{ fontSize: '0.625rem' }}>
          {entry.label}
        </span>
        <Tooltip label={`What is ${entry.label}`}>
          <p style={{ margin: 0 }}>{entry.short}</p>
          <p style={{ margin: '6px 0 0', color: 'var(--faint)', fontSize: '0.6875rem' }}>Good: {entry.good}</p>
        </Tooltip>
      </div>
      {value !== undefined && value !== '' && (
        <p className="num" style={{ fontSize: '1.0625rem', fontWeight: 600, color: TONE_COLOR[valueTone] }}>
          {value}
        </p>
      )}
      <details>
        <summary style={{ cursor: 'pointer', fontSize: '0.6875rem', fontWeight: 550, color: 'var(--faint)', userSelect: 'none' }}>
          Explain
        </summary>
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8, maxWidth: '58ch' }}>
          {entry.formula && <ExplainRow label="Formula" text={entry.formula} />}
          <ExplainRow label="Interpretation" text={entry.interpretation} />
          <ExplainRow label="Good" text={entry.good} tone="pos" />
          <ExplainRow label="Bad" text={entry.bad} tone="neg" />
          <ExplainRow label="Typical range" text={entry.typicalRange} />
          {entry.limitations && <ExplainRow label="Limitations" text={entry.limitations} />}
          {entry.entersScore && <ExplainRow label="Where it enters the score" text={entry.entersScore} />}
          <ExplainRow label="Why OmniSignal uses it" text={entry.why} />
          <ExplainRow label="References" text={entry.references.join(' · ')} />
        </div>
      </details>
    </div>
  )
}
