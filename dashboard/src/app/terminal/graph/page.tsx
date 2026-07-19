'use client'

import { Suspense } from 'react'

import GraphExplorer from '@/components/terminal/GraphExplorer'
import TerminalShell from '@/components/terminal/TerminalShell'
import Skeleton from '@/components/ui/Skeleton'

/**
 * /terminal/graph — the Knowledge Graph Explorer. The selected node lives
 * in the URL (?node=…&label=…), so any point in an exploration is a
 * permanent, shareable address, exactly like every other research surface.
 */
export default function GraphPage() {
  return (
    <TerminalShell loadingLabel="Loading graph…">
      <Suspense fallback={<Skeleton height={420} />}>
        <GraphExplorer />
      </Suspense>
    </TerminalShell>
  )
}
