'use client'

/**
 * Where a signed-in reader arrives.
 *
 * Three outcomes, decided by what the backend says about this account:
 *
 *   never chosen      -> the experience selector
 *   chose simple      -> the Beginner home
 *   chose advanced    -> the research terminal
 *
 * Routing on `experience_mode_chosen` rather than on the mode itself is the
 * whole point. Both resolve to advanced when unset, and only one of them
 * means "we have never asked" — keying off the mode would either re-prompt
 * every advanced user forever or never prompt anyone.
 *
 * An unreachable backend sends the reader to the terminal rather than holding
 * them on a spinner. That is the pre-existing behaviour and the safe default:
 * being unable to read a preference is not a reason to refuse to render the
 * product.
 */

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'

import ExperienceChooser from '@/components/beginner/ExperienceChooser'
import { useCapabilities } from '@/lib/capabilities'

export default function StartPage() {
  const router = useRouter()
  const { caps, resolved } = useCapabilities()

  useEffect(() => {
    if (!resolved) return
    if (!caps) {
      router.replace('/terminal/command')
      return
    }
    if (!caps.experience_mode_chosen) return
    router.replace(caps.experience_mode === 'beginner' ? '/beginner' : '/terminal/command')
  }, [caps, resolved, router])

  if (!resolved) {
    return (
      <main className="xc">
        <div className="xc__inner">
          <p className="xc__brand">OMNISIGNAL</p>
          <p className="xc__sub">Loading your workspace…</p>
        </div>
      </main>
    )
  }

  if (caps && !caps.experience_mode_chosen) {
    return <ExperienceChooser />
  }

  // Redirecting. Rendered rather than left blank so a slow route change does
  // not look like a broken page.
  return (
    <main className="xc">
      <div className="xc__inner">
        <p className="xc__brand">OMNISIGNAL</p>
        <p className="xc__sub">Opening your workspace…</p>
      </div>
    </main>
  )
}
