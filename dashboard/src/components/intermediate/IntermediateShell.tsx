'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState, type ReactNode } from 'react'

import ModeSwitch from '@/components/beginner/ModeSwitch'

const DESTINATIONS = [
  { href: '/intermediate', label: 'Home', glyph: '◆' },
  { href: '/explore', label: 'Explore', glyph: '⊞' },
  { href: '/intermediate/watchlist', label: 'Watchlist', glyph: '★' },
  { href: '/intermediate/portfolio', label: 'Portfolio', glyph: '▦' },
  { href: '/intermediate/compare', label: 'Compare', glyph: '⇄' },
  { href: '/learn', label: 'Learn', glyph: '?' },
]

/** Analysis density between the plain-language home and the research terminal. */
export default function IntermediateShell({
  title, subtitle, children,
}: {
  title: string
  subtitle?: string
  children: ReactNode
}) {
  const pathname = usePathname()
  const [navOpen, setNavOpen] = useState(false)

  return (
    <div className="wb" data-experience="intermediate">
      <nav className={`wb-rail${navOpen ? ' is-open' : ''}`} aria-label="OmniSignal Intermediate">
        <div className="wb-group" data-primary="">
          <div className="sys-label wb-group-label">Intermediate</div>
          {DESTINATIONS.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`)
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`wb-link${active ? ' is-active' : ''}`}
                aria-current={active ? 'page' : undefined}
                onClick={() => setNavOpen(false)}
              >
                <span className="wb-glyph" aria-hidden>{item.glyph}</span>
                <span className="wb-label">{item.label}</span>
              </Link>
            )
          })}
        </div>

        <div className="wb-group">
          <div className="sys-label wb-group-label">Experience</div>
          <ModeSwitch to="beginner" />
          <ModeSwitch to="advanced" />
        </div>
      </nav>

      <div className="wb-main">
        <header className="wb-head">
          <button
            className="wb-toggle sys-focusable"
            onClick={() => setNavOpen((value) => !value)}
            aria-expanded={navOpen}
            aria-label="Toggle navigation"
          >☰</button>
          <div className="wb-head-title">
            <h1 className="sys-title">{title}</h1>
            {subtitle ? <span className="sys-meta">{subtitle}</span> : null}
          </div>
        </header>
        <div className="wb-body">
          <main className="wb-workspace">{children}</main>
        </div>
      </div>
    </div>
  )
}
