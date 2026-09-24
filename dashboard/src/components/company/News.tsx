'use client'

import EntityMark from '@/components/visual/EntityMark'
import Thumb from '@/components/visual/Thumb'
import { timeAgo } from '@/lib/format'
import { sourceDomain } from '@/lib/identity'
import type { Headline, NewsStream } from '@/lib/types'

/** The engine's own headline tone: a count of bullish and bearish words. A
 *  zero means no keyword matched, which is not the same as neutral. */
function KeywordTone({ h }: { h: Headline }) {
  if (!h.score) return null
  return (
    <span
      className="nw-tone"
      data-tone={h.score > 0 ? 'pos' : 'neg'}
      title="Keyword tone from the engine's news factor — bullish and bearish words counted, not a reading of the article"
    >
      keyword tone {h.score > 0 ? '+' : ''}{h.score.toFixed(2)}
    </span>
  )
}

function Meta({ h }: { h: Headline }) {
  return (
    <span className="nw-meta">
      <EntityMark domain={sourceDomain(h.source, h.url)} label={h.source} size={14} />
      <span className="nw-meta__src">{h.source}</span>
      {h.publishedAt ? <span>{timeAgo(h.publishedAt)}</span> : null}
      {h.author ? <span>by {h.author}</span> : null}
      {h.corroboratedBy.length > 1 ? (
        <span className="nw-corrob" title={`Independently carried by ${h.corroboratedBy.join(', ')}`}>
          carried by {h.corroboratedBy.length} vendors
        </span>
      ) : null}
      {h.sentimentScore !== null && h.sentimentSource ? (
        <span className="nw-vendor" title="Vendor-scored article tone — evidence about tone, not a prediction">
          {h.sentimentLabel ?? h.sentimentScore.toFixed(2)} per {h.sentimentSource}
        </span>
      ) : null}
      <KeywordTone h={h} />
    </span>
  )
}

function Story({ h, lead, linked }: { h: Headline; lead?: boolean; linked: boolean }) {
  const body = (
    <>
      <Thumb src={h.imageUrl} source={h.source} url={h.url} width={lead ? '100%' : 124} ratio={lead ? '16 / 9' : '16 / 10'} />
      <span className="nw-story__text">
        <span className={lead ? 'nw-title nw-title--lead' : 'nw-title'}>{h.title}</span>
        <Meta h={h} />
      </span>
    </>
  )
  const cls = lead ? 'nw-story nw-story--lead' : 'nw-story'
  return linked && h.url ? (
    <a className={cls} href={h.url} target="_blank" rel="noopener noreferrer">{body}</a>
  ) : (
    <div className={cls}>{body}</div>
  )
}

/**
 * Company news from the provider fan-out. Publisher images only — a story
 * without one shows its publisher's mark, never a stock photograph.
 */
export default function News({ headlines, stream, isPro, onUpgrade }: {
  headlines: Headline[]
  stream: NewsStream | null
  isPro: boolean
  onUpgrade: () => void
}) {
  if (!headlines.length) {
    return (
      <section className="sys-panel">
        <div className="sys-state">
          <div className="sys-state__head">
            <span className="sys-status" data-state="unavailable">no stories</span>
            <span className="sys-state__title">No company headlines were returned for this run</span>
          </div>
          <p className="sys-state__detail">The news factor contributes nothing when there are no stories; it is not read as neutral news.</p>
        </div>
      </section>
    )
  }
  const leadIndex = Math.max(0, headlines.findIndex((h) => h.imageUrl && /^https:/i.test(h.imageUrl)))
  const lead = headlines[leadIndex]
  const rest = headlines.filter((_, i) => i !== leadIndex)
  const categories = Object.entries(stream?.categories ?? {}).filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1])

  return (
    <section className="sys-panel nw" aria-label="Company news">
      <header className="sys-panel-head">
        <div className="sys-panel-head__title">
          <h2 className="sys-panel-title">Company news</h2>
          <span className="sys-panel-sub">
            {stream
              ? `${stream.unique} stories from ${stream.providers.join(', ')} · ${stream.corroborated} corroborated`
              : `${headlines.length} stories`}
            {stream?.sentiment ? ` · tone scored on ${stream.sentiment.scored} of ${stream.sentiment.scored + stream.sentiment.unscored} by ${stream.sentiment.source ?? 'one vendor'}` : ''}
          </span>
        </div>
        {!isPro ? (
          <button type="button" className="sys-btn sys-btn--ghost" onClick={onUpgrade}>Open articles with Pro</button>
        ) : null}
      </header>
      {categories.length ? (
        <div className="nw-cats" aria-label="Story categories">
          {categories.map(([label, n]) => (
            <span key={label} className="nw-cat">{label}<b className="sys-num">{n}</b></span>
          ))}
        </div>
      ) : null}
      <div className="nw-body">
        <Story h={lead} lead linked={isPro} />
        <div className="nw-list">
          {rest.map((h, i) => <Story key={`${h.url || h.title}-${i}`} h={h} linked={isPro} />)}
        </div>
      </div>
    </section>
  )
}
