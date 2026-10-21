'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState, useSyncExternalStore } from 'react'
import Logo from '@/components/ui/Logo'
import ThemeToggle from '@/components/ui/ThemeToggle'

const NAV = [
  { href: '/#methodology', label: 'Methodology' },
  { href: '/#pricing', label: 'Pricing' },
  { href: '/news', label: 'News' },
]

/**
 * Clerk marks auth state in the readable `__client_uat` cookie (a unix
 * timestamp; 0 or absent = signed out). Reading it keeps the marketing
 * pages free of Clerk's JavaScript while still reflecting the session.
 */
const noopSubscribe = () => () => {}
function useSignedIn(): boolean {
  return useSyncExternalStore(
    noopSubscribe,
    () => /(?:^|;\s*)__client_uat(?:_[^=]*)?=[1-9]/.test(document.cookie),
    () => false,
  )
}

export default function SiteHeader() {
  const [menuOpen, setMenuOpen] = useState(false)
  const pathname = usePathname()
  const signedIn = useSignedIn()
  // Every link inside the mobile menu closes it on click, so no
  // navigation-watching effect is needed.

  return (
    <header className="site-header">
      <div className="container site-header__bar">
        <Link href="/" className="site-header__home" aria-label="OmniSignal home">
          <Logo size={22} />
        </Link>

        <nav aria-label="Primary" className="site-nav">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="sys-btn sys-btn--ghost site-nav__link"
              aria-current={pathname === item.href ? 'page' : undefined}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="site-header__end">
          <ThemeToggle />
          {!signedIn && (
            <Link href="/sign-in" className="sys-btn sys-btn--ghost site-nav__link site-signin">
              Sign in
            </Link>
          )}
          {/* Not prefetched. Next fetches a link's payload on hover or when
              it enters the viewport, and every terminal route is behind
              Clerk, so the prefetch is answered with a cross-origin redirect
              to the hosted sign-in page. That fails CORS, which put a failed
              request and a console error on the public site for every visitor
              who never clicked it. Navigation is unaffected — a click is a
              full navigation, not a fetch. */}
          <Link href="/terminal" prefetch={false} className="sys-btn sys-btn--primary">
            Open terminal
          </Link>
          {/* An icon on a phone, where the bar has no room for a word; the
              label stays for assistive technology. */}
          <button
            type="button"
            className="sys-btn sys-btn--ghost menu-toggle"
            aria-expanded={menuOpen}
            aria-controls="mobile-nav"
            onClick={() => setMenuOpen((v) => !v)}
          >
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" focusable="false">
              {menuOpen ? (
                <path d="M4 4l10 10M14 4L4 14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              ) : (
                <path d="M3 5h12M3 9h12M3 13h8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              )}
            </svg>
            <span className="visually-hidden">{menuOpen ? 'Close menu' : 'Menu'}</span>
          </button>
        </div>
      </div>

      {menuOpen && (
        <nav id="mobile-nav" aria-label="Mobile" className="fade-in site-mnav">
          {[...NAV, ...(signedIn ? [] : [{ href: '/sign-in', label: 'Sign in' }])].map((item) => (
            <Link key={item.href} href={item.href} onClick={() => setMenuOpen(false)} className="site-mnav__link">
              {item.label}
            </Link>
          ))}
        </nav>
      )}
    </header>
  )
}
