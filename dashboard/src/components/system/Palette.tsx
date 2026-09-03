/**
 * Command palette and universal search.
 *
 * One surface, because the distinction between "go somewhere" and "find
 * something" is an implementation detail the user does not have. Typing a
 * ticker, a model id, an experiment, a measure name or a workspace name all
 * work; commands and objects are ranked together and grouped on output.
 *
 * Every command listed here does something. A palette that offers actions
 * which silently do nothing is worse than a smaller palette, so there is no
 * entry for a capability the product does not have.
 */
'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'

import { loadCatalogue } from '@/lib/research/catalogue'
import { recordVisit, usePinnedObjects, useRecentObjects } from '@/lib/research/history'
import { KIND_ORDER, KINDS, href as objectHref, score, type ObjectKind, type ResearchObject } from '@/lib/research/objects'
import { Status, type ResearchState } from './index'

const STATE_MAP: Record<string, ResearchState> = {
  live: 'live', recorded: 'recorded', stale: 'stale', waking: 'waking',
  unavailable: 'unavailable', blocked: 'blocked', experimental: 'experimental',
  production_candidate: 'candidate', validated: 'candidate',
  production: 'production', retired: 'unavailable',
}

interface Command {
  id: string
  label: string
  hint?: string
  run: () => void
}

const DENSITY_KEY = 'ma.density'

export function applyStoredDensity(): void {
  try {
    const d = window.localStorage.getItem(DENSITY_KEY)
    if (d) document.documentElement.setAttribute('data-density', d)
  } catch {
    /* storage unavailable; the default density applies */
  }
}

function cycleDensity(): void {
  const order = ['compact', 'default', 'comfortable']
  const current = document.documentElement.getAttribute('data-density') ?? 'default'
  const next = order[(order.indexOf(current) + 1) % order.length]
  document.documentElement.setAttribute('data-density', next)
  try { window.localStorage.setItem(DENSITY_KEY, next) } catch { /* ignore */ }
}

export default function Palette() {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  // The cursor is stored with the query it belongs to and derived during
  // render, so a new query resets it without an effect that would paint the
  // stale position for one frame first.
  const [cursorFor, setCursorFor] = useState({ query: '', index: 0 })
  const [objects, setObjects] = useState<ResearchObject[]>([])
  const [failed, setFailed] = useState<{ source: string; reason: string }[]>([])
  const recent = useRecentObjects()
  const pinned = usePinnedObjects()
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      const typing = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)
      if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing)) {
        e.preventDefault()
        setOpen(true)
      }
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    if (!open) return
    const t = setTimeout(() => inputRef.current?.focus(), 0)
    loadCatalogue()
      .then((c) => { setObjects(c.objects); setFailed(c.failed) })
      .catch(() => { /* the catalogue reports its own failures */ })
    return () => clearTimeout(t)
  }, [open])

  const commands: Command[] = useMemo(() => {
    const go = (label: string, path: string, hint: string): Command => ({
      id: `go:${path}`, label, hint, run: () => router.push(path),
    })
    return [
      go('Go to Command', '/terminal/command', 'g c'),
      go('Go to Securities', '/terminal/analyze', 'g s'),
      go('Go to Factors', '/terminal/factorlab', 'g f'),
      go('Go to Signals', '/terminal/signals', 'g g'),
      go('Go to Models', '/terminal/lab', 'g m'),
      go('Go to Evidence', '/terminal/evidence', 'g v'),
      go('Go to Experiments', '/terminal/experiments', 'g x'),
      go('Go to Book', '/terminal/book', 'g b'),
      go('Go to Risk', '/terminal/risk', 'g r'),
      go('Go to Data', '/terminal/data', 'g d'),
      go('Go to Handbook', '/terminal/handbook', 'g y'),
      { id: 'density', label: 'Cycle information density', hint: 'compact / default / comfortable', run: cycleDensity },
    ]
  }, [router])

  const results = useMemo(() => {
    const q = query.trim()
    if (!q) {
      return {
        commands: commands.slice(0, 6),
        grouped: new Map<ObjectKind, ResearchObject[]>(),
      }
    }
    const rankedCommands = commands
      .map((c) => ({ c, s: score(q, c.label) }))
      .filter((r) => r.s > 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, 5)
      .map((r) => r.c)

    const ranked = objects
      .map((o) => ({ o, s: Math.max(score(q, o.label), score(q, o.detail ?? '') * 0.4) }))
      .filter((r) => r.s > 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, 40)

    const grouped = new Map<ObjectKind, ResearchObject[]>()
    for (const { o } of ranked) {
      const list = grouped.get(o.kind) ?? []
      list.push(o)
      grouped.set(o.kind, list)
    }
    return { commands: rankedCommands, grouped }
  }, [query, objects, commands])

  /**
   * One render-ready list: section headers and selectable rows together, with
   * each row carrying the index the cursor uses. Building it here rather than
   * counting during render means the keyboard index and the painted order can
   * never disagree.
   */
  const rows = useMemo(() => {
    type Row =
      | { type: 'header'; key: string; label: string }
      | { type: 'command'; key: string; index: number; value: Command }
      | { type: 'object'; key: string; index: number; value: ResearchObject }
    const out: Row[] = []
    let index = 0

    if (results.commands.length) {
      out.push({ type: 'header', key: 'h:commands', label: 'Commands' })
      for (const c of results.commands) {
        out.push({ type: 'command', key: `c:${c.id}`, index, value: c })
        index += 1
      }
    }

    for (const k of KIND_ORDER) {
      const list = results.grouped.get(k)
      if (!list?.length) continue
      out.push({ type: 'header', key: `h:${k}`, label: KINDS[k].plural })
      for (const o of list) {
        out.push({ type: 'object', key: `o:${o.kind}:${o.id}`, index, value: o })
        index += 1
      }
    }

    if (!query.trim()) {
      if (pinned.length) {
        out.push({ type: 'header', key: 'h:pinned', label: 'Pinned' })
        for (const o of pinned.slice(0, 5)) {
          out.push({ type: 'object', key: `p:${o.kind}:${o.id}`, index, value: o })
          index += 1
        }
      }
      if (recent.length) {
        out.push({ type: 'header', key: 'h:recent', label: 'Recent' })
        for (const o of recent.slice(0, 8)) {
          out.push({ type: 'object', key: `r:${o.kind}:${o.id}`, index, value: o })
          index += 1
        }
      }
    }
    return out
  }, [results, query, pinned, recent])

  const selectable = useMemo(
    () => rows.filter((r): r is Extract<typeof r, { index: number }> => r.type !== 'header'),
    [rows],
  )

  const cursor = cursorFor.query === query ? cursorFor.index : 0
  const setCursor = (next: number | ((c: number) => number)) =>
    setCursorFor((prev) => {
      const base = prev.query === query ? prev.index : 0
      return { query, index: typeof next === 'function' ? next(base) : next }
    })

  if (!open) return null

  const activate = (index: number) => {
    const item = selectable.find((r) => r.index === index)
    if (!item) return
    if (item.type === 'command') {
      item.value.run()
    } else {
      recordVisit(item.value)
      router.push(objectHref(item.value))
    }
    setOpen(false)
    setQuery('')
  }

  return (
    <div
      className="pal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      onMouseDown={(e) => { if (e.target === e.currentTarget) setOpen(false) }}
    >
      <div className="pal">
        <input
          ref={inputRef}
          className="pal-input"
          value={query}
          placeholder="Search objects, or type a workspace name"
          aria-label="Search"
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setCursor((c) => Math.min(c + 1, selectable.length - 1)) }
            if (e.key === 'ArrowUp') { e.preventDefault(); setCursor((c) => Math.max(c - 1, 0)) }
            if (e.key === 'Enter') { e.preventDefault(); activate(cursor) }
          }}
        />

        <div className="pal-body">
          {rows.map((row) => {
            if (row.type === 'header') {
              return <div key={row.key} className="sys-label pal-group-label" style={{ marginTop: 'var(--d-2)' }}>{row.label}</div>
            }
            const active = cursor === row.index
            if (row.type === 'command') {
              return (
                <button
                  key={row.key}
                  className={`pal-row${active ? ' is-active' : ''}`}
                  onMouseEnter={() => setCursor(row.index)}
                  onClick={() => activate(row.index)}
                >
                  <span className="pal-badge" aria-hidden>→</span>
                  <span className="pal-label">{row.value.label}</span>
                  {row.value.hint ? <kbd className="pal-hint">{row.value.hint}</kbd> : null}
                </button>
              )
            }
            const meta = KINDS[row.value.kind]
            const state = row.value.state ? STATE_MAP[row.value.state] : undefined
            return (
              <button
                key={row.key}
                className={`pal-row${active ? ' is-active' : ''}`}
                onMouseEnter={() => setCursor(row.index)}
                onClick={() => activate(row.index)}
              >
                <span className="pal-badge" aria-hidden>{meta.glyph}</span>
                <span className="pal-label">{row.value.label}</span>
                {row.value.detail ? <span className="pal-detail">{row.value.detail}</span> : null}
                {/* State travels with the result. Choosing between a recorded
                    model and a retired one should not need opening both. */}
                {state ? <Status state={state} label={row.value.state} /> : null}
                <span className="pal-hint">{meta.workspace}</span>
              </button>
            )
          })}

          {query.trim() && selectable.length === 0 ? (
            <div className="pal-empty">
              <div className="sys-meta">No object matches “{query}”.</div>
            </div>
          ) : null}

          {failed.length ? (
            <>
              <div className="sys-label pal-group-label" style={{ marginTop: 'var(--d-2)' }}>Not searched</div>
              {failed.map((f) => (
                <div key={f.source} className="pal-row" style={{ cursor: 'default' }}>
                  <span className="pal-badge" aria-hidden>!</span>
                  <span className="pal-label">{f.source}</span>
                  <span className="pal-detail">{f.reason}</span>
                </div>
              ))}
            </>
          ) : null}
        </div>

        <div className="pal-foot">
          <span className="sys-meta">↑↓ move · ⏎ open · esc close</span>
          <span className="sys-meta">{objects.length} objects indexed</span>
        </div>
      </div>
    </div>
  )
}
