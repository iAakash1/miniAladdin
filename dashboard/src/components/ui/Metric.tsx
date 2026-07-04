import type { Tone } from '@/lib/dashboardInsights'

interface MetricProps {
  label: string
  value: string
  unit?: string
  tone?: Tone
  size?: 'lg' | 'md'
  change?: string
}

const TONE_COLOR: Record<Tone, string> = {
  pos: 'var(--pos)',
  neg: 'var(--neg)',
  warn: 'var(--warn)',
  neutral: 'var(--text)',
}

/**
 * Label-over-value primitive for the dashboard hero's Primary Metrics row
 * (large typography, tiny supporting label — the hierarchy the redesign
 * hinges on). Reused wherever a single glanceable number needs to stand
 * out more than a full Card does.
 */
export default function Metric({ label, value, unit, tone = 'neutral', size = 'md', change }: MetricProps) {
  return (
    <div>
      <div className="label" style={{ fontSize: '0.625rem', marginBottom: 4 }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, flexWrap: 'wrap' }}>
        <span
          className="num"
          style={{
            fontSize: size === 'lg' ? 'clamp(1.375rem, 2.6vw, 2rem)' : '1.25rem',
            fontWeight: 650,
            color: TONE_COLOR[tone],
            lineHeight: 1.1,
          }}
        >
          {value}
        </span>
        {unit && <span style={{ fontSize: '0.75rem', color: 'var(--faint)' }}>{unit}</span>}
      </div>
      {change && (
        <div className="num" style={{ fontSize: '0.6875rem', color: 'var(--muted)', marginTop: 3 }}>
          {change}
        </div>
      )}
    </div>
  )
}
