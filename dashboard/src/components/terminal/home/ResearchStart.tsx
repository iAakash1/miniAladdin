'use client'

import { Shortcut } from '@/components/system/Shortcut'
import Link from 'next/link'
import { useSyncExternalStore } from 'react'

import Icon from '@/components/shell/Icon'
import { openPalette } from '@/components/system/Palette'
import CompanyMark from '@/components/ui/CompanyMark'
import { emptySnapshot, recentSnapshot, subscribeSymbols } from '@/lib/symbols'

/* Shortcuts only — large, liquid names across sectors so a first visit has
   somewhere to start. No data is claimed about them here. */
const STARTERS = ['AAPL', 'NVDA', 'MSFT', 'JPM', 'XOM', 'LLY', 'AMZN', 'COST']

export default function ResearchStart() {
  const recent = useSyncExternalStore(subscribeSymbols, recentSnapshot, emptySnapshot)
  const picks = [...recent.slice(0, 4), ...STARTERS.filter((s) => !recent.includes(s))].slice(0, 8)

  return (
    <section className="hs" aria-labelledby="hs-title">
      <h2 className="hs-title" id="hs-title">Research a company</h2>
      <p className="hs-lede">
        One run asks every configured provider, reconciles what they report and returns a
        deterministic verdict with its evidence.
      </p>
      <button type="button" className="hs-search" onClick={() => openPalette()} aria-keyshortcuts="Control+K Meta+K">
        <Icon name="search" size={16} />
        <span>Ticker, company or theme — “AAPL”, “semiconductor equipment”</span>
        <kbd><Shortcut k="K" /></kbd>
      </button>
      <div className="hs-picks" role="group" aria-label={recent.length ? 'Recent and suggested companies' : 'Suggested companies'}>
        <span className="hs-picks__k">{recent.length ? 'Recent' : 'Start with'}</span>
        {picks.map((s) => (
          <Link key={s} href={`/company/${encodeURIComponent(s)}`} className="hs-pick">
            <CompanyMark ticker={s} size={16} />
            <span>{s}</span>
          </Link>
        ))}
      </div>
    </section>
  )
}
