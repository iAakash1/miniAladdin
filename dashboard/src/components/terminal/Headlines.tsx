'use client'

import { timeAgo } from '@/lib/format'
import type { Headline } from '@/lib/types'

interface HeadlinesProps {
  headlines: Headline[]
  isPro: boolean
  onUpgrade: () => void
}

const LABEL_TONE: Record<Headline['label'], string> = {
  Bullish: 'badge--pos',
  Bearish: 'badge--neg',
  Neutral: 'badge--warn',
}

export default function Headlines({ headlines, isPro, onUpgrade }: HeadlinesProps) {
  if (headlines.length === 0) return null

  return (
    <section aria-label="Scored headlines" className="panel" style={{ padding: '20px 22px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
        <h3 className="h-panel">What moved the score</h3>
        {!isPro && (
          <button
            type="button"
            onClick={onUpgrade}
            style={{
              background: 'none',
              border: 'none',
              padding: 0,
              cursor: 'pointer',
              fontSize: '0.75rem',
              color: 'var(--accent)',
              textDecoration: 'underline',
              textUnderlineOffset: 3,
            }}
          >
            Article links are Pro
          </button>
        )}
      </div>

      <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
        {headlines.map((h, i) => {
          const inner = (
            <>
              <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                <p
                  style={{
                    flex: 1,
                    fontSize: '0.875rem',
                    lineHeight: 1.5,
                    color: 'var(--text)',
                    fontWeight: 480,
                  }}
                >
                  {h.title}
                </p>
                {isPro && h.url && (
                  <span aria-hidden="true" style={{ color: 'var(--faint)', fontSize: '0.8125rem', flexShrink: 0 }}>
                    ↗
                  </span>
                )}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 7, flexWrap: 'wrap' }}>
                <span className={`badge ${LABEL_TONE[h.label]}`} style={{ height: 19, fontSize: '0.625rem' }}>
                  {h.label}
                </span>
                {h.score !== 0 && (
                  <span
                    className="num"
                    style={{
                      fontSize: '0.6875rem',
                      color: h.score > 0 ? 'var(--pos)' : h.score < 0 ? 'var(--neg)' : 'var(--faint)',
                    }}
                  >
                    {h.score > 0 ? '+' : ''}
                    {h.score.toFixed(2)}
                  </span>
                )}
                <span style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>{h.source}</span>
                {h.publishedAt && (
                  <span style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>{timeAgo(h.publishedAt)}</span>
                )}
              </div>
            </>
          )

          const rowStyle: React.CSSProperties = {
            display: 'block',
            padding: '13px 0',
            borderBottom: i < headlines.length - 1 ? '1px solid var(--line)' : 'none',
            textDecoration: 'none',
          }

          return (
            <li key={`${h.title}-${i}`}>
              {isPro && h.url ? (
                <a href={h.url} target="_blank" rel="noopener noreferrer" style={rowStyle}>
                  {inner}
                </a>
              ) : (
                <div style={rowStyle}>{inner}</div>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
