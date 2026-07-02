'use client'

import { fmtNum, fmtPrice } from '@/lib/format'
import type { Analysis } from '@/lib/types'

/** 52-week range with current price + analyst target markers. */
function RangeBar({ low, high, price, target }: { low: number; high: number; price: number; target: number | null }) {
  const span = high - low
  if (span <= 0) return null
  const pos = Math.min(100, Math.max(0, ((price - low) / span) * 100))
  const targetPos = target != null ? Math.min(100, Math.max(0, ((target - low) / span) * 100)) : null

  return (
    <div style={{ margin: '14px 0 4px' }}>
      <div
        style={{ position: 'relative', height: 4, background: 'var(--surface-2)', borderRadius: 2 }}
        role="img"
        aria-label={`52-week range ${fmtPrice(low)} to ${fmtPrice(high)}; current ${fmtPrice(price)}${
          target != null ? `; analyst target ${fmtPrice(target)}` : ''
        }`}
      >
        {targetPos !== null && (
          <span
            title={`Analyst target ${fmtPrice(target)}`}
            style={{
              position: 'absolute',
              left: `${targetPos}%`,
              top: -3,
              width: 2,
              height: 10,
              background: 'var(--accent)',
              transform: 'translateX(-1px)',
            }}
          />
        )}
        <span
          style={{
            position: 'absolute',
            left: `${pos}%`,
            top: -2,
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: 'var(--text)',
            transform: 'translateX(-4px)',
            border: '2px solid var(--surface)',
            boxSizing: 'content-box',
          }}
        />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
        <span className="num" style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>
          {fmtPrice(low)}
        </span>
        <span className="label" style={{ fontSize: '0.625rem' }}>
          52-week range
        </span>
        <span className="num" style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>
          {fmtPrice(high)}
        </span>
      </div>
    </div>
  )
}

export default function Fundamentals({ analysis: a }: { analysis: Analysis }) {
  const upside =
    a.analystTarget != null && a.price > 0 ? ((a.analystTarget - a.price) / a.price) * 100 : null

  return (
    <section aria-label="Fundamentals" className="panel" style={{ padding: '20px 22px' }}>
      <h3 className="h-panel" style={{ marginBottom: 10 }}>
        Fundamentals
      </h3>
      <dl style={{ margin: 0 }}>
        <div className="metric-row">
          <dt>P/E, trailing</dt>
          <dd>{fmtNum(a.peRatio)}</dd>
        </div>
        <div className="metric-row">
          <dt>P/E, forward</dt>
          <dd>{fmtNum(a.forwardPe)}</dd>
        </div>
        <div className="metric-row">
          <dt>EPS</dt>
          <dd>{a.eps != null ? fmtPrice(a.eps) : '—'}</dd>
        </div>
        <div className="metric-row">
          <dt>Beta</dt>
          <dd style={{ color: a.beta != null && a.beta > 1.5 ? 'var(--warn)' : undefined }}>
            {fmtNum(a.beta)}
          </dd>
        </div>
        <div className="metric-row">
          <dt>Street target</dt>
          <dd>
            {a.analystTarget != null ? (
              <>
                {fmtPrice(a.analystTarget)}{' '}
                {upside != null && (
                  <span style={{ color: upside >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                    ({upside >= 0 ? '+' : ''}
                    {upside.toFixed(1)}%)
                  </span>
                )}
              </>
            ) : (
              '—'
            )}
          </dd>
        </div>
      </dl>

      {a.week52Low != null && a.week52High != null && (
        <RangeBar low={a.week52Low} high={a.week52High} price={a.price} target={a.analystTarget} />
      )}
    </section>
  )
}
