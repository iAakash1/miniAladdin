'use client'

import type { Analysis } from '@/lib/types'

export default function SentimentPanel({ analysis: a }: { analysis: Analysis }) {
  const score = a.sentimentScore

  return (
    <section aria-label="News sentiment" className="panel" style={{ padding: '20px 22px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 }}>
        <h3 className="h-panel">News sentiment</h3>
        {a.headlineCount > 0 && (
          <span style={{ fontSize: '0.75rem', color: 'var(--faint)' }}>
            {a.headlineCount} {a.headlineCount === 1 ? 'article' : 'articles'}
          </span>
        )}
      </div>

      {score === null ? (
        <p style={{ fontSize: '0.875rem', color: 'var(--muted)', lineHeight: 1.6 }}>
          Skipped in quick scan. Run a full analysis to score the tape.
        </p>
      ) : (
        <>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 16 }}>
            <span
              className="num"
              style={{
                fontSize: '1.75rem',
                fontWeight: 600,
                lineHeight: 1,
                color: score > 0.1 ? 'var(--pos)' : score < -0.1 ? 'var(--neg)' : 'var(--warn)',
              }}
            >
              {score > 0 ? '+' : ''}
              {score.toFixed(2)}
            </span>
            <span
              className={`badge ${
                score > 0.1 ? 'badge--pos' : score < -0.1 ? 'badge--neg' : 'badge--warn'
              }`}
            >
              {a.sentimentLabel ?? 'Neutral'}
            </span>
          </div>

          {/* Diverging scale −1 … +1 */}
          <div
            role="img"
            aria-label={`Average sentiment ${score.toFixed(2)} on a scale from minus one, bearish, to plus one, bullish`}
            style={{ position: 'relative', height: 4, background: 'var(--surface-2)', borderRadius: 2 }}
          >
            <span
              style={{
                position: 'absolute',
                left: '50%',
                top: -3,
                bottom: -3,
                width: 1,
                background: 'var(--line-strong)',
              }}
            />
            <span
              style={{
                position: 'absolute',
                top: 0,
                bottom: 0,
                left: score >= 0 ? '50%' : `${50 + score * 50}%`,
                width: `${Math.min(50, Math.abs(score) * 50)}%`,
                background: score > 0.1 ? 'var(--pos)' : score < -0.1 ? 'var(--neg)' : 'var(--warn)',
                borderRadius: 2,
              }}
            />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
            <span className="num" style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>
              −1 bearish
            </span>
            <span className="num" style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>
              +1 bullish
            </span>
          </div>
        </>
      )}
    </section>
  )
}
