import { ClerkProvider } from '@clerk/nextjs'
import type { Metadata } from 'next'

import { EntitlementProvider } from '@/components/system/Entitlement'

export const metadata: Metadata = {
  title: { default: 'Intermediate', template: '%s · OmniSignal' },
  description: 'Equity signals with factor, risk, evidence and agent detail.',
  robots: { index: false, follow: false },
}

export const dynamic = 'force-dynamic'

export default function IntermediateLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider>
      <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)' }}>
        <EntitlementProvider>{children}</EntitlementProvider>
      </div>
    </ClerkProvider>
  )
}
