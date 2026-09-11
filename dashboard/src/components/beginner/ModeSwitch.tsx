'use client'

/**
 * Move between the two experiences.
 *
 * Persists the choice before navigating, so the mode survives the next visit
 * rather than lasting until the tab closes. If the write fails the reader is
 * not moved: landing in a mode the server did not record would silently
 * revert on reload.
 */

import { useRouter } from 'next/navigation'
import { useState } from 'react'

import { type ExperienceMode, setExperienceMode } from '@/lib/capabilities'

export default function ModeSwitch({ to }: { to: ExperienceMode }) {
  const router = useRouter()
  const [busy, setBusy] = useState(false)

  async function go() {
    setBusy(true)
    const ok = await setExperienceMode(to)
    setBusy(false)
    if (ok) router.push(to === 'beginner' ? '/beginner' : '/terminal')
  }

  return (
    <button type="button" className="bg__switch" onClick={() => void go()} disabled={busy}>
      {busy ? 'Switching…' : to === 'advanced' ? 'Switch to Advanced' : 'Switch to Beginner'}
    </button>
  )
}
