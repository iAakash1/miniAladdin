import { ClerkProvider } from '@clerk/nextjs'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Start — OmniSignal',
  robots: { index: false, follow: false },
}

export const dynamic = 'force-dynamic'

export default function StartLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider>
      <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)' }}>
        {children}
      </div>
    </ClerkProvider>
  )
}
