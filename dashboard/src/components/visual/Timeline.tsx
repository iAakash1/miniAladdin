import Link from 'next/link'
import type { ReactNode } from 'react'

export type TimelineKind = 'filing' | 'news' | 'research' | 'earnings' | 'insider'

export interface TimelineItem {
  id: string
  /** ISO date or timestamp. Items without one are not timeline items. */
  date: string
  kind: TimelineKind
  title: ReactNode
  detail?: ReactNode
  /** A short tag such as a form type: "10-Q", "8-K". */
  tag?: string
  href?: string
  external?: boolean
  tone?: 'pos' | 'neg' | 'warn' | 'info' | 'muted'
  media?: ReactNode
}

const GLYPH: Record<TimelineKind, string> = {
  filing: 'M4.5 2.5h5L12 5v8.5H4.5ZM9.5 2.5V5H12M6.5 8h3.5M6.5 10.5h3.5',
  news: 'M3 3.5h8.5v9H4a1 1 0 0 1-1-1ZM11.5 6h1.5v5.5a1 1 0 0 1-1 1M5 6h4.5M5 8.5h4.5M5 11h2.5',
  research: 'M8 13.5a5.5 5.5 0 1 1 0-11 5.5 5.5 0 0 1 0 11Zm0-3a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z',
  earnings: 'M3.5 12.5v-3M6.5 12.5v-6M9.5 12.5v-4M12.5 12.5v-8M2.5 13.5h11',
  insider: 'M8 7.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM3.5 13.5c.6-2.4 2.3-3.6 4.5-3.6s3.9 1.2 4.5 3.6',
}

const KIND_LABEL: Record<TimelineKind, string> = {
  filing: 'Filing', news: 'News', research: 'Research run', earnings: 'Earnings', insider: 'Insider',
}

function day(iso: string): { key: string; label: string; year: string } {
  const d = new Date(iso.length <= 10 ? `${iso}T00:00:00` : iso)
  if (Number.isNaN(d.getTime())) return { key: iso, label: iso, year: '' }
  return {
    key: d.toISOString().slice(0, 10),
    label: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    year: String(d.getFullYear()),
  }
}

/** Dated events, newest first, grouped by day. */
export default function Timeline({ items, limit, empty }: {
  items: TimelineItem[]
  limit?: number
  empty?: ReactNode
}) {
  const sorted = items
    .filter((i) => i.date && !Number.isNaN(Date.parse(i.date.length <= 10 ? `${i.date}T00:00:00` : i.date)))
    .sort((a, b) => Date.parse(b.date) - Date.parse(a.date))
    .slice(0, limit ?? items.length)
  if (!sorted.length) return <>{empty ?? null}</>

  const groups: Array<{ key: string; label: string; year: string; items: TimelineItem[] }> = []
  for (const item of sorted) {
    const d = day(item.date)
    const last = groups[groups.length - 1]
    if (last && last.key === d.key) last.items.push(item)
    else groups.push({ ...d, items: [item] })
  }
  const thisYear = String(new Date().getFullYear())

  return (
    <ol className="tl">
      {groups.map((g) => (
        <li key={g.key} className="tl-day">
          <div className="tl-date">
            <span className="tl-date__d">{g.label}</span>
            {g.year !== thisYear ? <span className="tl-date__y">{g.year}</span> : null}
          </div>
          <ul className="tl-items">
            {g.items.map((item) => {
              const title = item.href ? (
                item.external
                  ? <a href={item.href} target="_blank" rel="noreferrer">{item.title}</a>
                  : <Link href={item.href}>{item.title}</Link>
              ) : item.title
              return (
                <li key={item.id} className="tl-item" data-kind={item.kind} data-tone={item.tone}>
                  <span className="tl-node" title={KIND_LABEL[item.kind]}>
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                      <path d={GLYPH[item.kind]} />
                    </svg>
                  </span>
                  <div className="tl-body">
                    <div className="tl-title">
                      {item.tag ? <span className="tl-tag">{item.tag}</span> : null}
                      <span className="tl-text">{title}</span>
                    </div>
                    {item.detail ? <div className="tl-detail">{item.detail}</div> : null}
                  </div>
                  {item.media ? <div className="tl-media">{item.media}</div> : null}
                </li>
              )
            })}
          </ul>
        </li>
      ))}
    </ol>
  )
}
