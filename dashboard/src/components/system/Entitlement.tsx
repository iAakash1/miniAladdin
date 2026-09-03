'use client'

/**
 * Who the reader is, what they have used today, and how to ask for more.
 *
 * These three facts used to live inside the old terminal shell, which is why
 * the one route that needed them could not move to the workbench: porting the
 * page meant either losing the session gate or duplicating it. Neither is
 * acceptable, so the concern is extracted instead.
 *
 * It carries only what genuinely depends on the session:
 *
 *  - the gate that waits for the identity provider to resolve, so a page never
 *    renders a free-tier state to a paying reader for a frame and then flips
 *  - the profile sync that runs once per browser session on first login
 *  - the upgrade dialog, which any workspace can open
 *  - notifications
 *
 * Everything else the old shell carried — header, navigation, keyboard,
 * palette — already exists once in the workbench, and is deliberately not
 * recreated here.
 *
 * The gate is not a spinner over the whole application. A workspace that does
 * not read entitlement renders immediately; only a consumer of `useEntitlement`
 * sees `resolved: false`, and it is that consumer's job to say so honestly
 * rather than guess.
 */

import { useUser } from '@clerk/nextjs'
import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
  type ReactNode,
} from 'react'

import Toasts from '@/components/ui/Toasts'
import UpgradeDialog from '@/components/terminal/UpgradeDialog'
import { syncProfile } from '@/lib/persistence'
import { useTodayCount } from '@/lib/usage'

export interface EntitlementValue {
  /**
   * False while the identity provider is still resolving. A consumer must not
   * treat this as "not pro" — unknown and no are different answers, and
   * rendering the second for the first is how a paying reader gets shown an
   * upgrade prompt.
   */
  resolved: boolean
  isPro: boolean
  /** Analyses run today, from local usage accounting. */
  usedToday: number
  requestUpgrade: (reason?: 'limit' | 'feature') => void
}

const Ctx = createContext<EntitlementValue | null>(null)

export function EntitlementProvider({ children }: { children: ReactNode }) {
  const { user, isLoaded } = useUser()
  const usedToday = useTodayCount()
  const [upgrade, setUpgrade] = useState<{ open: boolean; reason?: 'limit' | 'feature' }>({ open: false })

  const isPro = (user?.publicMetadata?.isPro as boolean) ?? false

  // Best-effort, once per browser session. A failure here changes nothing the
  // reader can see, so it is not surfaced.
  useEffect(() => {
    if (!isLoaded || !user) return
    try {
      if (sessionStorage.getItem('omni-profile-synced')) return
      sessionStorage.setItem('omni-profile-synced', '1')
    } catch {
      /* private mode: sync every visit, which is a harmless upsert */
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

  const value = useMemo<EntitlementValue>(
    () => ({ resolved: isLoaded, isPro, usedToday, requestUpgrade }),
    [isLoaded, isPro, usedToday, requestUpgrade],
  )

  return (
    <Ctx.Provider value={value}>
      <Toasts />
      <UpgradeDialog
        open={upgrade.open}
        reason={upgrade.reason}
        onClose={() => setUpgrade({ open: false })}
      />
      {children}
    </Ctx.Provider>
  )
}

/**
 * Outside a provider this reports unresolved rather than throwing. A workspace
 * rendered in isolation — a test, a story — should not crash, and reporting
 * `resolved: false` is the honest description of a page that cannot see a
 * session at all.
 */
export function useEntitlement(): EntitlementValue {
  return useContext(Ctx) ?? {
    resolved: false,
    isPro: false,
    usedToday: 0,
    requestUpgrade: () => {},
  }
}
