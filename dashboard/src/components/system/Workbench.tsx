/**
 * The shell every workspace sits in.
 *
 * Replaces the centred 1200px content column, which is a reading layout. A
 * research terminal is not read top to bottom — it is navigated, and the thing
 * being navigated needs to stay on screen while its context changes. Hence
 * three regions that scroll independently:
 *
 *   LEFT     where you are in the research loop
 *   CENTRE   the analytical workspace
 *   RIGHT    context for whatever is selected — provenance, method, assumptions
 *   BOTTOM   research state, always visible, never a banner
 *
 * The bottom rail is the piece that matters most. Research state is this
 * product's differentiator, and a state that appears only when something is
 * wrong teaches people that its absence means everything is fine. It is
 * present on every screen instead, reading the same way whether the news is
 * good or not.
 */
'use client'

import { useEffect, useState, type ReactNode } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'

import { Status, type ResearchState } from './index'
import Palette, { applyStoredDensity } from './Palette'
import Shortcuts from './Shortcuts'
import { usePinnedObjects, useRecentObjects } from '@/lib/research/history'
import { KINDS, href as objectHref } from '@/lib/research/objects'

/** `g` then a letter jumps between workspaces. Inert while typing. */
const GOTO: Record<string, string> = {
  c: '/terminal/command', s: '/terminal/security', f: '/terminal/factorlab',
  g: '/terminal/signals', m: '/terminal/lab', v: '/terminal/evidence',
  x: '/terminal/experiments', b: '/terminal/book', r: '/terminal/risk',
  d: '/terminal/data', y: '/terminal/handbook', p: '/terminal/performance',
  o: '/terminal/providers', n: '/terminal/provenance', k: '/terminal/covariance',
  w: '/terminal/compare', a: '/terminal/gates', e: '/terminal/memos', t: '/terminal/timeline',
  i: '/terminal/analyze', l: '/terminal/factors', z: '/terminal/portfolio',
  u: '/terminal/validation', h: '/terminal/graph',
}

/* Navigation follows the research loop, not the backend modules. The groups
   are the questions a researcher actually moves between. */
export const WORKBENCH: { group: string; items: { href: string; label: string; key: string }[] }[] = [
  {
    group: 'Observe',
    items: [
      { href: '/terminal/command', label: 'Command', key: 'c' },
      { href: '/terminal/security', label: 'Securities', key: 's' },
    ],
  },
  {
    group: 'Explain',
    items: [
      { href: '/terminal/factorlab', label: 'Factors', key: 'f' },
      { href: '/terminal/signals', label: 'Signals', key: 'g' },
    ],
  },
  {
    group: 'Validate',
    items: [
      { href: '/terminal/lab', label: 'Models', key: 'm' },
      { href: '/terminal/evidence', label: 'Evidence', key: 'v' },
      { href: '/terminal/gates', label: 'Gates', key: 'a' },
      { href: '/terminal/performance', label: 'Performance', key: 'p' },
      { href: '/terminal/experiments', label: 'Experiments', key: 'x' },
      { href: '/terminal/compare', label: 'Compare', key: 'w' },
    ],
  },
  {
    group: 'Allocate',
    items: [
      { href: '/terminal/book', label: 'Book', key: 'b' },
      { href: '/terminal/risk', label: 'Risk', key: 'r' },
      { href: '/terminal/covariance', label: 'Covariance', key: 'k' },
    ],
  },
  // The deep surfaces that predate the workbench and carry analysis the rebuilt
  // workspaces do not: the full security report, the factor lab's cross-section
  // and screen, the ownership and positions views, the knowledge graph. They are
  // listed rather than deleted, because deleting working analysis to tidy an
  // architecture is a bad trade, and rather than left unlinked, because a page
  // nobody can reach is its own kind of debt.
  {
    group: 'Deep',
    items: [
      { href: '/terminal/analyze', label: 'Report', key: 'i' },
      { href: '/terminal/factors', label: 'Factor lab', key: 'l' },
      { href: '/terminal/portfolio', label: 'Positions', key: 'z' },
      { href: '/terminal/validation', label: 'Validation', key: 'u' },
      { href: '/terminal/graph', label: 'Graph', key: 'h' },
    ],
  },
  {
    group: 'Verify',
    items: [
      { href: '/terminal/data', label: 'Data', key: 'd' },
      { href: '/terminal/providers', label: 'Providers', key: 'o' },
      { href: '/terminal/provenance', label: 'Provenance', key: 'n' },
      { href: '/terminal/handbook', label: 'Handbook', key: 'y' },
      { href: '/terminal/memos', label: 'Memos', key: 'e' },
      { href: '/terminal/timeline', label: 'Timeline', key: 't' },
    ],
  },
]

export interface RailState {
  label: string
  state: ResearchState
  detail?: string
}

export default function Workbench({
  title, subtitle, actions, context, rail, children,
}: {
  title: string
  subtitle?: ReactNode
  actions?: ReactNode
  /** Right column. Omit and the workspace takes the full width. */
  context?: ReactNode
  /** Bottom research-state rail. */
  rail?: RailState[]
  children: ReactNode
}) {
  const pathname = usePathname()
  const router = useRouter()
  const [navOpen, setNavOpen] = useState(false)
  const [ctxOpen, setCtxOpen] = useState(false)
  const recent = useRecentObjects()
  const pinned = usePinnedObjects()

  useEffect(() => { applyStoredDensity() }, [])

  // Two-key navigation. A leading `g` arms the next letter for one second,
  // which is short enough that it never swallows a keystroke the user meant
  // for something else.
  useEffect(() => {
    let armed = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (armed) {
        armed = false
        if (timer) clearTimeout(timer)
        const dest = GOTO[e.key.toLowerCase()]
        if (dest) { e.preventDefault(); router.push(dest) }
        return
      }
      if (e.key === 'g') {
        armed = true
        timer = setTimeout(() => { armed = false }, 1000)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => { window.removeEventListener('keydown', onKey); if (timer) clearTimeout(timer) }
  }, [router])

  return (
    <div className="wb">
      <Palette />
      <Shortcuts />
      <nav className={`wb-rail${navOpen ? ' is-open' : ''}`} aria-label="Workbench">
        {WORKBENCH.map((section) => (
          <div className="wb-group" key={section.group}>
            <div className="sys-label wb-group-label">{section.group}</div>
            {section.items.map((item) => {
              const active = pathname === item.href
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`wb-link${active ? ' is-active' : ''}`}
                  aria-current={active ? 'page' : undefined}
                  onClick={() => setNavOpen(false)}
                >
                  <span>{item.label}</span>
                  <kbd className="wb-key">g {item.key}</kbd>
                </Link>
              )
            })}
          </div>
        ))}

        {pinned.length ? (
          <div className="wb-group">
            <div className="sys-label wb-group-label">Pinned</div>
            {pinned.slice(0, 6).map((o) => (
              <Link key={`p-${o.kind}-${o.id}`} href={objectHref(o)} className="wb-link" title={`${KINDS[o.kind].plural} · ${o.detail ?? ''}`}>
                <span style={{ fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.label}</span>
                <span className="wb-key" style={{ opacity: 1 }}>{KINDS[o.kind].glyph}</span>
              </Link>
            ))}
          </div>
        ) : null}

        {recent.length ? (
          <div className="wb-group">
            <div className="sys-label wb-group-label">Recent</div>
            {recent.slice(0, 6).map((o) => (
              <Link key={`r-${o.kind}-${o.id}`} href={objectHref(o)} className="wb-link" title={`${KINDS[o.kind].plural} · ${o.detail ?? ''}`}>
                <span style={{ fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.label}</span>
                <span className="wb-key" style={{ opacity: 1 }}>{KINDS[o.kind].glyph}</span>
              </Link>
            ))}
          </div>
        ) : null}
      </nav>

      <div className="wb-main">
        <header className="wb-head">
          <button
            className="wb-toggle sys-focusable"
            onClick={() => setNavOpen((v) => !v)}
            aria-expanded={navOpen}
            aria-label="Toggle navigation"
          >☰</button>
          <div className="wb-head-title">
            <h1 className="sys-title">{title}</h1>
            {subtitle ? <span className="sys-meta">{subtitle}</span> : null}
          </div>
          <div className="wb-head-actions">
            <button
              className="sys-btn"
              onClick={() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }))}
              title="Search objects and commands"
            >
              search <kbd style={{ font: '400 var(--t-micro)/1 var(--font-mono)', opacity: 0.7 }}>⌘K</kbd>
            </button>
            <button
              className="sys-btn"
              onClick={() => {
                const order = ['compact', 'default', 'comfortable']
                const el = document.documentElement
                const next = order[(order.indexOf(el.getAttribute('data-density') ?? 'default') + 1) % order.length]
                el.setAttribute('data-density', next)
                try { window.localStorage.setItem('ma.density', next) } catch { /* ignore */ }
              }}
              title="Cycle information density"
            >
              density
            </button>
            <button
              className="sys-btn"
              onClick={() => window.dispatchEvent(new KeyboardEvent('keydown', { key: '?' }))}
              title="Keyboard shortcuts"
            >
              ?
            </button>
            {actions}
            {context ? (
              <button
                className="wb-toggle wb-toggle--ctx sys-focusable"
                onClick={() => setCtxOpen((v) => !v)}
                aria-expanded={ctxOpen}
                aria-label="Toggle context"
              >Context</button>
            ) : null}
          </div>
        </header>

        <div className="wb-body">
          <main className="wb-workspace">{children}</main>
          {context ? (
            <aside className={`wb-context${ctxOpen ? ' is-open' : ''}`} aria-label="Context">
              {context}
            </aside>
          ) : null}
        </div>

        {rail?.length ? (
          <footer className="wb-status" aria-label="Research state">
            {rail.map((r) => (
              <div className="wb-status-item" key={r.label} title={r.detail}>
                <span className="sys-label wb-status-key">{r.label}</span>
                <Status state={r.state} label={r.detail ?? r.state} />
              </div>
            ))}
          </footer>
        ) : null}
      </div>
    </div>
  )
}
