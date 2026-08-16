import Sparkline from './Sparkline'
import SourceBadge from './SourceBadge'
import Tooltip from './Tooltip'
import type { Tone } from '@/lib/dashboardInsights'

interface CardProps {
  title: string
  value: string
  unit?: string
  previous?: string | null
  change?: string | null
  direction?: 'up' | 'down' | 'flat'
  trend?: number[]
  /** One sentence, "why this matters" — shown behind an info trigger, not
   * inline, so the default card stays scannable (progressive disclosure). */
  explain?: string
  tone?: Tone
  /** Publisher of the series, when the payload names one. */
  source?: string | null
  /** The observation date the value carries — not the fetch time. Macro
   *  series are published on a lag, and a reader deciding whether a CPI
   *  print is current needs the print's own date, not ours. */
  updated?: string | null
}

const CHANGE_COLOR: Record<Tone, string> = {
  pos: 'var(--pos)',
  neg: 'var(--neg)',
  warn: 'var(--warn)',
  neutral: 'var(--faint)',
}

/**
 * Shared metric card: title, current value, mini sparkline, change tag,
 * previous value, and a one-sentence "why this matters" behind an info
 * trigger. Every card in the redesigned dashboard (Economic Conditions,
 * Interest Rates, Inflation) renders through this single component —
 * one shared implementation instead of the three near-duplicate card
 * markups the previous dashboard had.
 */
export default function Card({
  title, value, unit, previous, change, direction = 'flat', trend, explain, tone,
  source, updated,
}: CardProps) {
  const changeTone: Tone = tone ?? (direction === 'up' ? 'pos' : direction === 'down' ? 'neg' : 'neutral')

  return (
    <article className="card dash-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
        <span className="label" style={{ fontSize: '0.625rem', display: 'inline-flex', alignItems: 'center', gap: 3 }}>
          {title}
          {explain && <Tooltip label={`Why ${title} matters`}>{explain}</Tooltip>}
        </span>
        {trend && trend.length > 1 && <Sparkline points={trend} direction={direction} />}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
        <span className="num" style={{ fontSize: '1.25rem', fontWeight: 600 }}>
          {value}
          {unit && <span style={{ fontSize: '0.6875rem', color: 'var(--faint)', fontWeight: 400 }}> {unit}</span>}
        </span>
        {change && (
          <span className="num" style={{ fontSize: '0.6875rem', color: CHANGE_COLOR[changeTone] }}>{change}</span>
        )}
      </div>
      {/* Provenance line. A macro card is a claim about the economy, and
          until now the only thing distinguishing it from a number we made
          up was the reader's trust in the page. The publisher's mark and
          the observation date are both already in the payload. */}
      {(previous || source || updated) && (
        <div className="dash-card__foot">
          {previous && <span className="num">prev {previous}</span>}
          {(source || updated) && (
            <span className="dash-card__prov">
              {source && <SourceBadge name={source} compact />}
              {updated && <span className="num">{updated}</span>}
            </span>
          )}
        </div>
      )}
    </article>
  )
}
