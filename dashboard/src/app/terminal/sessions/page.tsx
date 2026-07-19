'use client'

import SessionsView from '@/components/terminal/SessionsView'
import TerminalShell from '@/components/terminal/TerminalShell'

/** /terminal/sessions — every investigation, newest-opened first. */
export default function SessionsPage() {
  return (
    <TerminalShell loadingLabel="Loading investigations…">
      <SessionsView />
    </TerminalShell>
  )
}
