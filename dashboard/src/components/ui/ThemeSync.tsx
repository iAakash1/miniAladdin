'use client'

import { usePathname } from 'next/navigation'
import { useEffect } from 'react'

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
    document.documentElement.dataset.theme = pathname.startsWith('/terminal') ? 'dark' : 'light'
  }, [pathname])

  return null
}
