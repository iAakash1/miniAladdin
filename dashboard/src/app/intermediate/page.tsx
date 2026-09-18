'use client'

import { useRouter } from 'next/navigation'
import { useState } from 'react'

import PerformanceLeaders from '@/components/beginner/PerformanceLeaders'
import TopIdeas from '@/components/beginner/TopIdeas'
import TrendingNow from '@/components/beginner/TrendingNow'
import IntermediateShell from '@/components/intermediate/IntermediateShell'
import MarketBand from '@/components/terminal/home/MarketBand'
import { Panel, Prose } from '@/components/system'

export default function IntermediateHome() {
  const router = useRouter()
  const [symbol, setSymbol] = useState('')

  function search(event: React.FormEvent) {
    event.preventDefault()
    const clean = symbol.trim().toUpperCase()
    if (clean) router.push(`/intermediate/company/${encodeURIComponent(clean)}`)
  }

  return (
    <IntermediateShell title="OmniSignal" subtitle="signals, factors and evidence">
      <Panel title="Analyze a company">
        <form onSubmit={search} className="bg__search" role="search">
          <label htmlFor="int-symbol" className="visually-hidden">Ticker symbol</label>
          <input
            id="int-symbol"
            value={symbol}
            onChange={(event) => setSymbol(event.target.value)}
            placeholder="Ticker, e.g. MSFT"
            autoComplete="off"
            spellCheck={false}
          />
          <button type="submit">Analyze</button>
        </form>
        <Prose>One scorecard, with factor contributions, validation and traceable evidence.</Prose>
      </Panel>
      <MarketBand />
      <TopIdeas limit={6} mode="intermediate" />
      <PerformanceLeaders limit={6} mode="intermediate" />
      <TrendingNow limit={6} mode="intermediate" />
    </IntermediateShell>
  )
}
