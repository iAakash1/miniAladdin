'use client'

import SourceBadge from '@/components/ui/SourceBadge'
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

/**
 * Scored headlines — the evidence behind a sentiment reading.
 *
 * The metadata line now leads with the publisher's own mark rather than its
 * name in the same grey as the timestamp. A reader deciding how much weight
 * to give a headline is asking "who says?" first, and a favicon answers that
 * before the sentence is read; the raw vendor string stays as the label,
 * cleaned of the banner decoration RSS aggregators prepend.
 *
 * Row styling moved out of inline objects into `.hl-row` so hover, focus and
 * the leading accent are defined once — and so a Pro row (a link) and a
 * locked row (a div) can share exactly one treatment instead of two copies
 * of the same six properties.
 */
export default function Headlines({ headlines, isPro, onUpgrade }: HeadlinesProps) {
  if (headlines.length === 0) return null

  return (
    <section aria-label="Scored headlines" className="panel panel--pad">
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
              <div className="hl-row__top">
                <p className="hl-row__title">{h.title}</p>
                {isPro && h.url && (
                  <span aria-hidden="true" className="hl-row__out">↗</span>
                )}
              </div>
              <div className="hl-row__meta">
                <SourceBadge name={h.source} url={h.url} />
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
                {h.publishedAt && (
                  <span className="u-meta">{timeAgo(h.publishedAt)}</span>
                )}
              </div>
            </>
          )

          return (
            <li
              key={`${h.title}-${i}`}
              style={{ borderBottom: i < headlines.length - 1 ? '1px solid var(--line)' : 'none' }}
            >
              {isPro && h.url ? (
                <a href={h.url} target="_blank" rel="noopener noreferrer" className="hl-row">
                  {inner}
                </a>
              ) : (
                <div className="hl-row">{inner}</div>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
