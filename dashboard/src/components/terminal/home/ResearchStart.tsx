'use client'

import Link from 'next/link'
import { useSyncExternalStore } from 'react'

import Icon from '@/components/shell/Icon'
import { openPalette } from '@/components/system/Palette'
import CompanyMark from '@/components/ui/CompanyMark'
import { emptySnapshot, recentSnapshot, subscribeSymbols } from '@/lib/symbols'

/* Shortcuts only — large, liquid names across sectors so a first visit has
   somewhere to start. No data is claimed about them here. */
const STARTERS = ['AAPL', 'NVDA', 'MSFT', 'JPM', 'XOM', 'LLY', 'AMZN', 'COST']

const STEPS = [
  { k: 'Providers', v: 'every configured vendor answers in parallel' },
  { k: 'Evidence', v: 'readings reconciled, disagreement kept' },
  { k: 'Engine', v: 'deterministic signal, confidence, risk' },
  { k: 'Synthesis', v: 'grounded explanation, validated citations' },
]

export default function ResearchStart() {
  const recent = useSyncExternalStore(subscribeSymbols, recentSnapshot, emptySnapshot)
  const picks = [...recent.slice(0, 4), ...STARTERS.filter((s) => !recent.includes(s))].slice(0, 8)

  return (
    <section className="hs" aria-label="Start research">
      <div className="hs-main">
        <p className="sys-label">Research a company</p>
        <button type="button" className="hs-search" onClick={() => openPalette()}>
          <Icon name="search" size={16} />
          <span>Search by ticker, company or theme — “semiconductor equipment”, “AAPL”</span>
          <kbd>⌘K</kbd>
        </button>
        <div className="hs-picks" aria-label={recent.length ? 'Recent and suggested companies' : 'Suggested companies'}>
          {picks.map((s) => (
            <Link key={s} href={`/company/${encodeURIComponent(s)}`} className="hs-pick">
              <CompanyMark ticker={s} size={18} />
              <span>{s}</span>
            </Link>
          ))}
        </div>
      </div>
      <ol className="hs-flow" aria-label="How a research run is built">
        {STEPS.map((s, i) => (
          <li key={s.k} className="hs-step">
            <span className="hs-step__n">{i + 1}</span>
            <span className="hs-step__k">{s.k}</span>
            <span className="hs-step__v">{s.v}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}
