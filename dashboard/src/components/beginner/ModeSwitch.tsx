'use client'

/**
 * Move between the three experiences.
 *
 * Persists the choice before navigating, so the mode survives the next visit
 * rather than lasting until the tab closes. If the write fails the reader is
 * not moved: landing in a mode the server did not record would silently
 * revert on reload.
 */

import { useRouter } from 'next/navigation'
import { useState } from 'react'

import { experienceHome, type ExperienceMode, setExperienceMode } from '@/lib/capabilities'

export default function ModeSwitch({ to, compact = false }: { to: ExperienceMode; compact?: boolean }) {
  const router = useRouter()
  const [busy, setBusy] = useState(false)

  async function go() {
    setBusy(true)
    const ok = await setExperienceMode(to)
    setBusy(false)
    if (ok) router.push(experienceHome(to))
  }

  return (
    <button type="button" className={compact ? 'sys-btn' : 'bg__switch'} onClick={() => void go()} disabled={busy}>
      {busy ? 'Switching…' : `Switch to ${to === 'beginner' ? 'Simple' : to[0].toUpperCase() + to.slice(1)}`}
    </button>
  )
}
