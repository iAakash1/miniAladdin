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
      {/* The research surface is dark on this route regardless of the app theme.
          It is read for long stretches beside a terminal, and the dense numeric
          tables below depend on the dark palette for their contrast ratios.
          Scoped with `data-theme` on this wrapper rather than by editing
          TerminalShell, so the chrome matches here and nothing changes on
          /terminal or anywhere else. */}
      <div
        data-theme="dark"
        style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)' }}
      >
        {children}
      </div>
    </ClerkProvider>
  )
}
