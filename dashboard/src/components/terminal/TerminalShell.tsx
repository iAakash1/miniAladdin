'use client'

import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { useUser } from '@clerk/nextjs'

import CommandPalette from '@/components/terminal/CommandPalette'
import TerminalHeader from '@/components/terminal/TerminalHeader'
import UpgradeDialog from '@/components/terminal/UpgradeDialog'
import { fetchMacroClient } from '@/lib/api'
import { syncProfile } from '@/lib/persistence'
import { useTodayCount } from '@/lib/usage'
import type { Macro } from '@/lib/types'

export interface TerminalShellContext {
  isPro: boolean
  usedToday: number
  requestUpgrade: (reason?: 'limit' | 'feature') => void
}

interface TerminalShellProps {
  /** Shown while Clerk resolves the session, e.g. "Loading portfolio…". */
  loadingLabel: string
  /** Plain children for simple pages; a render function for views that
   *  gate features on Pro status or open the upgrade dialog themselves. */
  children: ReactNode | ((shell: TerminalShellContext) => ReactNode)
}

/**
 * Shared chrome for every /terminal/* page: the Clerk loading gate, sticky
 * header with live macro readout, the upgrade dialog, and the 1200px
 * content column. Previously each page carried its own copy of all of
 * this — one implementation keeps spacing, loading behavior and the
 * upgrade flow identical across the terminal.
 */
export default function TerminalShell({ loadingLabel, children }: TerminalShellProps) {
  const { user, isLoaded } = useUser()
  const isPro = (user?.publicMetadata?.isPro as boolean) ?? false

  const [macro, setMacro] = useState<Macro | null>(null)
  const usedToday = useTodayCount()
  const [upgrade, setUpgrade] = useState<{ open: boolean; reason?: 'limit' | 'feature' }>({ open: false })

  useEffect(() => {
    let cancelled = false
    fetchMacroClient().then((result) => {
      if (!cancelled && result) setMacro(result)
    })
    return () => {
      cancelled = true
    }
  }, [])

  /* Profile auto-create/refresh on first successful login — best-effort,
     once per browser session. */
  useEffect(() => {
    if (!isLoaded || !user) return
    try {
      if (sessionStorage.getItem('omni-profile-synced')) return
      sessionStorage.setItem('omni-profile-synced', '1')
    } catch {
      /* private mode: sync every visit, harmless upsert */
    }
    void syncProfile({
      email: user.primaryEmailAddress?.emailAddress ?? undefined,
      full_name: user.fullName ?? undefined,
      avatar_url: user.imageUrl ?? undefined,
    })
  }, [isLoaded, user])

  const requestUpgrade = useCallback(
    (reason?: 'limit' | 'feature') => setUpgrade({ open: true, reason }),
    [],
  )

  if (!isLoaded) {
    return (
      <div
        style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
        aria-busy="true"
      >
        <span className="label">{loadingLabel}</span>
      </div>
    )
  }

  const shell: TerminalShellContext = { isPro, usedToday, requestUpgrade }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <TerminalHeader
        macro={macro}
        isPro={isPro}
        usedToday={usedToday}
        onUpgrade={() => setUpgrade({ open: true })}
      />
      <UpgradeDialog
        open={upgrade.open}
        reason={upgrade.reason}
        onClose={() => setUpgrade({ open: false })}
      />
      <CommandPalette />

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
        {typeof children === 'function' ? children(shell) : children}
      </main>
    </div>
  )
}
