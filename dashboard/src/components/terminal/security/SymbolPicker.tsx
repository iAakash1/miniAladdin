/**
 * Symbol entry for the security workspace.
 *
 * Suggestions come from the book's own holdings and from what has been visited,
 * not from a static list. A picker offering names the product has no data for
 * would produce an empty workspace and read as a broken page rather than as an
 * absent security.
 */
'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'

import { Panel, StateBlock } from '@/components/system'
import { useRecentObjects } from '@/lib/research/history'

export default function SymbolPicker({ current }: { current?: string }) {
  const router = useRouter()
  const recent = useRecentObjects()
  const [entry, setEntry] = useState(current ?? '')
  const [book, setBook] = useState<string[]>([])

  useEffect(() => {
    let alive = true
    fetch('/api/quant/portfolio')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: { weights?: { symbol: string }[] }) => {
        if (alive) setBook((d.weights ?? []).map((w) => w.symbol))
      })
      .catch(() => { /* the book is a convenience here, not a requirement */ })
    return () => { alive = false }
  }, [])

  const suggestions = useMemo(() => {
    const seen = new Set<string>()
    const out: string[] = []
    for (const o of recent) {
      if (o.kind !== 'security' || seen.has(o.id)) continue
      seen.add(o.id)
      out.push(o.id)
    }
    for (const s of book) {
      if (seen.has(s)) continue
      seen.add(s)
      out.push(s)
    }
    return out.slice(0, 18)
  }, [recent, book])

  const open = (symbol: string) => {
    const clean = symbol.trim().toUpperCase()
    if (clean) router.push(`/terminal/security?symbol=${encodeURIComponent(clean)}`)
  }

  return (
    <Panel
      title="Security"
      subtitle={current || undefined}
      actions={
        <form onSubmit={(e) => { e.preventDefault(); open(entry) }} style={{ display: 'flex', gap: 'var(--d-1)' }}>
          <input
            className="sys-input"
            value={entry}
            onChange={(e) => setEntry(e.target.value)}
            placeholder="ticker"
            aria-label="Security symbol"
            style={{ width: 110, textTransform: 'uppercase' }}
          />
          <button className="sys-btn" type="submit">open</button>
        </form>
      }
    >
      {suggestions.length ? (
        <>
          <div className="sys-label" style={{ marginBottom: 'var(--d-2)' }}>
            {recent.some((o) => o.kind === 'security') ? 'Recent and in the book' : 'In the book'}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--d-1)' }}>
            {suggestions.map((s) => (
              <button
                key={s}
                className="sys-btn"
                aria-pressed={s === current}
                onClick={() => open(s)}
                style={{ fontFamily: 'var(--font-mono)', letterSpacing: 0 }}
              >
                {s}
              </button>
            ))}
          </div>
          <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-micro)', color: 'var(--ink-faint)', lineHeight: 'var(--lh-body)' }}>
            Suggestions are names the product holds data for — the current book
            and what has been opened. Any ticker can be typed; one with no data
            will say so rather than render an empty workspace.
          </p>
        </>
      ) : current ? null : (
        <StateBlock
          state="unknown"
          title="No security selected"
          detail="Type a ticker above, or open one from the book, the screen or search."
        />
      )}
    </Panel>
  )
}
