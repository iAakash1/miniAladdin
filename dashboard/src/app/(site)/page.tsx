import Link from 'next/link'
import type { Metadata } from 'next'

import { DeterministicConclusion } from '@/components/company/Conclusion'
import { FAMILY_LABEL, FAMILY_ORDER, factorName } from '@/components/company/derive'
import LiveMacro from '@/components/marketing/LiveMacro'
import PipelineFigure from '@/components/marketing/PipelineFigure'
import ProductTour from '@/components/marketing/ProductTour'
import RunPreview from '@/components/marketing/RunPreview'
import { RECORDED_LABEL, recordedAnalysis as run } from '@/components/marketing/recordedRun'
import MarketNews from '@/components/terminal/home/MarketNews'
import { FREE_DAILY_LIMIT } from '@/lib/usage'

export const metadata: Metadata = {
  // Inherits the root default title; the template would double the brand here.
  description:
    'Equity research you can audit: a deterministic engine sets every signal from evidence traced to its provider, and an explanation layer narrates it with citations.',
  alternates: { canonical: '/' },
}

/** What each family reads, in the words the methodology uses. */
const FAMILY_READS: Record<string, string> = {
  momentum: 'Trend persistence across one to twelve months, confirmed by volume and measured against the market.',
  fundamental: 'What the price pays for earnings, against the sector and the street, and the drift after results.',
  quality: 'How profitably assets are used, and whether the share count and balance sheet are being diluted.',
  news: 'The tone of recent company headlines, weighted up around earnings.',
  reversal: 'Short-term overextension that tends to mean-revert, as a small contrarian counterweight.',
}

const FAQ = [
  {
    q: 'Does an AI decide the signal?',
    a: 'No. The signal, confidence and risk level come from a deterministic engine — the same inputs always give the same output. A language model writes the explanation afterwards; it must cite the evidence items it uses, and any section that cites nothing, or quotes a number the evidence does not contain, is withheld. The page says which sections were withheld and which provider and model wrote the rest.',
  },
  {
    q: 'Where does the data come from?',
    a: 'Prices, fundamentals and news come from the market-data vendors configured for the deployment; filings come from SEC EDGAR and macro series from FRED. Every run lists which providers answered, which failed and which inputs are missing. A missing input is never filled with an estimate, and a single source is never presented as agreement.',
  },
  {
    q: 'Is this investment advice?',
    a: 'No. OmniSignal is a research and education tool. It summarises public data into a structured, repeatable readout; it does not know your situation, and a signal is a summary of evidence, not a recommendation. Decisions and their consequences remain yours.',
  },
  {
    q: 'Is Pro a subscription?',
    a: 'No. Pro is a single ₹100 payment through Razorpay that unlocks the paid features on your account. There is no recurring charge and nothing to cancel.',
  },
]

export default function LandingPage() {
  const q = run.quant
  const byFamily = (family: string) => (q?.factors ?? []).filter((f) => f.family === family).map((f) => factorName(f.name))

  return (
    <div className="lp">
      {/* ── hero ─────────────────────────────────────────────────────── */}
      <section className="lp-hero">
        <div className="lp-container lp-hero__grid">
          <div className="lp-hero__copy">
            <p className="lp-eyebrow">Evidence-grounded equity research</p>
            <h1 className="lp-title">Research you can audit, <em>line by line.</em></h1>
            <p className="lp-lede">
              A deterministic engine sets every signal from evidence it can trace to a provider.
              Disagreements and gaps stay visible. An explanation layer then narrates the result — and
              has to cite the evidence for every sentence it keeps.
            </p>
            <div className="lp-cta">
              <Link href="/start" prefetch={false} className="lp-btn lp-btn--primary">Open the terminal</Link>
              <Link href="/#how" className="lp-btn">How a signal is made</Link>
            </div>
            <p className="lp-fine">Free: {FREE_DAILY_LIMIT} research runs a day, no card required.</p>
          </div>
          <RunPreview />
        </div>
      </section>

      <LiveMacro />

      {/* ── how ──────────────────────────────────────────────────────── */}
      <section id="how" className="lp-section">
        <div className="lp-container">
          <header className="lp-section__head">
            <p className="lp-eyebrow">How a run is assembled</p>
            <h2 className="lp-h2">The signal is fixed before a word is written</h2>
            <p className="lp-section__lede">
              Four stages, always in this order. The explanation layer reads the engine’s output; nothing
              it writes can change it.
            </p>
          </header>
          <PipelineFigure />
        </div>
      </section>

      {/* ── product ──────────────────────────────────────────────────── */}
      <section id="product" className="lp-section lp-section--panel">
        <div className="lp-container">
          <header className="lp-section__head">
            <p className="lp-eyebrow">The company workspace</p>
            <h2 className="lp-h2">One company, every layer of the evidence</h2>
            <p className="lp-section__lede">
              These are the terminal’s own panels, rendered from one recorded production run — not a mock-up.
            </p>
          </header>
          <ProductTour />
        </div>
      </section>

      {/* ── methodology ──────────────────────────────────────────────── */}
      <section id="methodology" className="lp-section">
        <div className="lp-container lp-method">
          <header className="lp-section__head">
            <p className="lp-eyebrow">Methodology · {q?.modelVersion}</p>
            <h2 className="lp-h2">Five families, one composite, a gated sleeve</h2>
            <p className="lp-section__lede">
              Each factor is normalised with outlier-resistant statistics against the company’s own history
              and volatility, then weighted into its family; the families are weighted into one composite.
              Macro stress scales only the momentum sleeve — value, quality and news are never
              macro-suppressed — and in high-volatility regimes momentum is halved in favour of reversal.
            </p>
          </header>

          <div className="lp-method__grid">
            <div className="lp-families">
              {FAMILY_ORDER.map((f) => {
                const w = q?.weightsUsed[f]
                return (
                  <div key={f} className="lp-family">
                    <div className="lp-family__head">
                      <span className="lp-family__name">{FAMILY_LABEL[f]}</span>
                      <span className="lp-family__w sys-num">{w === undefined ? '—' : `${Math.round(w * 100)}%`}</span>
                    </div>
                    <span className="lp-family__bar" aria-hidden><span style={{ width: `${(w ?? 0) * 100 * 2.5}%` }} /></span>
                    <p>{FAMILY_READS[f]}</p>
                    <p className="lp-family__factors">{byFamily(f).join(' · ')}</p>
                  </div>
                )
              })}
              <p className="lp-note">Weights and factors as used in the recorded run. The momentum gate there was ×{q?.macroGate.toFixed(2)}.</p>
            </div>
            <div className="lp-method__side">
              <div className="sys-panel">
                <header className="sys-panel-head">
                  <div className="sys-panel-head__title">
                    <h3 className="sys-panel-title">Confidence and risk, itemised</h3>
                    <span className="sys-panel-sub">{RECORDED_LABEL}</span>
                  </div>
                </header>
                <div className="sys-panel-body lp-conclusion">
                  <DeterministicConclusion a={run} />
                </div>
              </div>
              <ul className="lp-rules">
                <li><b>Unknown is not zero.</b> A factor that could not be computed is reported as missing and costs confidence.</li>
                <li><b>One source is not agreement.</b> Readings from a single vendor are labelled single-source.</li>
                <li><b>Disagreement is shown, not averaged.</b> Conflicting vendor figures appear side by side.</li>
                <li><b>Stale is not current.</b> Every observation carries its own date.</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* ── news ─────────────────────────────────────────────────────── */}
      <section id="news" className="lp-section lp-section--panel">
        <div className="lp-container">
          <header className="lp-section__head">
            <p className="lp-eyebrow">Live</p>
            <h2 className="lp-h2">Market news, with its sources</h2>
          </header>
          <MarketNews count={5} />
        </div>
      </section>

      {/* ── pricing ──────────────────────────────────────────────────── */}
      <section id="pricing" className="lp-section">
        <div className="lp-container">
          <header className="lp-section__head">
            <p className="lp-eyebrow">Pricing</p>
            <h2 className="lp-h2">Free to use daily. Pro when you need depth.</h2>
          </header>
          <div className="lp-plans">
            <div className="lp-plan">
              <p className="lp-plan__name">Free</p>
              <p className="lp-plan__price"><span className="sys-num">₹0</span></p>
              <ul>
                <li>{FREE_DAILY_LIMIT} research runs a day</li>
                <li>Full signal, evidence record and synthesis</li>
                <li>Three-month price charts</li>
                <li>Live macro conditions</li>
                <li>Headlines, without article links</li>
              </ul>
              <Link href="/sign-up" className="lp-btn">Start free</Link>
            </div>
            <div className="lp-plan lp-plan--pro">
              <p className="lp-plan__name">Pro</p>
              <p className="lp-plan__price"><span className="sys-num">₹100</span><small>one-time</small></p>
              <ul>
                <li>Unlimited research runs</li>
                <li>Every chart window, one month to five years</li>
                <li>Full article access from the news evidence</li>
                <li>Everything in Free</li>
              </ul>
              <Link href="/start" prefetch={false} className="lp-btn lp-btn--primary">Go Pro in the terminal</Link>
            </div>
          </div>
          <p className="lp-note lp-note--center">Payments through Razorpay. One payment, no renewal.</p>
        </div>
      </section>

      {/* ── faq ──────────────────────────────────────────────────────── */}
      <section className="lp-section lp-section--panel">
        <div className="lp-container lp-faq">
          <h2 className="lp-h2">Questions</h2>
          {FAQ.map((item) => (
            <details key={item.q} className="lp-faq__item">
              <summary>{item.q}</summary>
              <p>{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="lp-section lp-final">
        <div className="lp-container lp-final__inner">
          <h2 className="lp-h2">Open a company. Read the evidence.</h2>
          <Link href="/start" prefetch={false} className="lp-btn lp-btn--primary">Open the terminal</Link>
        </div>
      </section>
    </div>
  )
}
