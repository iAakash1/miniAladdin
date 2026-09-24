'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { StateBlock } from '@/components/system'
import Thumb from '@/components/visual/Thumb'
import { timeAgo } from '@/lib/format'
import { readResource } from '@/lib/resource'
import type { NewsItem, NewsResponse } from '@/lib/types'

/** Market headlines from the aggregated public feeds, with publisher images. */
export default function MarketNews({ count = 5 }: { count?: number }) {
  const [answer, setAnswer] = useState<{ items?: NewsItem[]; error?: string } | null>(null)

  useEffect(() => {
    let alive = true
    readResource<NewsResponse>(`/api/news?pageSize=${count + 3}`, 'snapshot')
      .then((d) => { if (alive) setAnswer({ items: d.items ?? [] }) })
      .catch((e: Error) => { if (alive) setAnswer({ error: e.message }) })
    return () => { alive = false }
  }, [count])

  const items = (answer?.items ?? []).slice(0, count)
  // Lead with a story that carries its own image, when one does.
  const leadIndex = Math.max(0, items.findIndex((i) => i.image && /^https:/i.test(i.image)))
  const lead = items[leadIndex]
  const rest = items.filter((_, i) => i !== leadIndex).slice(0, 4)

  return (
    <section className="sys-panel home-news" aria-label="Market news">
      <header className="sys-panel-head">
        <div className="sys-panel-head__title">
          <h2 className="sys-panel-title">Market news</h2>
          <span className="sys-panel-sub">aggregated from public financial feeds</span>
        </div>
        <Link className="cw-more" href="/news">All news</Link>
      </header>
      {answer === null ? (
        <StateBlock state="waking" title="Loading market news" />
      ) : answer.error || !lead ? (
        <StateBlock state="unavailable" title="Market news is unavailable" detail="The public feeds did not answer. Company-specific news is still read inside each research run." />
      ) : (
        <div className="home-news__body">
          <a className="home-news__lead" href={lead.url} target="_blank" rel="noreferrer">
            <Thumb src={lead.image} source={lead.source} url={lead.url} width="100%" ratio="16 / 9" />
            <span className="home-news__meta">{lead.source} · {timeAgo(lead.publishedAt)}</span>
            <span className="home-news__title home-news__title--lead">{lead.title}</span>
          </a>
          <ul className="home-news__list">
            {rest.map((n) => (
              <li key={n.id}>
                <a href={n.url} target="_blank" rel="noreferrer" className="home-news__item">
                  <Thumb src={n.image} source={n.source} url={n.url} width={88} ratio="16 / 10" />
                  <span className="home-news__text">
                    <span className="home-news__title">{n.title}</span>
                    <span className="home-news__meta">{n.source} · {timeAgo(n.publishedAt)}</span>
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
