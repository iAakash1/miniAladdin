import { ClerkProvider } from '@clerk/nextjs'
import type { Metadata } from 'next'

import { EntitlementProvider } from '@/components/system/Entitlement'

export const metadata: Metadata = {
  title: { absolute: 'Opening terminal · OmniSignal' },
  robots: { index: false, follow: false },
}

export const dynamic = 'force-dynamic'

/* The entitlement provider registers the session-token accessor that
   authenticated requests wait on. Without it the capabilities request here
   waited out a ten-second timeout and then went out unauthenticated. */
export default function StartLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider>
      <EntitlementProvider>{children}</EntitlementProvider>
    </ClerkProvider>
  )
}
