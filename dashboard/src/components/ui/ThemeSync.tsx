'use client'

import { usePathname } from 'next/navigation'
import { useEffect } from 'react'

/** Routes that are part of the terminal and therefore dark by default.
 *
 *  `/company/[ticker]` belongs here even though its path does not start with
 *  `/terminal`: it renders the terminal chrome, it is where the Research tab
 *  lands, and it is reached by clicking a symbol from inside the terminal.
 *  Matching on the path prefix alone flipped the entire app from dark to
 *  light in the middle of a research workflow — the theme followed the URL
 *  rather than the surface the user was actually in.
 */
const TERMINAL_ROUTES = ['/terminal', '/company']

/**
 * Keeps the route-based theme default working across client-side navigation:
 * users without an explicit preference get the light site and the dark
 * terminal. An explicit choice (localStorage) always wins.
 */
export default function ThemeSync() {
  const pathname = usePathname()

  useEffect(() => {
    let stored: string | null = null
    try {
      stored = localStorage.getItem('omni-theme')
    } catch {
      /* private mode */
    }
    if (stored === 'light' || stored === 'dark') return
    const inTerminal = TERMINAL_ROUTES.some((route) => pathname.startsWith(route))
    document.documentElement.dataset.theme = inTerminal ? 'dark' : 'light'
  }, [pathname])

  return null
}
