'use client'

import { useState } from 'react'

import SourceBadge from '@/components/ui/SourceBadge'
import { timeAgo } from '@/lib/format'
import type { Headline, NewsStream } from '@/lib/types'

interface HeadlinesProps {
  headlines: Headline[]
  isPro: boolean
  onUpgrade: () => void
  /** Fan-out summary: how many vendors contributed, how many stories were
   *  corroborated, what the event mix was. Absent on payloads from a backend
   *  that predates the multi-vendor news fabric. */
  stream?: NewsStream | null
}

/** A story's photograph, from the publisher that ran it.
 *
 *  Explicitly *not* a stock image: editorial context imagery lives on its own
 *  endpoint and is labelled as context, because presenting a stock library
 *  photograph as an article's own picture is a small, repeated lie. An
 *  article with no image renders without one. */
function ArticleThumb({ src, title }: { src: string; title: string }) {
  const [failed, setFailed] = useState(false)
  if (!src || failed) return null
  return (
    <span className="hl-row__thumb">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt=""
        loading="lazy"
        decoding="async"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
        title={title}
      />
    </span>
  )
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
export default function Headlines({ headlines, isPro, onUpgrade, stream }: HeadlinesProps) {
  if (headlines.length === 0) return null

  const categories = Object.entries(stream?.categories ?? {}).slice(0, 6)

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

      {/* What the fan-out actually did. A single-vendor feed cannot state
          any of this: the collected-vs-unique gap is deduplication, and the
          corroboration count is stories more than one vendor carried
          independently. */}
      {stream && (
        <div className="hl-stream">
          <span className="hl-stream__stat">
            <strong className="num">{stream.unique}</strong> unique
            {stream.collected > stream.unique && (
              <span className="u-note"> of {stream.collected} collected</span>
            )}
          </span>
          <span className="hl-stream__stat">
            <strong className="num">{stream.providers.length}</strong> vendor
            {stream.providers.length === 1 ? '' : 's'}
            <span className="u-note"> · {stream.providers.join(', ')}</span>
          </span>
          {stream.corroborated > 0 && (
            <span className="hl-stream__stat hl-stream__stat--corrob">
              <strong className="num">{stream.corroborated}</strong> corroborated
            </span>
          )}
          {stream.sentiment && (
            <span className="hl-stream__stat" title={`Scored by ${stream.sentiment.source ?? 'a vendor'}`}>
              {stream.sentiment.positive}↑ {stream.sentiment.negative}↓
              <span className="u-note">
                {' '}scored ({stream.sentiment.scored} of {stream.sentiment.scored + stream.sentiment.unscored})
              </span>
            </span>
          )}
        </div>
      )}

      {categories.length > 0 && (
        <div className="hl-cats">
          {categories.map(([label, count]) => (
            <span key={label} className="hl-cat">
              {label}
              <span className="num hl-cat__n">{count}</span>
            </span>
          ))}
        </div>
      )}

      <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
        {headlines.map((h, i) => {
          const inner = (
            <>
              <div className="hl-row__top">
                <p className="hl-row__title">{h.title}</p>
                {h.imageUrl && <ArticleThumb src={h.imageUrl} title={h.source} />}
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
                {/* Independent corroboration, only when there is any. */}
                {h.corroboratedBy.length > 1 && (
                  <span
                    className="hl-corrob"
                    title={`Independently carried by ${h.corroboratedBy.join(', ')}`}
                  >
                    ×{h.corroboratedBy.length} sources
                  </span>
                )}
                {/* Vendor-scored tone, attributed to the vendor rather than
                    presented as the product's own judgement. */}
                {h.sentimentScore !== null && (
                  <span
                    className={`hl-sent hl-sent--${
                      h.sentimentScore > 0.15 ? 'pos' : h.sentimentScore < -0.15 ? 'neg' : 'neutral'
                    }`}
                    title="Vendor-scored article sentiment — evidence about tone, not a prediction"
                  >
                    {h.sentimentLabel ?? h.sentimentScore.toFixed(2)}
                  </span>
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
