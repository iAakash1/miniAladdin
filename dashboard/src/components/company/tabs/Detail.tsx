'use client'

import Link from 'next/link'

import ChartPanel from '../ChartPanel'
import Filings from '../Filings'
import MacroVisual from '../MacroVisual'
import News from '../News'
import Ownership from '../Ownership'
import CompanyEcosystem from '@/components/terminal/CompanyEcosystem'
import StreetIntelligence from '@/components/terminal/StreetIntelligence'
import TechnicalIntelligence from '@/components/terminal/TechnicalIntelligence'
import Financials from '@/components/terminal/security/Financials'
import Fundamentals2 from '@/components/terminal/security/Fundamentals2'
import MarketStats from '@/components/terminal/security/MarketStats'
import Options from '@/components/terminal/security/Options'
import Reported from '@/components/terminal/security/Reported'
import Street from '@/components/terminal/security/Street'
import type { Analysis } from '@/lib/types'

export function FinancialsTab({ symbol, analysis }: { symbol: string; analysis: Analysis | null }) {
  return (
    <div className="cw-stack">
      <p className="cw-lede">
        Filed facts come first and stay separate from vendor-computed figures: one is what the company
        reported to the SEC, the other is each vendor&apos;s own arithmetic.
      </p>
      <Financials symbol={symbol} />
      <div className="cw-grid cw-grid--2">
        <Fundamentals2 symbol={symbol} />
        <Street symbol={symbol} />
      </div>
      {analysis?.streetIntelligence && analysis.ownership ? (
        <div className="cw-grid cw-grid--side">
          <StreetIntelligence block={analysis.streetIntelligence} />
          <Ownership ownership={analysis.ownership} />
        </div>
      ) : (
        <>
          {analysis?.streetIntelligence ? <StreetIntelligence block={analysis.streetIntelligence} /> : null}
          {analysis?.ownership ? <Ownership ownership={analysis.ownership} /> : null}
        </>
      )}
      <Reported symbol={symbol} />
    </div>
  )
}

export function TechnicalsTab({ symbol, analysis, isPro, requestUpgrade }: {
  symbol: string
  analysis: Analysis | null
  isPro: boolean
  requestUpgrade: (reason?: 'limit' | 'feature') => void
}) {
  return (
    <div className="cw-stack">
      <ChartPanel symbol={symbol} isPro={isPro} requestUpgrade={requestUpgrade} height={380} title="Price and volume" />
      {analysis ? <TechnicalIntelligence block={analysis.technicalIntelligence} /> : null}
      <MarketStats symbol={symbol} />
    </div>
  )
}

export function MacroTab({ analysis: a }: { analysis: Analysis }) {
  return (
    <div className="cw-stack">
      <MacroVisual a={a} />
      <div className="cw-links">
        <Link className="sys-btn sys-btn--ghost" href="/terminal/market">Open Markets for the full macro board</Link>
      </div>
    </div>
  )
}

export function NewsTab({ analysis: a, isPro, requestUpgrade }: {
  analysis: Analysis
  isPro: boolean
  requestUpgrade: (reason?: 'limit' | 'feature') => void
}) {
  return (
    <div className="cw-stack">
      <News headlines={a.headlines} stream={a.newsStream} isPro={isPro} onUpgrade={() => requestUpgrade('feature')} />
    </div>
  )
}

export function FilingsTab({ analysis: a }: { analysis: Analysis }) {
  return a.filings && a.filings.filings.length ? (
    <Filings block={a.filings} />
  ) : (
    <section className="sys-panel">
      <div className="sys-state">
        <div className="sys-state__head"><span className="sys-status" data-state="unavailable">no filings</span><span className="sys-state__title">EDGAR returned no recent filings for {a.ticker}</span></div>
        <p className="sys-state__detail">Foreign private issuers and funds often file under different forms or not at all. Nothing is substituted.</p>
      </div>
    </section>
  )
}

export function RelationshipsTab({ symbol }: { symbol: string }) {
  return (
    <div className="cw-stack">
      <CompanyEcosystem ticker={symbol} />
      <div className="cw-links">
        <Link className="sys-btn" href={`/terminal/graph?symbols=${encodeURIComponent(symbol)}`}>Open in the knowledge graph</Link>
        <Link className="sys-btn sys-btn--ghost" href={`/terminal/graph/explore?node=${encodeURIComponent(`company:${symbol}`)}`}>Explore outward from {symbol}</Link>
      </div>
    </div>
  )
}

export function OptionsTab({ symbol, price }: { symbol: string; price: number | null }) {
  return (
    <div className="cw-stack">
      <Options symbol={symbol} underlyingPrice={price} />
    </div>
  )
}
