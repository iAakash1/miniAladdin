'use client'

import Link from 'next/link'

import { EmptyLine, StateBlock, Value } from '@/components/system'
import { age } from '@/components/company/derive'
import CompanyIdentity from '@/components/visual/CompanyIdentity'
import SymbolSpark from '@/components/visual/SymbolSpark'
import { useQuotes } from '@/lib/use-quotes'
import { useResearchHistory, verdictTone } from '@/lib/use-research-history'

/** The account's latest research runs — one per company, newest first. */
export default function RecentResearch({ limit = 6 }: { limit?: number }) {
  const research = useResearchHistory()
  const runs = research.recent.slice(0, limit)
  const { quotes } = useQuotes(runs.map((r) => r.ticker))

  if (research.status === 'loading') {
    return <section className="sys-panel"><StateBlock state="waking" title="Loading your research record" /></section>
  }
  if (!runs.length) {
    return (
      <EmptyLine label="Recent research">
        {research.status === 'unavailable'
          ? 'Your research record could not be read right now.'
          : 'Runs you make appear here with their verdict, confidence and date.'}
      </EmptyLine>
    )
  }

  return (
    <section className="sys-panel home-rr" aria-label="Recent research">
      <header className="sys-panel-head">
        <div className="sys-panel-head__title">
          <h2 className="sys-panel-title">Recent research</h2>
          <span className="sys-panel-sub">{research.total} runs recorded</span>
        </div>
        <Link className="cw-more" href="/terminal/vault">Research log</Link>
      </header>
      <ul className="home-rr__list">
        {runs.map((r) => {
          const q = quotes[r.ticker.toUpperCase()]
          return (
            <li key={r.id} className="home-rr__row">
              <CompanyIdentity
                symbol={r.ticker.toUpperCase()}
                name={r.company_name}
                size="md"
                href={`/company/${encodeURIComponent(r.ticker)}`}
              />
              <span className="home-rr__state">
                <span className="sig-verdict sig-verdict--sm" data-tone={verdictTone(r.verdict)}>{r.verdict}</span>
                {r.confidence !== null ? (
                  <span className="home-conf" title={`Confidence ${r.confidence} of 100`}>
                    <span className="home-conf__bar" style={{ width: `${Math.max(0, Math.min(100, r.confidence))}%` }} />
                  </span>
                ) : null}
                <span className="home-rr__meta">
                  {r.confidence !== null ? <span className="sys-num">{r.confidence}</span> : null}
                  {r.risk_level ? <span>{r.risk_level.toLowerCase()} risk</span> : null}
                  <span>{age(r.created_at)}</span>
                </span>
              </span>
              <span className="home-rr__px">
                <SymbolSpark symbol={r.ticker.toUpperCase()} width={72} height={20} />
                <span className="home-rr__chg"><Value value={q?.change_1d ?? null} kind="percent" digits={2} signed tone /></span>
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
