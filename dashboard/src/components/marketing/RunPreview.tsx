'use client'

import { Diverging } from '@/components/company/Panels'
import { SignalGrid } from '@/components/company/SignalState'
import { factorName } from '@/components/company/derive'
import CompanyMark from '@/components/ui/CompanyMark'

import { RECORDED_LABEL, recordedAnalysis as a } from './recordedRun'

/**
 * The company workspace's opening screen, rendered by the product's own
 * components from a recorded run. Framed as a window and labelled as a
 * record so it is never mistaken for a live quote or a recommendation.
 */
export default function RunPreview() {
  const factors = [...(a.quant?.factors ?? [])]
    .sort((x, y) => Math.abs(y.contribution) - Math.abs(x.contribution))
    .slice(0, 5)

  return (
    <figure className="lp-window" aria-label="A recorded research run for Apple, as the terminal shows it">
      <div className="lp-window__bar" aria-hidden>
        <span className="lp-window__dots"><i /><i /><i /></span>
        <span className="lp-window__path">omnisignal · company · AAPL</span>
        <span className="lp-window__tag">recorded</span>
      </div>
      <div className="lp-window__body">
        <div className="lp-id" data-sector="technology">
          <CompanyMark ticker="AAPL" name="Apple Inc." size={42} />
          <div className="lp-id__text">
            <div className="lp-id__line">
              <span className="lp-id__sym">AAPL</span>
              <span className="lp-id__name">Apple Inc.</span>
            </div>
            <span className="lp-id__meta">NASDAQ · Technology · Consumer Electronics</span>
          </div>
          <div className="lp-id__px">
            <span className="sys-num">${a.consensusPrice?.consensus.toFixed(2)}</span>
            <span>price at the run</span>
          </div>
        </div>

        <section className="sig" aria-label="Deterministic output">
          <header className="sig-head">
            <span className="sig-head__k">System output</span>
            <span className="sig-head__note">
              Deterministic engine {a.quant?.modelVersion} · no model or LLM sets these values
            </span>
          </header>
          <SignalGrid a={a} />
        </section>

        <div className="lp-contrib">
          <p className="sys-label">Largest contributions to the composite</p>
          <ul>
            {factors.map((f) => (
              <li key={f.name}>
                <span className="lp-contrib__name">{factorName(f.name)}</span>
                <Diverging value={f.contribution} max={0.08} />
                <span className={`sys-num ${f.contribution >= 0 ? 'sys-pos' : 'sys-neg'}`}>
                  {f.contribution >= 0 ? '+' : ''}{f.contribution.toFixed(3)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <figcaption className="lp-window__cap">
        {RECORDED_LABEL}. Shown exactly as recorded — not live data and not a recommendation.
      </figcaption>
    </figure>
  )
}
