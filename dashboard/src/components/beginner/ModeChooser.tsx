'use client'

/**
 * How a first-time reader picks their experience.
 *
 * Shown only when the backend reports `experience_mode_chosen: false`. That
 * flag is separate from the mode itself for a reason: "never asked" and
 * "asked, answered advanced" both resolve to advanced, and only the first
 * should produce a prompt. Keying off the mode alone would re-ask every
 * advanced user on every visit.
 *
 * Neither option is a tier and neither is a role. The same analysis, the same
 * verdict and the same permissions sit behind both — only the density of what
 * is drawn differs, which is why the copy describes presentation rather than
 * capability.
 */

import { useRouter } from 'next/navigation'
import { useState } from 'react'

import { Panel, Prose } from '@/components/system'
import { type ExperienceMode, setExperienceMode } from '@/lib/capabilities'

export default function ModeChooser({ onChosen }: { onChosen?: (m: ExperienceMode) => void }) {
  const router = useRouter()
  const [saving, setSaving] = useState<ExperienceMode | null>(null)
  const [failed, setFailed] = useState(false)

  async function choose(mode: ExperienceMode) {
    setSaving(mode)
    setFailed(false)
    const ok = await setExperienceMode(mode)
    setSaving(null)
    if (!ok) {
      // Not navigated. Sending the reader into a mode the server did not
      // record would strand them there and re-prompt on the next load.
      setFailed(true)
      return
    }
    onChosen?.(mode)
    router.push(mode === 'beginner' ? '/beginner' : '/terminal')
  }

  return (
    <Panel title="Choose your experience">
      <Prose>How would you like OmniSignal to explain markets?</Prose>

      <div className="bg__modes">
        <button
          type="button"
          className="bg__mode"
          onClick={() => void choose('beginner')}
          disabled={saving !== null}
        >
          <span className="bg__mode-title">Beginner</span>
          <span className="bg__mode-body">
            Simple signals, plain-language explanations, risk, and curated
            market ideas.
          </span>
          <span className="bg__mode-cta">
            {saving === 'beginner' ? 'Saving…' : 'Start with Beginner'}
          </span>
        </button>

        <button
          type="button"
          className="bg__mode"
          onClick={() => void choose('advanced')}
          disabled={saving !== null}
        >
          <span className="bg__mode-title">Advanced</span>
          <span className="bg__mode-body">
            The full quantitative research terminal: factors, provenance,
            financial statements and professional analytics.
          </span>
          <span className="bg__mode-cta">
            {saving === 'advanced' ? 'Saving…' : 'Start with Advanced'}
          </span>
        </button>
      </div>

      {failed ? (
        <Prose>
          That preference could not be saved, so nothing was changed. Check
          your connection and try again.
        </Prose>
      ) : null}

      <Prose>You can change this at any time.</Prose>
    </Panel>
  )
}
