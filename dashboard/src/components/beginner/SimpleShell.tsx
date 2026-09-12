'use client'

/**
 * The Simple-mode shell.
 *
 * A separate shell rather than the research terminal with items hidden. The
 * terminal's rail carries twenty-eight destinations grouped by research
 * concern — covariance, calibration gates, registries — and hiding two thirds
 * of them would still leave a reader navigating a structure built for a
 * different job. Six destinations, named for what a person wants to do.
 *
 * The visual language is deliberately the terminal's: same tokens, same rail
 * geometry, same typography. Simple mode is the same product at a different
 * density, and it should look like it.
 */

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useState, type ReactNode } from 'react'

import { setExperienceMode } from '@/lib/capabilities'

const DESTINATIONS: Array<{ href: string; label: string; glyph: string }> = [
  { href: '/beginner', label: 'Home', glyph: '◆' },
  { href: '/explore', label: 'Explore', glyph: '⊞' },
  { href: '/terminal/watchlists', label: 'Watchlist', glyph: '★' },
  { href: '/terminal/portfolio', label: 'Portfolio', glyph: '▦' },
  { href: '/learn', label: 'Learn', glyph: '?' },
]

export default function SimpleShell({
  title, subtitle, children,
}: {
  title: string
  subtitle?: string
  children: ReactNode
}) {
  const pathname = usePathname()
  const router = useRouter()
  const [navOpen, setNavOpen] = useState(false)
  const [switching, setSwitching] = useState(false)

  async function toAdvanced() {
    setSwitching(true)
    const ok = await setExperienceMode('advanced')
    setSwitching(false)
    if (ok) router.push('/terminal/command')
  }

  return (
    <div className="wb">
      <nav className={`wb-rail${navOpen ? ' is-open' : ''}`} aria-label="OmniSignal">
        <div className="wb-group" data-primary="">
          <div className="sys-label wb-group-label">OmniSignal</div>
          {DESTINATIONS.map((item) => {
            const active = pathname === item.href
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
          <button type="button" className="bg__switch" onClick={() => void toAdvanced()} disabled={switching}>
            {switching ? 'Switching…' : 'Switch to Advanced'}
          </button>
        </div>
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
        </header>
        <div className="wb-body">
          <main className="wb-workspace">{children}</main>
        </div>
      </div>
    </div>
  )
}
