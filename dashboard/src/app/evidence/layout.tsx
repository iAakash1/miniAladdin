import NonceClerkProvider from '@/components/auth/NonceClerkProvider'
import type { Metadata } from 'next'

import { EntitlementProvider } from '@/components/system/Entitlement'

export const metadata: Metadata = {
  title: { default: 'Evidence inspector', template: '%s · OmniSignal' },
  robots: { index: false, follow: false },
}

export const dynamic = 'force-dynamic'

export default function EvidenceLayout({ children }: { children: React.ReactNode }) {
  return (
    <NonceClerkProvider>
      <EntitlementProvider>{children}</EntitlementProvider>
    </NonceClerkProvider>
  )
}
