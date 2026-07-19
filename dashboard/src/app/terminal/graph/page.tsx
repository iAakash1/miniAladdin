'use client'

import { Suspense } from 'react'

import GraphWorkspace from '@/components/terminal/GraphWorkspace'
import TerminalShell from '@/components/terminal/TerminalShell'
import Skeleton from '@/components/ui/Skeleton'

/**
 * /terminal/graph — the Knowledge Graph Workspace. Every piece of state
 * (companies, depth, filters, as-of date) lives in the URL, so any
 * workspace is a permanent, shareable address, exactly like every other
 * research surface. Single-node exploration remains available at
 * /terminal/graph/explore.
 */
export default function GraphPage() {
  return (
    <TerminalShell loadingLabel="Loading graph…">
      <Suspense fallback={<Skeleton height={420} />}>
        <GraphWorkspace />
      </Suspense>
    </TerminalShell>
  )
}
