'use client'

import { useState } from 'react'

import { Claims } from '@/components/company/Claims'
import { FactorTable } from '@/components/company/Conclusion'
import Filings from '@/components/company/Filings'
import { Drivers, EvidenceCondition } from '@/components/company/Panels'
import Synthesis from '@/components/company/Synthesis'

import { RECORDED_LABEL, recordedAnalysis as a } from './recordedRun'

const VIEWS = [
  {
    key: 'signal',
    label: 'Signal',
    title: 'The verdict, decomposed',
    lede: 'Five factor families, their weights, and every factor the engine computed — its value, its standardised score and what it contributed.',
  },
  {
    key: 'evidence',
    label: 'Evidence',
    title: 'Every figure keeps its readings',
    lede: 'Where vendors agree, disagree or only one answered, the claim says so. Missing inputs are named with the reason — never filled with a guess.',
  },
  {
    key: 'synthesis',
    label: 'Synthesis',
    title: 'An explanation layer that cites',
    lede: 'A language model narrates the engine’s output and must cite the evidence it uses. It never sets the signal. Sections that fail validation are withheld, and the page says which.',
  },
  {
    key: 'sources',
    label: 'Primary sources',
    title: 'Filings as documents',
    lede: 'SEC filings open at the source, and the company’s own tagged figures are compared year over year — primary sources, not a vendor’s reading of them.',
  },
] as const

type View = (typeof VIEWS)[number]['key']

/** The workspace's main panels, rendered from the same recorded run. */
export default function ProductTour() {
  const [view, setView] = useState<View>('signal')
  const current = VIEWS.find((v) => v.key === view) ?? VIEWS[0]

  return (
    <div className="lp-tour">
      <div className="lp-tour__tabs" role="tablist" aria-label="Product views">
        {VIEWS.map((v) => (
          <button
            key={v.key}
            type="button"
            role="tab"
            id={`tour-${v.key}`}
            aria-selected={view === v.key}
            aria-controls="tour-panel"
            className="lp-tour__tab"
            onClick={() => setView(v.key)}
          >
            {v.label}
          </button>
        ))}
      </div>
      <div className="lp-tour__head">
        <h3>{current.title}</h3>
        <p>{current.lede}</p>
      </div>
      <div id="tour-panel" role="tabpanel" aria-labelledby={`tour-${view}`} className="lp-tour__panel">
        {view === 'signal' ? (
          <div className="cw-grid cw-grid--side">
            <section className="sys-panel">
              <header className="sys-panel-head">
                <div className="sys-panel-head__title">
                  <h2 className="sys-panel-title">Every factor</h2>
                  <span className="sys-panel-sub">value, standardised score and contribution to the composite</span>
                </div>
              </header>
              <div className="sys-panel-body sys-panel-body--flush">
                <FactorTable a={a} />
              </div>
            </section>
            <Drivers a={a} links={false} />
          </div>
        ) : null}
        {view === 'evidence' ? (
          <div className="cw-grid cw-grid--side">
            <Claims a={a} />
            <EvidenceCondition a={a} links={false} />
          </div>
        ) : null}
        {view === 'synthesis' ? (
          <Synthesis
            analysis={a}
            preview
            footer={<span>Hover a citation to see the evidence item it resolves to.</span>}
          />
        ) : null}
        {view === 'sources' && a.filings ? <Filings block={a.filings} recorded /> : null}
      </div>
      <p className="lp-tour__cap">{RECORDED_LABEL}. Rendered by the terminal’s own components.</p>
    </div>
  )
}
