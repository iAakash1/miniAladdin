import { ClerkProvider } from '@clerk/nextjs'
import type { Metadata } from 'next'

import { EntitlementProvider } from '@/components/system/Entitlement'

export const metadata: Metadata = {
  title: 'Explore — miniAladdin',
  description: 'Securities ranked across momentum, quality, value, risk and attention.',
}

/* Rankings are recomputed from a cached snapshot and carry a generated-at
   stamp, so this route is never prerendered into a build artefact where that
   stamp would age silently. */
export const dynamic = 'force-dynamic'

export default function ExploreLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider>
      <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)' }}>
        <EntitlementProvider>{children}</EntitlementProvider>
      </div>
    </ClerkProvider>
  )
}
