'use client'

/*
 * What this account may do, and how it has asked to be shown things.
 *
 * Read once and shared, because navigation asks the same question from
 * several places and each answer costs a verified round trip.
 *
 * This is presentation state. It decides which links are drawn, never what
 * the caller may reach: the backend re-checks every permission on every
 * request, so a browser that lies to itself about this payload gains
 * nothing but a link that 403s.
 */

import { useEffect, useState } from 'react'

import { authFetch } from '@/lib/persistence'

export type Role = 'user' | 'admin'
export type ExperienceMode = 'beginner' | 'advanced'

export interface Capabilities {
  role: Role
  permissions: string[]
  experience_mode: ExperienceMode
  /** False when the user has never chosen — what onboarding keys off.
   *  Distinct from the mode itself: "never asked" and "answered advanced"
   *  produce the same mode and must not produce the same first run. */
  experience_mode_chosen: boolean
  /** null means the backend cannot say, not that the account is free. */
  is_pro: boolean | null
}

/** The shape used before the real answer arrives, and if it never does.
 *  Advanced and unprivileged: the safe direction on both axes. */
export const FALLBACK_CAPABILITIES: Capabilities = {
  role: 'user',
  permissions: [],
  experience_mode: 'advanced',
  experience_mode_chosen: true,
  is_pro: null,
}

export async function fetchCapabilities(): Promise<Capabilities | null> {
  try {
    const res = await authFetch('/api/me/capabilities')
    if (!res.ok) return null
    const body = (await res.json()) as Partial<Capabilities>
    const mode = body.experience_mode === 'beginner' ? 'beginner' : 'advanced'
    return {
      role: body.role === 'admin' ? 'admin' : 'user',
      permissions: Array.isArray(body.permissions) ? body.permissions : [],
      experience_mode: mode,
      experience_mode_chosen: body.experience_mode_chosen === true,
      is_pro: typeof body.is_pro === 'boolean' ? body.is_pro : null,
    }
  } catch {
    return null
  }
}

export async function setExperienceMode(mode: ExperienceMode): Promise<boolean> {
  try {
    const res = await authFetch('/api/preferences', {
      method: 'PATCH',
      body: JSON.stringify({ experience_mode: mode }),
    })
    return res.ok
  } catch {
    return false
  }
}

export function hasPermission(caps: Capabilities | null, permission: string): boolean {
  return caps?.permissions.includes(permission) ?? false
}

export interface CapabilitiesState {
  caps: Capabilities | null
  /** False until the first answer settles. Callers must not treat
   *  "still loading" as "not permitted" and flash a denied state. */
  resolved: boolean
  refresh: () => void
}

export function useCapabilities(): CapabilitiesState {
  const [caps, setCaps] = useState<Capabilities | null>(null)
  const [resolved, setResolved] = useState(false)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let live = true
    void fetchCapabilities().then((value) => {
      if (!live) return
      setCaps(value)
      setResolved(true)
    })
    return () => {
      live = false
    }
  }, [nonce])

  return { caps, resolved, refresh: () => setNonce((n) => n + 1) }
}
