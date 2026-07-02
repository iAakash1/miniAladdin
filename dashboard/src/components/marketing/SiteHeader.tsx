'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState } from 'react'
import Logo from '@/components/ui/Logo'

const NAV = [
  { href: '/#methodology', label: 'Methodology' },
  { href: '/#pricing', label: 'Pricing' },
  { href: '/news', label: 'News' },
]

export default function SiteHeader() {
  const [menuOpen, setMenuOpen] = useState(false)
  const pathname = usePathname()
  // Every link inside the mobile menu closes it on click, so no
  // navigation-watching effect is needed.

  return (
    <header
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 50,
        background: 'color-mix(in srgb, var(--paper) 92%, transparent)',
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
        borderBottom: '1px solid var(--line)',
      }}
    >
      <div
        className="container"
        style={{ display: 'flex', alignItems: 'center', height: 60, gap: 28 }}
      >
        <Link href="/" style={{ textDecoration: 'none', flexShrink: 0 }} aria-label="OmniSignal home">
          <Logo size={21} />
        </Link>

        <nav aria-label="Primary" className="site-nav" style={{ display: 'flex', gap: 4 }}>
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="btn btn--ghost btn--sm"
              style={{
                color: pathname === item.href ? 'var(--text)' : undefined,
                fontWeight: 500,
              }}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          <Link href="/sign-in" className="btn btn--ghost btn--sm site-signin" style={{ fontWeight: 500 }}>
            Sign in
          </Link>
          <Link href="/terminal" className="btn btn--primary btn--sm">
            Open terminal
          </Link>
          <button
            type="button"
            className="btn btn--ghost btn--sm menu-toggle"
            aria-expanded={menuOpen}
            aria-controls="mobile-nav"
            onClick={() => setMenuOpen((v) => !v)}
          >
            {menuOpen ? 'Close' : 'Menu'}
          </button>
        </div>
      </div>

      {menuOpen && (
        <nav
          id="mobile-nav"
          aria-label="Mobile"
          className="fade-in"
          style={{
            borderTop: '1px solid var(--line)',
            background: 'var(--paper)',
            padding: '8px 20px 16px',
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
          }}
        >
          {[...NAV, { href: '/sign-in', label: 'Sign in' }].map((item) => (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setMenuOpen(false)}
              style={{
                padding: '12px 4px',
                textDecoration: 'none',
                fontSize: '0.9375rem',
                fontWeight: 500,
                color: 'var(--text)',
                borderBottom: '1px solid var(--line)',
              }}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      )}
    </header>
  )
}
