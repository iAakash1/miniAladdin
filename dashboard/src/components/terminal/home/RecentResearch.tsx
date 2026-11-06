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
  const { quotes, at: quotedAt } = useQuotes(runs.map((r) => r.ticker))

  if (research.status === 'loading') {
    return <section className="sys-panel"><StateBlock state="waking" title="Loading your research record" /></section>
  }
  if (!runs.length) {
    if (research.status === 'unavailable') {
      return (
        <EmptyLine label="Recent research">
          Your research record could not be read right now, so this cannot say whether it is empty.
        </EmptyLine>
      )
    }
    return <FirstRun />
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
                <SymbolSpark values={q?.closes ?? (quotedAt ? [] : undefined)} width={72} height={20} />
                <span className="home-rr__chg"><Value value={q?.change_1d ?? null} kind="percent" digits={2} signed tone /></span>
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

/* The four stages of a run, said once, where a new account would otherwise
   see an empty list. */
const STAGES = [
  { k: 'Providers', v: 'Every configured vendor is asked in parallel; failures are kept, not hidden.' },
  { k: 'Evidence', v: 'Readings are reconciled field by field and disagreements stay visible.' },
  { k: 'Engine', v: 'A deterministic model sets the signal, confidence and risk.' },
  { k: 'Synthesis', v: 'An explanation is written from the evidence, with every citation checked.' },
]

/* A large, liquid name with full provider coverage: a first run that shows every stage. */
const FIRST_COMPANY = 'AAPL'

function FirstRun() {
  return (
    <section className="sys-panel firstrun" aria-labelledby="firstrun-title">
      <header className="sys-panel-head">
        <div className="sys-panel-head__title">
          <h2 className="sys-panel-title" id="firstrun-title">Recent research</h2>
          <span className="sys-panel-sub">no runs recorded yet</span>
        </div>
      </header>
      <div className="firstrun__body">
        <p className="firstrun__lede">
          Your research record is empty. Each company you research is kept here with its verdict,
          confidence, risk and date, so you can come back to what you concluded.
        </p>
        <ol className="firstrun__stages" aria-label="How a research run is built">
          {STAGES.map((s, i) => (
            <li key={s.k} className="firstrun__stage">
              <span className="firstrun__n">{i + 1}</span>
              <span className="firstrun__k">{s.k}</span>
              <span className="firstrun__v">{s.v}</span>
            </li>
          ))}
        </ol>
        <div className="firstrun__actions">
          <Link href={`/company/${encodeURIComponent(FIRST_COMPANY)}`} className="sys-btn sys-btn--primary">Research Apple ({FIRST_COMPANY})</Link>
          <Link href="/terminal/methodology" className="sys-btn sys-btn--ghost">How every number is made</Link>
        </div>
      </div>
    </section>
  )
}
