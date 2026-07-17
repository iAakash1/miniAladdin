'use client'

import MethodologyView from '@/components/terminal/MethodologyView'
import TerminalShell from '@/components/terminal/TerminalShell'

export default function MethodologyPage() {
  return (
    <TerminalShell loadingLabel="Loading methodology…">
      <MethodologyView />
    </TerminalShell>
  )
}
