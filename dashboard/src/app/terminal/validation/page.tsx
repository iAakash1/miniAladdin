'use client'

import TerminalShell from '@/components/terminal/TerminalShell'
import ValidationView from '@/components/terminal/ValidationView'

export default function ValidationPage() {
  return (
    <TerminalShell loadingLabel="Loading validation…">
      <ValidationView />
    </TerminalShell>
  )
}
