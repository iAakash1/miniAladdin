'use client'

import TerminalShell from '@/components/terminal/TerminalShell'
import ModelIntelligenceView from '@/components/terminal/ModelIntelligenceView'

export default function ModelsPage() {
  return (
    <TerminalShell loadingLabel="Reading study artifacts…">
      <ModelIntelligenceView />
    </TerminalShell>
  )
}
