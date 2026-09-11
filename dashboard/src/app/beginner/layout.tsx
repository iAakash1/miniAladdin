import { ClerkProvider } from '@clerk/nextjs'
import type { Metadata } from 'next'

import { EntitlementProvider } from '@/components/system/Entitlement'

export const metadata: Metadata = {
  title: 'OmniSignal — Beginner',
  description: 'Plain-language equity signals, risk and ranked ideas.',
  robots: { index: false, follow: false },
}

/* Rankings and prices carry as-of stamps; never prerender a stamp. */
export const dynamic = 'force-dynamic'

export default function BeginnerLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider>
      <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)' }}>
        <EntitlementProvider>{children}</EntitlementProvider>
      </div>
    </ClerkProvider>
  )
}
