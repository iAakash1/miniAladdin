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
import { useId, useState } from 'react'

import { experienceHome, type ExperienceMode, setExperienceMode } from '@/lib/capabilities'

export default function ModeSwitch({ to, compact = false }: { to: ExperienceMode; compact?: boolean }) {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  const messageId = useId()

  async function go() {
    setBusy(true)
    setFailed(false)
    const ok = await setExperienceMode(to)
    setBusy(false)
    if (ok) router.push(experienceHome(to))
    else setFailed(true)
  }

  const label = `Switch to ${to === 'beginner' ? 'Simple' : to[0].toUpperCase() + to.slice(1)}`
  return (
    <>
      <button type="button" className={compact ? 'sys-btn' : 'bg__switch'} onClick={() => void go()} disabled={busy} aria-describedby={failed ? messageId : undefined}>
        {busy ? 'Switching…' : label}
      </button>
      {/* Staying put without a word would read as a dead button. */}
      <span id={messageId} className={failed ? 'mode-switch__failed' : 'visually-hidden'} role="status">
        {failed ? 'The preference could not be saved, so the mode did not change. Try again.' : ''}
      </span>
    </>
  )
}
