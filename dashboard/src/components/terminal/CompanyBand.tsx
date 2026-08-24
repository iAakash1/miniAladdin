'use client'

import CompanyMark from '@/components/ui/CompanyMark'
import CopyButton from '@/components/ui/CopyButton'
import { useState } from 'react'
import { fmtPrice } from '@/lib/format'
import { sectorProxy } from '@/lib/identity'
import { saveReport } from '@/lib/persistence'
import type { Analysis, ConsensusPrice, Verdict } from '@/lib/types'

const VERDICT_TONE: Record<Verdict, 'pos' | 'warn' | 'neg'> = {
  'Strong Buy': 'pos',
  Buy: 'pos',
  Hold: 'warn',
  Sell: 'neg',
  'Strong Sell': 'neg',
}

const TONE_VAR = { pos: 'var(--pos)', warn: 'var(--warn)', neg: 'var(--neg)' }
const WASH_VAR = { pos: 'var(--pos-wash)', warn: 'var(--warn-wash)', neg: 'var(--neg-wash)' }

export function VerdictChip({ verdict, size = 'md' }: { verdict: Verdict; size?: 'md' | 'lg' }) {
  const tone = VERDICT_TONE[verdict]
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: size === 'lg' ? '7px 14px' : '4px 10px',
        borderRadius: 'var(--r-md)',
        background: WASH_VAR[tone],
        border: `1px solid color-mix(in srgb, ${TONE_VAR[tone]} 35%, transparent)`,
        color: TONE_VAR[tone],
        fontSize: size === 'lg' ? '0.9375rem' : '0.8125rem',
        fontWeight: 620,
        letterSpacing: '0.01em',
        whiteSpace: 'nowrap',
      }}
    >
      {verdict}
    </span>
  )
}

/** Bookmark this run into Saved Reports (Vault). Only rendered when the
 *  backend recorded the analysis (historyId present). */
function SaveReportButton({ historyId }: { historyId: string }) {
  const [state, setState] = useState<'idle' | 'saving' | 'saved' | 'failed'>('idle')

  const save = async () => {
    setState('saving')
    const saved = await saveReport(historyId)
    setState(saved ? 'saved' : 'failed')
  }

  if (state === 'saved') {
    return (
      <span className="badge badge--accent" style={{ height: 24 }}>
        ★ Saved to Vault
      </span>
    )
  }
  return (
    <button
      type="button"
      className="btn btn--ghost btn--sm"
      onClick={save}
      disabled={state === 'saving'}
      title="Bookmark this analysis in your Vault"
      style={{ border: '1px solid var(--line)' }}
    >
      {state === 'saving' ? 'Saving…' : state === 'failed' ? 'Retry save' : '☆ Save report'}
    </button>
  )
}

/** Price agreement across every vendor that answered.
 *
 *  Deliberately compact — one line, not a panel. The reader's question is
 *  "can I trust this number", and the answer is a count and a spread, not a
 *  table. The individual readings sit behind the title attribute for anyone
 *  who wants them, and in full in the provenance section below.
 */
function ConsensusStrip({ consensus }: { consensus: ConsensusPrice }) {
  const spread = consensus.dispersion_pct
  return (
    <div className={`cons${consensus.conflict ? ' cons--conflict' : ''}`}>
      <span className="cons__agree">
        <span className="cons__bar" aria-hidden>
          {Array.from({ length: consensus.provider_count }, (_, i) => (
            <span key={i} className={i < consensus.agreeing ? 'cons__tick is-on' : 'cons__tick'} />
          ))}
        </span>
        <strong className="num">{consensus.agreement}</strong> sources agree
      </span>
      <span
        className="cons__range num"
        title={consensus.readings.map((r) => `${r.provider} ${r.price}`).join(' · ')}
      >
        {fmtPrice(consensus.low)}–{fmtPrice(consensus.high)}
        <span className="u-note"> · {spread.toFixed(3)}% spread</span>
      </span>
      {consensus.spread_bps !== null && (
        <span className="cons__book num">
          bid/ask {consensus.spread_bps.toFixed(1)}bps
          <span className="u-note"> via {consensus.spread_source}</span>
        </span>
      )}
      {consensus.conflict && (
        <span className="cons__flag">sources disagree materially</span>
      )}
    </div>
  )
}

/** Session context from the same quote fan-out, attributed per field.
 *
 *  Every value names the vendor that supplied it because none of these are
 *  reconciled: a session high belongs to one venue's tape, an average volume
 *  uses a window that vendor chose, and a moving average carries that
 *  vendor's adjustment conventions. Presenting them as a single unattributed
 *  row would imply a consensus that was never computed.
 */
function SessionStrip({ session }: { session: NonNullable<ConsensusPrice['session']> }) {
  const ORDER: Array<[string, string, (v: number) => string]> = [
    ['day_open', 'Open', (v) => v.toFixed(2)],
    ['day_high', 'High', (v) => v.toFixed(2)],
    ['day_low', 'Low', (v) => v.toFixed(2)],
    ['previous_close', 'Prev close', (v) => v.toFixed(2)],
    ['change_pct', 'Change', (v) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`],
    ['vwap', 'VWAP', (v) => v.toFixed(2)],
    ['ma_50', '50d MA', (v) => v.toFixed(2)],
    ['ma_200', '200d MA', (v) => v.toFixed(2)],
    ['trade_count', 'Trades', (v) => v.toLocaleString()],
    ['avg_volume', 'Avg vol', (v) => `${(v / 1e6).toFixed(1)}M`],
  ]
  const rows = ORDER.filter(([key]) => session[key] !== undefined)
  if (rows.length === 0) return null

  return (
    <div className="sess">
      {rows.map(([key, label, format]) => (
        <span key={key} className="sess__cell" title={`via ${session[key].provider}`}>
          <span className="sess__label">{label}</span>
          <span className="num sess__value">{format(session[key].value)}</span>
          <span className="sess__src">{session[key].provider}</span>
        </span>
      ))}
    </div>
  )
}

export default function CompanyBand({ analysis }: { analysis: Analysis }) {
  const wasDampened = analysis.verdict !== analysis.riskAdjusted

  return (
    <section
      aria-label={`${analysis.ticker} overview`}
      className="panel"
      style={{ padding: 'clamp(18px, 3vw, 26px)' }}
    >
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '16px 32px',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 4 }}>
            <CompanyMark ticker={analysis.ticker} name={analysis.companyName} size={40} />
            <h2 className="mono" style={{ fontSize: '1.25rem', fontWeight: 600, letterSpacing: '0.01em' }}>
              {analysis.ticker}
            </h2>
            {/* The ticker is the single most-copied string in the product —
                it goes into notes, spreadsheets and messages constantly, and
                the alternative is selecting monospace text by hand. */}
            <CopyButton value={analysis.ticker} label="Copy" title={`Copy ticker ${analysis.ticker}`} />
            <span style={{ fontSize: '1rem', color: 'var(--muted)', fontWeight: 500 }}>
              {analysis.companyName}
            </span>
          </div>
          {/* The sector gets a mark too — the sector-SPDR ETF that stands for
              it is a real listed instrument with a real logo, and the same
              symbol the breadth map on Market already trades on, so the two
              surfaces name the sector the same way. A sector with no proxy
              simply renders as text. */}
          <p style={{ fontSize: '0.8125rem', color: 'var(--faint)', display: 'flex', alignItems: 'center', gap: 7 }}>
            {sectorProxy(analysis.sector) && (
              <CompanyMark ticker={sectorProxy(analysis.sector)} name={`${analysis.sector} sector`} size={16} />
            )}
            {[analysis.sector, analysis.marketCap ? `${analysis.marketCap} market cap` : null]
              .filter(Boolean)
              .join(' · ') || '—'}
          </p>

          <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginTop: 18 }}>
            <span className="num" style={{ fontSize: 'clamp(1.9rem, 4vw, 2.4rem)', fontWeight: 600, lineHeight: 1 }}>
              {fmtPrice(analysis.price)}
            </span>
            <span style={{ fontSize: '0.8125rem', color: 'var(--faint)' }}>last close</span>
          </div>

          {/* Cross-vendor agreement. Every vendor that could quote this
              symbol was asked in parallel and none was discarded, so the
              useful statement is not the price — it is how many independent
              sources landed on it and how far apart they were. A single
              vendor can never say this. */}
          {analysis.consensusPrice && analysis.consensusPrice.provider_count > 1 && (
            <ConsensusStrip consensus={analysis.consensusPrice} />
          )}
          {/* Session context from the same fan-out. Attributed per field
              because none of it is reconciled across vendors. */}
          {analysis.consensusPrice?.session && (
            <SessionStrip session={analysis.consensusPrice.session} />
          )}
        </div>

        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'baseline',
              justifyContent: 'flex-end',
              gap: 12,
              marginBottom: 10,
            }}
          >
            {analysis.historyId && <SaveReportButton historyId={analysis.historyId} />}
            <p className="label">Risk-adjusted verdict</p>
          </div>
          <VerdictChip verdict={analysis.riskAdjusted} size="lg" />
          <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', marginTop: 12, maxWidth: 240 }}>
            {wasDampened ? (
              <>
                Raw signal{' '}
                <strong style={{ fontWeight: 560, color: 'var(--text)' }}>{analysis.verdict}</strong>, dampened
                under macro regime <span className="num">SRM {analysis.macro.srm.toFixed(2)}</span>
              </>
            ) : (
              <>
                Raw and risk-adjusted signals agree
                {analysis.macro.srm > 1 ? (
                  <>
                    {' '}
                    at <span className="num">SRM {analysis.macro.srm.toFixed(2)}</span>
                  </>
                ) : null}
              </>
            )}
          </p>
        </div>
      </div>
    </section>
  )
}
