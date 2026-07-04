'use client'

import Link from 'next/link'
import { useEffect, useRef, useState } from 'react'
import Skeleton from '@/components/ui/Skeleton'

interface ScreenResult {
  symbol: string
  name: string
  via: string
  snippet: string | null
  url: string | null
}

interface ScreenResponse {
  query: string
  mode: 'lookup' | 'thematic'
  results: ScreenResult[]
  note: string
}

/**
 * Phase 7 search: tickers, company names, or natural language
 * ("AI companies", "largest banks"). Thematic answers are web-grounded
 * and attributed — each row says which source mentioned it.
 */
export default function ScreenSearch() {
  const [value, setValue] = useState('')
  const [query, setQuery] = useState('') // debounced, drives fetch
  const [data, setData] = useState<ScreenResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(false)
  const [open, setOpen] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!query) {
      queueMicrotask(() => {
        setData(null)
        setLoading(false)
      })
      return undefined
    }
    const controller = new AbortController()
    let alive = true
    queueMicrotask(() => {
      if (alive) {
        setLoading(true)
        setFailed(false)
      }
    })
    fetch(`/api/screen?q=${encodeURIComponent(query)}`, { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(String(response.status)))))
      .then((json: ScreenResponse) => {
        if (alive) setData(json)
      })
      .catch((error: unknown) => {
        if (alive && (error as Error).name !== 'AbortError') setFailed(true)
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
      controller.abort()
    }
  }, [query])

  /* Close on outside click / Escape */
  useEffect(() => {
    function onPointer(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false)
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [])

  const onChange = (next: string) => {
    setValue(next)
    setOpen(true)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => setQuery(next.trim()), 350)
  }

  return (
    <div ref={rootRef} style={{ position: 'relative', maxWidth: 520 }}>
      <label htmlFor="screen-q" className="visually-hidden">
        Search tickers, companies or themes
      </label>
      <input
        id="screen-q"
        className="input"
        type="search"
        role="combobox"
        aria-expanded={open && Boolean(data || loading)}
        aria-controls="screen-results"
        autoComplete="off"
        placeholder='Search anything — "NVDA", "largest banks", "AI companies"…'
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onFocus={() => setOpen(true)}
        style={{ height: 42 }}
      />

      {open && (loading || failed || data) && (
        <div
          id="screen-results"
          role="listbox"
          aria-label="Search results"
          className="panel fade-in"
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            left: 0,
            right: 0,
            zIndex: 60,
            maxHeight: 380,
            overflowY: 'auto',
            boxShadow: 'var(--shadow-dialog)',
            padding: '6px',
          }}
        >
          {loading && (
            <div style={{ padding: 10, display: 'flex', flexDirection: 'column', gap: 8 }} aria-label="Searching">
              <Skeleton height={34} />
              <Skeleton height={34} />
              <Skeleton height={34} />
            </div>
          )}
          {failed && !loading && (
            <p style={{ padding: 14, fontSize: '0.8125rem', color: 'var(--muted)' }}>
              Search is unreachable right now — try again shortly.
            </p>
          )}
          {!loading && !failed && data && data.results.length === 0 && (
            <p style={{ padding: 14, fontSize: '0.8125rem', color: 'var(--muted)' }}>
              Nothing found for “{data.query}”. Try a ticker, a company name, or a broader theme.
            </p>
          )}
          {!loading && !failed && data && data.results.length > 0 && (
            <>
              {data.results.map((result) => (
                <Link
                  key={result.symbol}
                  role="option"
                  aria-selected="false"
                  href={`/terminal/analyze?ticker=${result.symbol}`}
                  onClick={() => setOpen(false)}
                  style={{
                    display: 'block',
                    padding: '9px 10px',
                    borderRadius: 'var(--r-md)',
                    textDecoration: 'none',
                  }}
                  className="screen-hit"
                >
                  <span style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
                    <span className="mono" style={{ fontWeight: 600, color: 'var(--text)', width: 62, flexShrink: 0 }}>
                      {result.symbol}
                    </span>
                    <span style={{ fontSize: '0.8125rem', color: 'var(--muted)', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {result.name}
                    </span>
                    <span style={{ fontSize: '0.625rem', color: 'var(--faint)', flexShrink: 0 }}>{result.via}</span>
                  </span>
                  {result.snippet && (
                    <span style={{ display: 'block', fontSize: '0.6875rem', color: 'var(--faint)', marginTop: 3, paddingLeft: 72 }}>
                      {result.snippet}
                    </span>
                  )}
                </Link>
              ))}
              <p style={{ padding: '8px 10px 6px', fontSize: '0.625rem', color: 'var(--faint)', borderTop: '1px solid var(--line)', marginTop: 4 }}>
                {data.note}
              </p>
            </>
          )}
        </div>
      )}
    </div>
  )
}
