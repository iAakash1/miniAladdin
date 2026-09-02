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

import { useState, type ReactNode } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

import { Status, type ResearchState } from './index'

/* Navigation follows the research loop, not the backend modules. The groups
   are the questions a researcher actually moves between. */
export const WORKBENCH: { group: string; items: { href: string; label: string; key: string }[] }[] = [
  {
    group: 'Observe',
    items: [
      { href: '/terminal/command', label: 'Command', key: 'c' },
      { href: '/terminal/analyze', label: 'Securities', key: 's' },
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
      { href: '/terminal/experiments', label: 'Experiments', key: 'x' },
    ],
  },
  {
    group: 'Allocate',
    items: [
      { href: '/terminal/book', label: 'Book', key: 'b' },
      { href: '/terminal/risk', label: 'Risk', key: 'r' },
    ],
  },
  {
    group: 'Verify',
    items: [
      { href: '/terminal/data', label: 'Data', key: 'd' },
      { href: '/terminal/handbook', label: 'Handbook', key: 'y' },
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
  const [navOpen, setNavOpen] = useState(false)
  const [ctxOpen, setCtxOpen] = useState(false)

  return (
    <div className="wb">
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
