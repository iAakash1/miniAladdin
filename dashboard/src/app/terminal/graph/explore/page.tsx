'use client'

import { Suspense } from 'react'

import GraphExplorer from '@/components/terminal/GraphExplorer'
import TerminalShell from '@/components/terminal/TerminalShell'
import Skeleton from '@/components/ui/Skeleton'

/**
 * Single-node exploration — the focused counterpart to the workspace:
 * one entity at the centre, its neighbours around it, re-centre on click.
 */
export default function GraphExplorePage() {
  return (
    <TerminalShell loadingLabel="Loading graph…">
      <Suspense fallback={<Skeleton height={420} />}>
        <GraphExplorer />
      </Suspense>
    </TerminalShell>
  )
}
