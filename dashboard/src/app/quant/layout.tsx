import { ClerkProvider } from '@clerk/nextjs'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Quant',
  robots: { index: false, follow: false },
}

/* Same contract as the terminal: per-user, auth-gated, never prerendered.
   `/quant` sits at the top level rather than under `/terminal` because it is a
   research surface rather than a per-symbol workspace, but it uses TerminalShell
   and therefore needs the same ClerkProvider the terminal layout supplies. */
export const dynamic = 'force-dynamic'

export default function QuantLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider>
      <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)' }}>
        {children}
      </div>
    </ClerkProvider>
  )
}
