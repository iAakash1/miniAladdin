'use client'

import TerminalShell from '@/components/terminal/TerminalShell'
import FactorLabView from '@/components/terminal/FactorLabView'

export default function FactorLabPage() {
  return (
    <TerminalShell loadingLabel="Building factor panel…">
      <FactorLabView />
    </TerminalShell>
  )
}
