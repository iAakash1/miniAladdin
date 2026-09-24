'use client'

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useEffect, useMemo, useRef, useState } from 'react'

import CompanyHeader from './CompanyHeader'
import { NarrativeProvider, useNarrative } from './Depth'
import SignalState from './SignalState'
import { signalTone } from './derive'
import { useIdentity, useResearch, type ResearchRun } from './useCompany'
import Evidence from './tabs/Evidence'
import Overview from './tabs/Overview'
import Report from './tabs/Report'
import {
  FilingsTab, FinancialsTab, MacroTab, NewsTab, OptionsTab, RelationshipsTab, TechnicalsTab,
} from './tabs/Detail'
import Drawer from '@/components/shell/Drawer'
import { useEntitlement } from '@/components/system/Entitlement'
import OrderTicket from '@/components/terminal/paper/OrderTicket'
import { companyHref } from '@/lib/context-commands'
import { fetchPaperStatus } from '@/lib/paper'
import { readResource } from '@/lib/resource'
import { workspaceRoot } from '@/lib/section-nav'
import { useQuotes } from '@/lib/use-quotes'

export const TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'report', label: 'Report' },
  { key: 'evidence', label: 'Evidence' },
  { key: 'financials', label: 'Financials' },
  { key: 'technicals', label: 'Technicals' },
  { key: 'macro', label: 'Macro' },
  { key: 'news', label: 'News' },
  { key: 'filings', label: 'Filings' },
  { key: 'relationships', label: 'Relationships' },
  { key: 'options', label: 'Options' },
] as const

export type TabKey = (typeof TABS)[number]['key']

export function tabFrom(value: string | null): TabKey {
  return TABS.some((t) => t.key === value) ? (value as TabKey) : 'overview'
}

/** Shown in a tab that needs the research run before it can render. */
function Awaiting({ run, what }: { run: ResearchRun; what: string }) {
  if (run.status === 'limited') {
    return <p className="cw-awaiting">The {what} needs a research run, and today&apos;s free runs are used. Price and history remain available on Overview and Technicals.</p>
  }
  if (run.status === 'error') {
    return <p className="cw-awaiting">The {what} is unavailable because the research run did not complete. Retry from the status above.</p>
  }
  return (
    <div className="sys-loading" role="status">
      <span className="sys-loading__line">Building the {what} from the research run</span>
      <span className="sys-skeleton" style={{ height: 8, width: '58%' }} />
      <span className="sys-skeleton" style={{ height: 8, width: '44%' }} />
    </div>
  )
}

export default function CompanyWorkspace({ ticker }: { ticker: string }) {
  const params = useSearchParams()
  const tab = tabFrom(params.get('tab'))
  const fast = params.get('fast') === '1'
  const { resolved, isPro, requestUpgrade } = useEntitlement()
  const { quotes, error: quoteError } = useQuotes([ticker])
  const quote = quotes[ticker] ?? null
  const identity = useIdentity(ticker)
  const { run, retry } = useResearch(ticker, { fast, resolved, isPro, onLimit: () => requestUpgrade('limit') })
  const researched = run.status === 'ready' ? run.analysis : null
  // The narrative at the reader's chosen depth. Only `ai` is swapped; every
  // deterministic field is the research run's own.
  const narrative = useNarrative(researched)
  const analysis = useMemo(
    () => (researched && narrative.ai !== researched.ai ? { ...researched, ai: narrative.ai } : researched),
    [researched, narrative.ai],
  )
  // Panels that read research themselves may mount only once the shared,
  // authenticated run is registered — never on a limited or failed run.
  const researchLive = run.status === 'running' || run.status === 'ready'

  const [paperConfigured, setPaperConfigured] = useState(false)
  const [paperOpen, setPaperOpen] = useState(params.get('paper') === '1')
  const [programme, setProgramme] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    fetchPaperStatus().then((s) => { if (alive) setPaperConfigured(Boolean(s.configured)) }).catch(() => {})
    return () => { alive = false }
  }, [])
  // The ticket snapshots the research programme's recorded verdict onto the
  // thesis, read from the selection artifact's own boolean: no verdict read
  // means no verdict recorded. Absent stays absent.
  useEffect(() => {
    if (!paperOpen) return undefined
    let alive = true
    readResource<{ verdict?: { passed?: boolean } }>('/api/quant/selection/EXP-007', 'artifact')
      .then((d) => {
        if (!alive || typeof d.verdict?.passed !== 'boolean') return
        setProgramme(d.verdict.passed ? 'EXP-007 · production candidate' : 'EXP-007 · no production candidate')
      })
      .catch(() => {})
    return () => { alive = false }
  }, [paperOpen])

  // A compact identity joins the sticky tab bar once the header scrolls away.
  const headRef = useRef<HTMLDivElement>(null)
  const [compact, setCompact] = useState(false)
  useEffect(() => {
    const root = workspaceRoot()
    const el = headRef.current
    if (!root || !el) return undefined
    const io = new IntersectionObserver(([entry]) => setCompact(!entry.isIntersecting), { root, threshold: 0 })
    io.observe(el)
    return () => io.disconnect()
  }, [])

  // Switching tabs keeps the tab bar in view rather than leaving the reader
  // halfway down the previous tab's content.
  const tabsRef = useRef<HTMLElement>(null)
  const firstTab = useRef(true)
  useEffect(() => {
    if (firstTab.current) { firstTab.current = false; return }
    const root = workspaceRoot()
    const bar = tabsRef.current
    if (!root || !bar) return
    const offset = bar.offsetTop
    if (root.scrollTop > offset) root.scrollTo({ top: offset })
  }, [tab])

  const profile = analysis?.profile
  const name = profile?.name ?? identity?.name ?? (analysis?.companyName !== ticker ? analysis?.companyName : null) ?? null
  const counts: Partial<Record<TabKey, number>> = analysis ? {
    news: analysis.headlines.length || undefined,
    filings: analysis.filings?.filings.length || undefined,
  } : {}
  const tone = analysis ? signalTone(analysis.riskAdjusted) : null

  return (
    <NarrativeProvider value={narrative.control}>
    <div className="cw">
      <div ref={headRef} className="cw-top">
        <CompanyHeader
          symbol={ticker}
          name={name}
          exchange={profile?.exchange ?? null}
          sector={profile?.sector ?? analysis?.sector ?? null}
          industry={profile?.industry && profile.industry !== profile.sector ? profile.industry : null}
          profile={profile}
          quote={quote}
          quoteError={quoteError}
          historyId={analysis?.historyId ?? null}
          onPaper={() => setPaperOpen(true)}
          paperAvailable={paperConfigured}
        />
        <SignalState run={run} onRetry={retry} onUpgrade={() => requestUpgrade('limit')} />
      </div>

      <nav ref={tabsRef} className="cw-tabs" aria-label={`${ticker} research sections`}>
        <div className="cw-tabs__id" data-visible={compact ? '' : undefined} aria-hidden={!compact}>
          <span className="cw-tabs__sym">{ticker}</span>
          {quote?.price !== null && quote?.price !== undefined ? <span className="sys-num">{quote.price.toFixed(2)}</span> : null}
          {analysis ? <span className="sig-verdict sig-verdict--sm" data-tone={tone ?? undefined}>{analysis.riskAdjusted}</span> : null}
        </div>
        <div className="cw-tabs__list">
          {TABS.map((t) => (
            <Link
              key={t.key}
              href={companyHref(ticker, t.key)}
              scroll={false}
              replace
              className="sys-tab"
              aria-current={tab === t.key ? 'page' : undefined}
            >
              {t.label}
              {counts[t.key] ? <span className="sys-tab__count">{counts[t.key]}</span> : null}
            </Link>
          ))}
        </div>
      </nav>

      <div className="cw-body" data-tab={tab}>
        {tab === 'overview' ? (
          <Overview symbol={ticker} analysis={analysis} isPro={isPro} requestUpgrade={requestUpgrade} />
        ) : null}
        {tab === 'report' ? (analysis ? <Report analysis={analysis} /> : <Awaiting run={run} what="report" />) : null}
        {tab === 'evidence' ? (analysis ? <Evidence analysis={analysis} /> : <Awaiting run={run} what="evidence record" />) : null}
        {tab === 'financials' ? (researchLive ? <FinancialsTab symbol={ticker} analysis={analysis} /> : <Awaiting run={run} what="financials" />) : null}
        {tab === 'technicals' ? (
          researchLive
            ? <TechnicalsTab symbol={ticker} analysis={analysis} isPro={isPro} requestUpgrade={requestUpgrade} />
            : <Awaiting run={run} what="technical read" />
        ) : null}
        {tab === 'macro' ? (analysis ? <MacroTab analysis={analysis} /> : <Awaiting run={run} what="macro context" />) : null}
        {tab === 'news' ? (analysis ? <NewsTab analysis={analysis} isPro={isPro} requestUpgrade={requestUpgrade} /> : <Awaiting run={run} what="news record" />) : null}
        {tab === 'filings' ? (analysis ? <FilingsTab analysis={analysis} /> : <Awaiting run={run} what="filings record" />) : null}
        {tab === 'relationships' ? <RelationshipsTab symbol={ticker} /> : null}
        {tab === 'options' ? <OptionsTab symbol={ticker} price={quote?.price ?? null} /> : null}

        <p className="cw-disclaimer">{analysis?.disclaimer ?? 'Research and education only — not investment advice.'}</p>
      </div>

      {paperConfigured ? (
        <Drawer open={paperOpen} onClose={() => setPaperOpen(false)} title={`Paper trade ${ticker}`} meta="Simulated account — no real money">
          <OrderTicket symbol={ticker} researchState={programme} onClose={() => setPaperOpen(false)} />
        </Drawer>
      ) : null}
    </div>
    </NarrativeProvider>
  )
}
