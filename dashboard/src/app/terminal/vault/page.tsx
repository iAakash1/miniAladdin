'use client'

import TerminalShell from '@/components/terminal/TerminalShell'
import VaultView from '@/components/terminal/VaultView'

export default function VaultPage() {
  return (
    <TerminalShell loadingLabel="Loading vault…">
      <VaultView />
    </TerminalShell>
  )
}
