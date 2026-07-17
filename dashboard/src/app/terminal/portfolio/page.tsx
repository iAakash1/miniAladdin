'use client'

import PortfolioView from '@/components/terminal/PortfolioView'
import TerminalShell from '@/components/terminal/TerminalShell'

export default function PortfolioPage() {
  return (
    <TerminalShell loadingLabel="Loading portfolio…">
      <PortfolioView />
    </TerminalShell>
  )
}
