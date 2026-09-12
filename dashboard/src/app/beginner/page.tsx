'use client'

/**
 * The Beginner home.
 *
 * Answers "what should I look at, and why" rather than showing every
 * institutional metric at once. Everything on it is the same data the
 * terminal serves — the same snapshot, the same scorecard, the same verdicts.
 * What differs is how much is drawn and how much of it is explained.
 */

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'

import SimpleShell from '@/components/beginner/SimpleShell'
import TopIdeas from '@/components/beginner/TopIdeas'
import TrendingNow from '@/components/beginner/TrendingNow'
import { Panel, Prose, StateBlock } from '@/components/system'
import { useCapabilities } from '@/lib/capabilities'

const CATEGORIES: Array<{ key: string; label: string; blurb: string }> = [
  { key: 'momentum', label: 'Momentum', blurb: 'Securities the price trend is behind.' },
  { key: 'quality', label: 'Quality', blurb: 'Profitable, conservatively financed businesses.' },
  { key: 'value', label: 'Value', blurb: 'Cheaper against earnings and analyst targets.' },
  { key: 'low_risk', label: 'Low Risk', blurb: 'Least volatile, least market-sensitive.' },
  { key: 'news_buzz', label: 'News Buzz', blurb: 'Most written about — tone shown separately.' },
  { key: 'analyst_upside', label: 'Analyst Upside', blurb: 'Furthest below the mean analyst target.' },
]

export default function BeginnerHome() {
  const router = useRouter()
  const { caps, resolved } = useCapabilities()
  const [symbol, setSymbol] = useState('')

  function search(e: React.FormEvent) {
    e.preventDefault()
    const clean = symbol.trim().toUpperCase()
    if (clean) router.push(`/beginner/company/${encodeURIComponent(clean)}`)
  }

  // A reader who has never chosen is sent to the selector rather than shown a
  // second copy of it here. One onboarding surface, one place to change it.
  if (resolved && caps && !caps.experience_mode_chosen) {
    router.replace('/start')
    return null
  }

  return (
    <SimpleShell title="OmniSignal" subtitle="what to look at, and why">
      <Panel title="Look up a company">
        <form onSubmit={search} className="bg__search" role="search">
          <label htmlFor="bg-symbol" className="visually-hidden">
            Company or ticker symbol
          </label>
          <input
            id="bg-symbol"
            name="symbol"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            placeholder="Ticker, e.g. MSFT"
            autoComplete="off"
            spellCheck={false}
          />
          <button type="submit">Analyse</button>
        </form>
      </Panel>

      <TopIdeas limit={4} />
      <TrendingNow limit={5} />

      <Panel title="Explore by theme" subtitle="ranked across the universe">
        <Prose>
          Each of these orders the same universe on one stated dimension.
          Ranking high on one says nothing about the others.
        </Prose>
        <div className="bg__cats">
          {CATEGORIES.map((c) => (
            <Link key={c.key} href={`/explore?category=${c.key}`} className="bg__cat">
              <span className="bg__cat-title">{c.label}</span>
              <span className="bg__cat-blurb">{c.blurb}</span>
            </Link>
          ))}
        </div>
      </Panel>

      {resolved && !caps ? (
        <StateBlock
          state="unavailable"
          title="Signed-out view"
          detail="preferences and watchlists need a session"
        >
          <Prose>
            Rankings and analysis are shown to everyone. Saving a watchlist or
            a preference needs you to be signed in.
          </Prose>
        </StateBlock>
      ) : null}
    </SimpleShell>
  )
}
