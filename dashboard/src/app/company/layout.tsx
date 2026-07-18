import { ClerkProvider } from '@clerk/nextjs'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Company research',
  robots: { index: false, follow: false },
}

/* Company research is per-user (auth-gated, usage-metered) — never prerendered. */
export const dynamic = 'force-dynamic'

export default function CompanyLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider>
      <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)' }}>{children}</div>
    </ClerkProvider>
  )
}
