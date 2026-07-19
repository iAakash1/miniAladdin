'use client'

import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useRef, useState } from 'react'

import { TYPE_LABELS, groupByType, type Entity } from '@/lib/intelligence/entities'
import { registerDefaultProviders } from '@/lib/intelligence/providers'
import { queryIntelligence, readRecents, recordRecent } from '@/lib/intelligence/registry'

/**
 * ⌘K — the first client of the Intelligence OS. Pure consumer: all
 * matching, ranking and provider composition live in lib/intelligence;
 * this component renders results and handles keys. Instant (sync tier on
 * every keystroke, async merge when it settles), keyboard-first, calm.
 */
export default function CommandPalette() {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Entity[]>([])
  const [settled, setSettled] = useState(true)
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  /* Global shortcut: Cmd/Ctrl+K toggles, from any terminal surface. */
  useEffect(() => {
    registerDefaultProviders()
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setOpen((value) => !value)
      }
    }
    // The header affordance opens the same surface as the shortcut, so
    // there is exactly one search experience in the product.
    const onRequest = () => setOpen(true)
    document.addEventListener('keydown', onKey)
    window.addEventListener('omni-open-palette', onRequest)
    return () => {
      document.removeEventListener('keydown', onKey)
      window.removeEventListener('omni-open-palette', onRequest)
    }
  }, [])

  /* Query the registry on every keystroke; empty query shows recents. */
  useEffect(() => {
    if (!open) return
    if (!query.trim()) {
      setResults(readRecents())
      setSettled(true)
      setActive(0)
      return
    }
    queryIntelligence(query, readRecents().map((e) => e.id), ({ scored, settled: done }) => {
      setResults(scored.map((s) => s.entity))
      setSettled(done)
      setActive((index) => Math.min(index, Math.max(0, scored.length - 1)))
    })
  }, [query, open])

  useEffect(() => {
    if (open) {
      setQuery('')
      setResults(readRecents())
      setActive(0)
      queueMicrotask(() => inputRef.current?.focus())
    }
  }, [open])

  const openEntity = useCallback(
    (entity: Entity) => {
      recordRecent(entity)
      setOpen(false)
      router.push(entity.route)
    },
    [router],
  )

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape') {
      setOpen(false)
    } else if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActive((index) => Math.min(index + 1, results.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((index) => Math.max(index - 1, 0))
    } else if (event.key === 'Enter' && results[active]) {
      event.preventDefault()
      openEntity(results[active])
    }
  }

  /* Keep the active row in view while arrowing. */
  useEffect(() => {
    listRef.current
      ?.querySelector(`[data-index="${active}"]`)
      ?.scrollIntoView({ block: 'nearest' })
  }, [active])

  if (!open) return null

  const groups = groupByType(results.map((entity) => ({ entity, score: 0 })))
  let flatIndex = -1

  return (
    <div
      className="dialog-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) setOpen(false)
      }}
      style={{
        position: 'fixed', inset: 0, zIndex: 120, background: 'var(--backdrop)',
        display: 'flex', justifyContent: 'center', alignItems: 'flex-start',
        padding: '12vh 20px 20px',
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search OmniSignal"
        className="dialog-panel"
        style={{
          width: '100%', maxWidth: 560, background: 'var(--surface-3)',
          border: '1px solid var(--line)', borderRadius: 'var(--r-lg)',
          boxShadow: 'var(--shadow-dialog)', overflow: 'hidden',
        }}
      >
        <input
          ref={inputRef}
          role="combobox"
          aria-expanded={results.length > 0}
          aria-controls="palette-results"
          aria-activedescendant={results[active] ? `palette-${active}` : undefined}
          className="input"
          placeholder="Search companies, research, watchlists, concepts…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={onKeyDown}
          style={{ height: 48, border: 'none', borderBottom: '1px solid var(--line)', borderRadius: 0, background: 'transparent', fontSize: '0.9375rem' }}
        />
        <div id="palette-results" role="listbox" ref={listRef} style={{ maxHeight: '52vh', overflowY: 'auto', padding: 6 }}>
          {results.length === 0 && (
            <p style={{ padding: '18px 14px', fontSize: '0.8125rem', color: 'var(--faint)' }}>
              {query.trim()
                ? settled ? 'Nothing matches — try a ticker, a page, or a concept.' : 'Searching…'
                : 'Type to search. Recent destinations appear here as you use the terminal.'}
            </p>
          )}
          {groups.map((group) => (
            <div key={group.type}>
              <p className="label" style={{ padding: '8px 10px 4px', fontSize: '0.625rem' }}>{group.label}</p>
              {group.items.map((entity) => {
                flatIndex += 1
                const index = flatIndex
                return (
                  <button
                    key={entity.id}
                    id={`palette-${index}`}
                    data-index={index}
                    type="button"
                    role="option"
                    aria-selected={index === active}
                    className={`screen-hit${index === active ? ' screen-hit--active' : ''}`}
                    onMouseEnter={() => setActive(index)}
                    onClick={() => openEntity(entity)}
                    style={{
                      display: 'flex', alignItems: 'baseline', gap: 10, width: '100%',
                      padding: '8px 10px', border: 'none', background: 'transparent',
                      borderRadius: 'var(--r-md)', cursor: 'pointer', textAlign: 'left',
                    }}
                  >
                    <span style={{ fontWeight: 550, fontSize: '0.8438rem', color: 'var(--text)', flexShrink: 0 }}>
                      {entity.title}
                    </span>
                    {entity.subtitle && (
                      <span style={{ fontSize: '0.75rem', color: 'var(--muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {entity.subtitle}
                      </span>
                    )}
                    <span className="label" style={{ marginLeft: 'auto', fontSize: '0.5625rem', color: 'var(--faint)', flexShrink: 0 }}>
                      {TYPE_LABELS[entity.type]}
                    </span>
                  </button>
                )
              })}
            </div>
          ))}
          {!settled && results.length > 0 && (
            <p style={{ padding: '6px 10px', fontSize: '0.6875rem', color: 'var(--faint)' }}>Searching…</p>
          )}
        </div>
        <p className="hairline-top" style={{ padding: '7px 12px', fontSize: '0.625rem', color: 'var(--faint)', display: 'flex', gap: 14 }}>
          <span>↑↓ navigate</span><span>↵ open</span><span>esc close</span>
        </p>
      </div>
    </div>
  )
}
