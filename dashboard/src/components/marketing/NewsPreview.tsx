'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { timeAgo } from '@/lib/format'
import type { NewsItem, NewsResponse } from '@/lib/types'
import Skeleton from '@/components/ui/Skeleton'

/** Four latest stories from the live aggregation — typographic rows, no thumbnails. */
export default function NewsPreview() {
  const [items, setItems] = useState<NewsItem[] | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetch('/api/news?pageSize=4')
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((data: NewsResponse) => {
        if (!cancelled) setItems(data.items)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (failed) return null

  return (
    <div>
      {items === null ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }} aria-label="Loading news">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} style={{ padding: '18px 0', borderBottom: i < 3 ? '1px solid var(--line)' : 'none' }}>
              <Skeleton height={14} width={120} style={{ marginBottom: 10 }} />
              <Skeleton height={18} width="85%" />
            </div>
          ))}
        </div>
      ) : (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
          {items.map((item, i) => (
            <li
              key={item.id}
              style={{ borderBottom: i < items.length - 1 ? '1px solid var(--line)' : 'none' }}
            >
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="news-preview-row"
                style={{
                  display: 'block',
                  padding: '18px 0',
                  textDecoration: 'none',
                }}
              >
                <div style={{ display: 'flex', gap: 10, alignItems: 'baseline', marginBottom: 6 }}>
                  <span className="label" style={{ color: 'var(--accent)' }}>
                    {item.source}
                  </span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--faint)' }}>
                    {timeAgo(item.publishedAt)}
                  </span>
                </div>
                <p
                  style={{
                    fontFamily: 'var(--font-serif)',
                    fontSize: '1.1875rem',
                    fontWeight: 500,
                    lineHeight: 1.35,
                    color: 'var(--text)',
                    letterSpacing: '-0.005em',
                  }}
                >
                  {item.title}
                </p>
              </a>
            </li>
          ))}
        </ul>
      )}

      <div style={{ marginTop: 22 }}>
        <Link href="/news" className="btn btn--secondary btn--sm">
          All market news →
        </Link>
      </div>
    </div>
  )
}
