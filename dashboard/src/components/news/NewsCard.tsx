'use client'

import { useState } from 'react'
import { timeAgo } from '@/lib/format'
import type { NewsItem } from '@/lib/types'

const CATEGORY_LABEL: Record<string, string> = {
  markets: 'Markets',
  economy: 'Economy',
  companies: 'Companies',
  technology: 'Technology',
  crypto: 'Crypto',
}

interface NewsCardProps {
  item: NewsItem
  /** Lead story: serif display treatment with a larger image */
  lead?: boolean
}

function Thumb({ src, alt, lead }: { src: string; alt: string; lead?: boolean }) {
  const [failed, setFailed] = useState(false)
  if (failed) return null
  return (
    <div
      style={{
        flexShrink: 0,
        width: lead ? '100%' : 104,
        aspectRatio: lead ? '16 / 9' : '4 / 3',
        borderRadius: 'var(--r-md)',
        overflow: 'hidden',
        background: 'var(--surface-2)',
        order: lead ? -1 : 1,
      }}
    >
      {/* News thumbnails come from many third-party CDNs; a plain img with
          lazy loading avoids allow-listing every host. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt={alt}
        loading="lazy"
        decoding="async"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
      />
    </div>
  )
}

export default function NewsCard({ item, lead = false }: NewsCardProps) {
  return (
    <article style={{ borderBottom: '1px solid var(--line)' }}>
      <a
        href={item.url}
        target="_blank"
        rel="noopener noreferrer"
        className="news-preview-row"
        style={{
          display: 'flex',
          flexDirection: lead ? 'column' : 'row',
          gap: lead ? 18 : 20,
          padding: lead ? '0 0 28px' : '20px 0',
          textDecoration: 'none',
        }}
        aria-label={`${item.title} — ${item.source}, opens in a new tab`}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'baseline', marginBottom: 8, flexWrap: 'wrap' }}>
            <span className="label" style={{ color: 'var(--accent)' }}>
              {item.source}
            </span>
            <span className="label" style={{ color: 'var(--faint)', textTransform: 'none', letterSpacing: 0 }}>
              {CATEGORY_LABEL[item.category]}
            </span>
            <span style={{ fontSize: '0.75rem', color: 'var(--faint)' }}>
              <time dateTime={item.publishedAt}>{timeAgo(item.publishedAt)}</time>
            </span>
          </div>

          <h3
            style={{
              fontFamily: 'var(--font-serif)',
              fontSize: lead ? 'clamp(1.5rem, 3vw, 2rem)' : '1.125rem',
              fontWeight: 500,
              lineHeight: lead ? 1.2 : 1.35,
              letterSpacing: '-0.008em',
              color: 'var(--text)',
              marginBottom: item.summary ? 8 : 0,
            }}
          >
            {item.title}
          </h3>

          {item.summary && (
            <p
              style={{
                fontSize: lead ? '0.9688rem' : '0.875rem',
                lineHeight: 1.6,
                color: 'var(--muted)',
                display: '-webkit-box',
                WebkitLineClamp: lead ? 3 : 2,
                WebkitBoxOrient: 'vertical',
                overflow: 'hidden',
              }}
            >
              {item.summary}
            </p>
          )}

          {item.author && (
            <p style={{ fontSize: '0.75rem', color: 'var(--faint)', marginTop: 8 }}>By {item.author}</p>
          )}
        </div>

        {item.image && <Thumb src={item.image} alt="" lead={lead} />}
      </a>
    </article>
  )
}
