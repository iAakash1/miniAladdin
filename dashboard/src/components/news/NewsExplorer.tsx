'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { NEWS_CATEGORIES } from '@/lib/news/sources'
import type { NewsCategory, NewsResponse } from '@/lib/types'
import { timeAgo } from '@/lib/format'
import NewsCard from './NewsCard'
import Skeleton from '@/components/ui/Skeleton'
import EmptyState from '@/components/ui/EmptyState'

type Status = 'loading' | 'ready' | 'error'
type CategoryFilter = NewsCategory | 'all'

const TABS: Array<{ value: CategoryFilter; label: string }> = [
  { value: 'all', label: 'All' },
  ...NEWS_CATEGORIES,
]

function ListSkeleton() {
  return (
    <div aria-hidden="true">
      <div style={{ paddingBottom: 28, borderBottom: '1px solid var(--line)' }}>
        <Skeleton height={200} style={{ marginBottom: 18 }} />
        <Skeleton height={14} width={140} style={{ marginBottom: 10 }} />
        <Skeleton height={26} width="70%" />
      </div>
      {[0, 1, 2, 3, 4].map((i) => (
        <div
          key={i}
          style={{
            display: 'flex',
            gap: 20,
            padding: '20px 0',
            borderBottom: '1px solid var(--line)',
          }}
        >
          <div style={{ flex: 1 }}>
            <Skeleton height={12} width={120} style={{ marginBottom: 10 }} />
            <Skeleton height={18} width="88%" style={{ marginBottom: 8 }} />
            <Skeleton height={14} width="60%" />
          </div>
          <Skeleton width={104} height={78} />
        </div>
      ))}
    </div>
  )
}

export default function NewsExplorer() {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const category = (searchParams.get('category') ?? 'all') as CategoryFilter
  const page = Math.max(1, parseInt(searchParams.get('page') ?? '1', 10) || 1)
  const urlQuery = searchParams.get('q') ?? ''

  const [inputValue, setInputValue] = useState(urlQuery)
  const [data, setData] = useState<NewsResponse | null>(null)
  const [failed, setFailed] = useState(false)
  const [fetching, setFetching] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const listTopRef = useRef<HTMLDivElement>(null)

  /* Derived: first load shows skeletons; later loads keep the previous
     list on screen and only mark the status line as updating. */
  const status: Status = failed ? 'error' : data === null ? 'loading' : 'ready'

  const setParams = useCallback(
    (next: { category?: CategoryFilter; q?: string; page?: number }) => {
      const params = new URLSearchParams(searchParams.toString())
      if (next.category !== undefined) {
        if (next.category === 'all') params.delete('category')
        else params.set('category', next.category)
      }
      if (next.q !== undefined) {
        if (next.q) params.set('q', next.q)
        else params.delete('q')
      }
      if (next.page !== undefined && next.page > 1) params.set('page', String(next.page))
      else params.delete('page')
      router.replace(`${pathname}${params.size ? `?${params}` : ''}`, { scroll: false })
    },
    [router, pathname, searchParams],
  )

  /* Debounced search → URL */
  const onSearchChange = (value: string) => {
    setInputValue(value)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => setParams({ q: value, page: 1 }), 300)
  }

  /* Fetch on URL state change. State updates happen only in promise
     callbacks / microtasks — never synchronously inside the effect. */
  useEffect(() => {
    let alive = true
    const controller = new AbortController()
    queueMicrotask(() => {
      if (alive) setFetching(true)
    })

    const params = new URLSearchParams()
    if (category !== 'all') params.set('category', category)
    if (urlQuery) params.set('q', urlQuery)
    params.set('page', String(page))
    params.set('pageSize', '20')

    fetch(`/api/news?${params}`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((json: NewsResponse) => {
        if (!alive) return
        setData(json)
        setFailed(false)
      })
      .catch((e: unknown) => {
        if (alive && (e as Error).name !== 'AbortError') setFailed(true)
      })
      .finally(() => {
        if (alive) setFetching(false)
      })

    return () => {
      alive = false
      controller.abort()
    }
  }, [category, urlQuery, page, reloadKey])

  const retry = () => {
    setFailed(false)
    setData(null)
    setReloadKey((k) => k + 1)
  }

  const goToPage = (p: number) => {
    setParams({ page: p })
    listTopRef.current?.scrollIntoView({ block: 'start' })
  }

  const clearFilters = () => {
    setInputValue('')
    setParams({ category: 'all', q: '', page: 1 })
  }

  const hasFilters = category !== 'all' || urlQuery !== ''

  return (
    <div ref={listTopRef} style={{ scrollMarginTop: 76 }}>
      {/* Controls */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 12,
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 8,
        }}
      >
        <div className="seg" role="group" aria-label="Filter by category" style={{ flexWrap: 'wrap' }}>
          {TABS.map((tab) => (
            <button
              key={tab.value}
              type="button"
              className="seg__btn"
              aria-pressed={category === tab.value}
              onClick={() => setParams({ category: tab.value, page: 1 })}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div style={{ position: 'relative', width: 'min(280px, 100%)' }}>
          <label htmlFor="news-search" className="visually-hidden">
            Search news
          </label>
          <input
            id="news-search"
            type="search"
            className="input"
            placeholder="Search headlines…"
            value={inputValue}
            onChange={(e) => onSearchChange(e.target.value)}
            style={{ height: 36, fontSize: '0.875rem' }}
          />
        </div>
      </div>

      {/* Status line */}
      <div
        aria-live="polite"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          gap: 12,
          flexWrap: 'wrap',
          padding: '10px 0 14px',
          borderBottom: '1px solid var(--line-strong)',
          marginBottom: 4,
        }}
      >
        <span style={{ fontSize: '0.8125rem', color: 'var(--muted)' }}>
          {status === 'loading' && 'Loading stories…'}
          {status === 'ready' && data && (
            <>
              {fetching ? 'Updating… · ' : ''}
              {data.total.toLocaleString()} {data.total === 1 ? 'story' : 'stories'}
              {hasFilters && (
                <>
                  {' · '}
                  <button
                    type="button"
                    onClick={clearFilters}
                    style={{
                      background: 'none',
                      border: 'none',
                      padding: 0,
                      color: 'var(--accent)',
                      cursor: 'pointer',
                      fontSize: '0.8125rem',
                      textDecoration: 'underline',
                      textUnderlineOffset: 3,
                    }}
                  >
                    clear filters
                  </button>
                </>
              )}
            </>
          )}
          {status === 'error' && 'Could not load stories.'}
        </span>
        {status === 'ready' && data && (
          <span style={{ fontSize: '0.8125rem', color: 'var(--faint)' }}>
            Updated {timeAgo(data.updatedAt)}
          </span>
        )}
      </div>

      {/* Body */}
      {status === 'loading' && <ListSkeleton />}

      {status === 'error' && (
        <EmptyState
          title="The news feed is unreachable"
          description="Source feeds may be briefly unavailable. This usually resolves in under a minute."
          action={
            <button type="button" className="btn btn--secondary btn--sm" onClick={retry}>
              Try again
            </button>
          }
        />
      )}

      {status === 'ready' && data && data.items.length === 0 && (
        <EmptyState
          title="No stories match"
          description={
            urlQuery
              ? `Nothing in the current feed mentions “${urlQuery}”. Feeds refresh every few minutes.`
              : 'Nothing in this category right now. Feeds refresh every few minutes.'
          }
          action={
            hasFilters ? (
              <button type="button" className="btn btn--secondary btn--sm" onClick={clearFilters}>
                Clear filters
              </button>
            ) : undefined
          }
        />
      )}

      {status === 'ready' && data && data.items.length > 0 && (
        <>
          <div className="fade-in">
            {data.items.map((item, i) => (
              <NewsCard key={item.id} item={item} lead={i === 0 && page === 1} />
            ))}
          </div>

          {/* Pagination */}
          {data.totalPages > 1 && (
            <nav
              aria-label="News pages"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 12,
                padding: '22px 0 4px',
              }}
            >
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                disabled={page <= 1}
                onClick={() => goToPage(page - 1)}
              >
                ← Newer
              </button>
              <span className="num" style={{ fontSize: '0.8125rem', color: 'var(--muted)' }}>
                Page {data.page} of {data.totalPages}
              </span>
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                disabled={page >= data.totalPages}
                onClick={() => goToPage(page + 1)}
              >
                Older →
              </button>
            </nav>
          )}
        </>
      )}
    </div>
  )
}
