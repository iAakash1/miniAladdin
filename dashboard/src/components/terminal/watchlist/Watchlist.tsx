'use client'

import Link from 'next/link'

import { EmptyLine, StateBlock, Value } from '@/components/system'
import CompanyIdentity from '@/components/visual/CompanyIdentity'
import SymbolSpark from '@/components/visual/SymbolSpark'
import { age } from '@/components/company/derive'
import { useQuotes } from '@/lib/use-quotes'
import { useResearchHistory, verdictTone } from '@/lib/use-research-history'
import { useWatchedSymbols, useWatchlists, useWatchlistsStatus } from '@/lib/watchlists'

/** The names the account follows, with price, trend and last research state. */
export default function Watchlist({ limit = 10 }: { limit?: number }) {
  const lists = useWatchlists()
  const status = useWatchlistsStatus()
  const symbols = useWatchedSymbols().slice(0, limit)
  const { quotes, error } = useQuotes(symbols)
  const research = useResearchHistory()

  if (status === 'idle' || status === 'loading') {
    return <section className="sys-panel"><StateBlock state="waking" title="Loading your watchlists" /></section>
  }
  if (status === 'error' || status === 'unauthenticated') {
    return (
      <section className="sys-panel">
        <StateBlock state="unavailable" title="Watchlists are unavailable right now" detail="The persistence service did not answer. Your lists are stored on the server and are unaffected." />
      </section>
    )
  }
  if (!symbols.length) {
    return (
      <EmptyLine label="Watchlist">
        No names yet. Open any company and press <kbd className="sys-kbd">Watch</kbd> — lists sync to your account.
      </EmptyLine>
    )
  }

  return (
    <section className="sys-panel home-wl" aria-label="Watchlist">
      <header className="sys-panel-head">
        <div className="sys-panel-head__title">
          <h2 className="sys-panel-title">Watchlist</h2>
          <span className="sys-panel-sub">{lists.length} list{lists.length === 1 ? '' : 's'} · {watchedCount(lists)} names</span>
        </div>
        <Link className="cw-more" href="/terminal/portfolio">Manage lists</Link>
      </header>
      {error ? <p className="home-warn">Quote refresh failed; prices shown are from the last successful read.</p> : null}
      <div className="sys-scroll-x">
        <table className="sys-table home-wl__t">
          <thead>
            <tr>
              <th scope="col">Company</th>
              <th scope="col" className="num">Last</th>
              <th scope="col" className="num">1D</th>
              <th scope="col" className="num">1W</th>
              <th scope="col" className="home-wl__trend">3 months</th>
              <th scope="col">Last research</th>
            </tr>
          </thead>
          <tbody>
            {symbols.map((s) => {
              const q = quotes[s]
              const run = research.latest(s)
              return (
                <tr key={s}>
                  <td><CompanyIdentity symbol={s} name={run?.company_name} size="sm" href={`/company/${encodeURIComponent(s)}`} /></td>
                  <td className="num"><Value value={q?.price ?? null} kind="currency" /></td>
                  <td className="num"><Value value={q?.change_1d ?? null} kind="percent" digits={2} signed tone /></td>
                  <td className="num"><Value value={q?.change_1w ?? null} kind="percent" digits={2} signed tone /></td>
                  <td className="home-wl__trend"><SymbolSpark symbol={s} width={84} height={20} /></td>
                  <td>
                    {run ? (
                      <span className="home-run">
                        <span className="sig-verdict sig-verdict--sm" data-tone={verdictTone(run.verdict)}>{run.verdict}</span>
                        {run.confidence !== null ? <span className="home-run__c sys-num">{run.confidence}</span> : null}
                        <span className="home-run__t">{age(run.created_at)}</span>
                      </span>
                    ) : <span className="home-dim">not researched</span>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function watchedCount(lists: Array<{ tickers: string[] }>): number {
  return new Set(lists.flatMap((l) => l.tickers)).size
}
