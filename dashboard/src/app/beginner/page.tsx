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

import Workbench from '@/components/system/Workbench'
import ModeChooser from '@/components/beginner/ModeChooser'
import ModeSwitch from '@/components/beginner/ModeSwitch'
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
  const { caps, resolved, refresh } = useCapabilities()
  const [symbol, setSymbol] = useState('')

  function search(e: React.FormEvent) {
    e.preventDefault()
    const clean = symbol.trim().toUpperCase()
    if (clean) router.push(`/beginner/company/${encodeURIComponent(clean)}`)
  }

  // Only for a reader who has genuinely never chosen. `experience_mode_chosen`
  // is separate from the mode precisely so an advanced user is not re-asked.
  if (resolved && caps && !caps.experience_mode_chosen) {
    return (
      <Workbench title="Welcome" subtitle="choose how much detail you want">
        <ModeChooser onChosen={() => refresh()} />
      </Workbench>
    )
  }

  return (
    <Workbench
      title="OmniSignal"
      subtitle="what to look at, and why"
      rail={[{ label: 'Beginner', state: 'live', detail: 'same engine, less density' }]}
      context={
        <>
          <Panel title="What the signal is">
            <Prose>
              Every signal here comes from the same quantitative engine the
              full research terminal uses. It is a model output about a
              security, not advice about your money.
            </Prose>
          </Panel>
          <Panel title="What confidence is not">
            <Prose>
              Analysis confidence describes how complete and how consistent the
              evidence was. It is not the probability that a price will rise.
            </Prose>
          </Panel>
          <Panel title="Want the full detail?">
            <Prose>
              Advanced mode adds factor attribution, financial statements,
              provenance and the complete research terminal. Same conclusions,
              more of the working.
            </Prose>
            <ModeSwitch to="advanced" />
          </Panel>
        </>
      }
    >
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
    </Workbench>
  )
}
