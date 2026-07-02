import { ClerkProvider } from '@clerk/nextjs'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Terminal',
  robots: { index: false, follow: false },
}

/* The terminal is per-user and gated by auth — never prerendered. */
export const dynamic = 'force-dynamic'

export default function TerminalLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider>
      {/* Theme comes from html[data-theme]: dark by default on this route,
          light if the user has explicitly chosen it. */}
      <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)' }}>{children}</div>
    </ClerkProvider>
  )
}
