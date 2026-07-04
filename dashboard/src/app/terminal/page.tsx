'use client'

import { useEffect, useState } from 'react'
import { useUser } from '@clerk/nextjs'

import MarketDashboard from '@/components/terminal/MarketDashboard'
import ScreenSearch from '@/components/terminal/ScreenSearch'
import TerminalHeader from '@/components/terminal/TerminalHeader'
import UpgradeDialog from '@/components/terminal/UpgradeDialog'
import { fetchMacroClient } from '@/lib/api'
import { useTodayCount } from '@/lib/usage'
import type { Macro } from '@/lib/types'

/**
 * Terminal home: the Market Intelligence dashboard.
 * "What is happening in the market?" — before any ticker is typed.
 * Single-ticker analysis lives at /terminal/analyze.
 */
export default function MarketPage() {
  const { user, isLoaded } = useUser()
  const isPro = (user?.publicMetadata?.isPro as boolean) ?? false

  const [macro, setMacro] = useState<Macro | null>(null)
  const usedToday = useTodayCount()
  const [upgradeOpen, setUpgradeOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchMacroClient().then((result) => {
      if (!cancelled && result) setMacro(result)
    })
    return () => {
      cancelled = true
    }
  }, [])

  if (!isLoaded) {
    return (
      <div
        style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
        aria-busy="true"
      >
        <span className="label">Loading terminal…</span>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <TerminalHeader
        macro={macro}
        isPro={isPro}
        usedToday={usedToday}
        onUpgrade={() => setUpgradeOpen(true)}
      />
      <UpgradeDialog open={upgradeOpen} onClose={() => setUpgradeOpen(false)} />

      <main
        id="main"
        style={{
          flex: 1,
          width: '100%',
          maxWidth: 1200,
          margin: '0 auto',
          padding: '28px clamp(16px, 3vw, 28px) 64px',
        }}
      >
        <div style={{ marginBottom: 26 }}>
          <ScreenSearch />
        </div>
        <MarketDashboard />
      </main>
    </div>
  )
}
