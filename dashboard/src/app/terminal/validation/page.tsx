'use client'

import { useEffect, useState } from 'react'
import { useUser } from '@clerk/nextjs'

import TerminalHeader from '@/components/terminal/TerminalHeader'
import UpgradeDialog from '@/components/terminal/UpgradeDialog'
import ValidationView from '@/components/terminal/ValidationView'
import { fetchMacroClient } from '@/lib/api'
import { useTodayCount } from '@/lib/usage'
import type { Macro } from '@/lib/types'

export default function ValidationPage() {
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
        <span className="label">Loading validation…</span>
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
        <ValidationView />
      </main>
    </div>
  )
}
