import { Suspense } from 'react'
import type { Metadata } from 'next'
import NewsExplorer from '@/components/news/NewsExplorer'
import Skeleton from '@/components/ui/Skeleton'

export const metadata: Metadata = {
  title: 'Market news',
  description:
    'Live market, economy and company headlines aggregated from Yahoo Finance, MarketWatch and CNBC. Searchable, filterable, updated continuously.',
  alternates: { canonical: '/news' },
}

export default function NewsPage() {
  return (
    <div style={{ padding: 'clamp(40px, 6vw, 72px) 0 clamp(64px, 8vw, 96px)' }}>
      <div className="container" style={{ maxWidth: 880 }}>
        <header style={{ marginBottom: 'clamp(24px, 4vw, 40px)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
            <span className="live-dot" aria-hidden="true" />
            <p className="eyebrow" style={{ color: 'var(--muted)' }}>
              Live feed
            </p>
          </div>
          <h1 className="h-section" style={{ fontSize: 'clamp(2rem, 4vw, 2.75rem)', marginBottom: 12 }}>
            Market news
          </h1>
          <p className="body-copy">
            Aggregated from Yahoo Finance, MarketWatch and CNBC, refreshed every
            few minutes. Every story opens at its original publisher.
          </p>
        </header>

        <Suspense fallback={<Skeleton height={480} />}>
          <NewsExplorer />
        </Suspense>
      </div>
    </div>
  )
}
