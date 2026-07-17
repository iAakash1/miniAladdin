'use client'

import MarketDashboard from '@/components/terminal/MarketDashboard'
import TerminalShell from '@/components/terminal/TerminalShell'

/**
 * Terminal home: the Market Intelligence dashboard.
 * "What is happening in the market?" — before any ticker is typed.
 * Single-ticker analysis lives at /terminal/analyze.
 */
export default function MarketPage() {
  return (
    <TerminalShell loadingLabel="Loading terminal…">
      <MarketDashboard />
    </TerminalShell>
  )
}
