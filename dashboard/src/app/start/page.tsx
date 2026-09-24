'use client'

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'

import ExperienceChooser from '@/components/beginner/ExperienceChooser'
import { experienceHome, useCapabilities } from '@/lib/capabilities'

/**
 * Short transition between the public site and the product.
 *
 * This intentionally makes no fake percentage/progress claim. We only know
 * that account/workspace state is being resolved, so the animation communicates
 * activity rather than invented completion.
 */
function TerminalBoot({
  label,
  detail,
}: {
  label: string
  detail: string
}) {
  return (
    <main
      className="terminal-boot"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="terminal-boot__panel">
        <div className="terminal-boot__brand">
          <span className="terminal-boot__mark" aria-hidden>
            <span />
            <span />
            <span />
          </span>

          <span>OmniSignal</span>
        </div>

        <div className="terminal-boot__copy">
          <strong>{label}</strong>
          <span>{detail}</span>
        </div>

        <div className="terminal-boot__rail" aria-hidden>
          <span />
        </div>
      </div>
    </main>
  )
}

/**
 * Where a signed-in reader arrives.
 *
 * Three outcomes:
 * - first visit -> experience selector
 * - known mode -> that workspace
 * - unavailable preference service -> advanced terminal fallback
 */
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

    router.replace(experienceHome(caps.experience_mode))
  }, [caps, resolved, router])

  if (!resolved) {
    return (
      <TerminalBoot
        label="Opening terminal"
        detail="Checking your session and workspace"
      />
    )
  }

  if (caps && !caps.experience_mode_chosen) {
    return <ExperienceChooser />
  }

  return (
    <TerminalBoot
      label="Opening terminal"
      detail="Restoring your workspace"
    />
  )
}