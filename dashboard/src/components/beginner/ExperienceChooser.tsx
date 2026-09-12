'use client'

/**
 * The first screen a new account sees.
 *
 * Before this existed, a first-time user landed in the research terminal —
 * twenty-eight destinations, covariance matrices, calibration gates — which
 * is the right product for someone who came for it and the wrong one for
 * everybody else.
 *
 * The question is about how much detail the reader wants, not about how much
 * they know. Someone can understand markets perfectly well and still want the
 * short version, so the copy asks about detail and never labels the person.
 * The internal enum stays BEGINNER/ADVANCED because that is what the API and
 * the database call it.
 *
 * This is presentation only. Whichever is chosen, the same engine produces the
 * same verdict, the same confidence and the same risk for the same evidence —
 * the choice decides how much of that working is drawn.
 */

import { useRouter } from 'next/navigation'
import { useState } from 'react'

import { type ExperienceMode, setExperienceMode } from '@/lib/capabilities'

const OPTIONS: Array<{
  mode: ExperienceMode
  name: string
  tagline: string
  body: string
  points: string[]
  cta: string
}> = [
  {
    mode: 'beginner',
    name: 'Simple',
    tagline: 'Just show me what matters.',
    body:
      'Clear model signals, risk explained in plain language, and the strongest '
      + 'current ideas — without the quantitative machinery underneath.',
    points: [
      'Buy / Hold / Sell, stated plainly',
      'Risk and confidence explained in a sentence',
      'Why the model likes it, and what makes it cautious',
      'Top Ranked Ideas and Trending',
      'Guided Explore by theme',
      'How complete and fresh the evidence is',
    ],
    cta: 'Use Simple Mode',
  },
  {
    mode: 'advanced',
    name: 'Advanced',
    tagline: 'Show me the full research.',
    body:
      'The complete quantitative terminal: factor decomposition, risk '
      + 'analytics, provenance, evidence validation and model diagnostics.',
    points: [
      'Full factor decomposition and contributions',
      'Risk decomposition and macro regime gating',
      'Financial statements and reconciled fundamentals',
      'Evidence provenance and claim validation',
      'Agent pipeline and run traces',
      'Portfolio analytics, experiments and registries',
    ],
    cta: 'Use Advanced Mode',
  },
]

export default function ExperienceChooser({ onChosen }: { onChosen?: () => void }) {
  const router = useRouter()
  const [saving, setSaving] = useState<ExperienceMode | null>(null)
  const [failed, setFailed] = useState(false)

  async function choose(mode: ExperienceMode) {
    setSaving(mode)
    setFailed(false)
    const ok = await setExperienceMode(mode)
    setSaving(null)
    if (!ok) {
      // Deliberately not navigated. Sending someone into a mode the server did
      // not record strands them there and re-prompts on the next load.
      setFailed(true)
      return
    }
    onChosen?.()
    router.push(mode === 'beginner' ? '/beginner' : '/terminal/command')
  }

  return (
    <main className="xc">
      <div className="xc__inner">
        <p className="xc__brand">OMNISIGNAL</p>
        <h1 className="xc__title">How much detail would you like to see?</h1>
        <p className="xc__sub">
          Both give you the same analysis. They differ in how much of the working
          is shown.
        </p>

        <div className="xc__grid">
          {OPTIONS.map((option) => (
            <section key={option.mode} className="xc__card">
              <h2 className="xc__name">{option.name}</h2>
              <p className="xc__tagline">{option.tagline}</p>
              <p className="xc__body">{option.body}</p>
              <ul className="xc__points">
                {option.points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
              <button
                type="button"
                className="xc__cta"
                onClick={() => void choose(option.mode)}
                disabled={saving !== null}
              >
                {saving === option.mode ? 'Saving…' : option.cta}
              </button>
            </section>
          ))}
        </div>

        {failed ? (
          <p className="xc__error" role="alert">
            That preference could not be saved, so nothing was changed. Check your
            connection and try again.
          </p>
        ) : null}

        <p className="xc__note">You can change this at any time.</p>
      </div>
    </main>
  )
}
