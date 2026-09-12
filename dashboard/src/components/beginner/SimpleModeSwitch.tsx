'use client'

/**
 * The route back to Simple mode, in the terminal chrome.
 *
 * Persisted before navigating, so the choice survives the next visit rather
 * than lasting until the tab closes. A failed write does not navigate: landing
 * in a mode the server did not record silently reverts on reload, which reads
 * as the product ignoring you.
 */

import { useRouter } from 'next/navigation'
import { useState } from 'react'

import { setExperienceMode } from '@/lib/capabilities'

export default function SimpleModeSwitch() {
  const router = useRouter()
  const [busy, setBusy] = useState(false)

  async function go() {
    setBusy(true)
    const ok = await setExperienceMode('beginner')
    setBusy(false)
    if (ok) router.push('/beginner')
  }

  return (
    <button
      type="button"
      className="sys-btn"
      onClick={() => void go()}
      disabled={busy}
      title="Switch to the simplified experience"
    >
      {busy ? 'switching…' : 'simple mode'}
    </button>
  )
}
