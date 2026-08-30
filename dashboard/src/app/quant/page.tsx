'use client'

import TerminalShell from '@/components/terminal/TerminalShell'
import QuantResearchView from '@/components/terminal/QuantResearchView'

export default function QuantPage() {
  return (
    <TerminalShell loadingLabel="Reading experiment artifacts…">
      <QuantResearchView />
    </TerminalShell>
  )
}
