'use client'

/**
 * What is happening now — the arithmetic on the price series.
 *
 * Every figure here was already being computed and returned by the research
 * endpoint, and none of it reached this page. Two components read the
 * `technicals` block, and neither is on the security route: the page renders
 * `Fundamentals2`, not `Fundamentals`. So twenty-four fields of real computed
 * market analytics — the fifty-two week range, realised volatility, drawdown,
 * Sharpe, Sortino, RSI — were arriving on every request and being discarded.
 *
 * Three things govern how they are shown.
 *
 * **Scale.** The returns, the volatility and the drawdown arrive as
 * fractions: `return_5d` is 0.0266, not 2.66. The ratios elsewhere in the very
 * same payload arrive as percentages: `gross_margin_ttm` is 48.65. One
 * response, two scales, similar names. They are scaled once here, at the only
 * place that knows which is which, because no formatter in this product
 * multiplies.
 *
 * **Method.** An annualised figure computed from three months of data is not
 * the same claim as one computed from three years, and a Sharpe with no
 * risk-free rate is not the Sharpe most readers assume. Both are stated on
 * the figure rather than in a footnote.
 *
 * **What is deliberately not here.** The block also carries `raw_signal` and
 * `risk_adjusted_signal`, both currently reading "Buy". They are the output of
 * a scoring function in the prediction agent, not of anything promoted — the
 * research programme's verdict is NO PRODUCTION CANDIDATE and production
 * models are zero. Rendering "Buy" beside a price would make an unpromoted
 * heuristic look like a recommendation this product is standing behind, which
 * is the one thing the research firewall exists to prevent. `market_cap` is
 * also skipped: it arrives here pre-formatted as the string "$4.68T" while
 * the profile returns it as a number, and the profile's is the one that can
 * carry a unit and a provenance chain.
 */

import { useEffect, useState } from 'react'

import { EmptyLine, Inspectable, Panel, Prose, StateBlock, Value } from '@/components/system'
import { fetchResearch } from '@/lib/research-cache'
import { format } from '@/lib/quantity'

/** One session field, and the vendor that supplied it. */
interface Observed { value?: number; provider?: string }

interface Session {
  day_open?: Observed
  day_high?: Observed
  day_low?: Observed
  previous_close?: Observed
  change?: Observed
  change_pct?: Observed
  vwap?: Observed
  trade_count?: Observed
  avg_volume?: Observed
}

interface Technicals {
  current_price?: number | null
  return_5d?: number | null
  return_21d?: number | null
  volatility?: number | null
  sharpe_ratio?: number | null
  sortino_ratio?: number | null
  rsi_14?: number | null
  max_drawdown?: number | null
  week_52_high?: number | null
  week_52_low?: number | null
  beta?: number | null
  pe_ratio?: number | null
  eps?: number | null
}

/* The session fields worth showing, in reading order. Volume-weighted
   average price and trade count are the two that no other surface in this
   product has ever carried, and both are plain observations rather than
   anything this product computed. */
const SESSION_FIELDS: {
  key: keyof Session
  label: string
  kind: 'currency' | 'count' | 'percent'
  digits?: number
}[] = [
  { key: 'day_open', label: 'Open', kind: 'currency' },
  { key: 'day_high', label: 'High', kind: 'currency' },
  { key: 'day_low', label: 'Low', kind: 'currency' },
  { key: 'previous_close', label: 'Previous close', kind: 'currency' },
  { key: 'change', label: 'Change', kind: 'currency' },
  { key: 'vwap', label: 'VWAP', kind: 'currency' },
  { key: 'trade_count', label: 'Trades', kind: 'count', digits: 0 },
  { key: 'avg_volume', label: 'Average volume', kind: 'count', digits: 0 },
]

/** The window every derived figure below is computed over. */
const WINDOW = 'three months of daily closes, about 63 sessions'

/** A fraction the provider returns, scaled once, here. */
const pct = (v: number | null | undefined): number | null =>
  typeof v === 'number' && Number.isFinite(v) ? v * 100 : null

type Answer =
  | {
    for: string
    t: Technicals
    session: Session | null
    sessionDate: string | null
    excluded: string[]
    coherent: boolean | null
  }
  | { for: string; error: string }

export default function MarketStats({ symbol }: { symbol: string }) {
  const [answer, setAnswer] = useState<Answer | null>(null)

  useEffect(() => {
    let alive = true
    fetchResearch(symbol)
      .then((raw) => {
        if (!alive) return
        const d = raw as {
          technicals?: Technicals
          consensus_price?: {
            session?: Session | null
            session_date?: string | null
            session_excluded?: string[] | null
            session_coherent?: boolean | null
          }
        }
        const c = d.consensus_price
        setAnswer({
          for: symbol,
          t: d.technicals ?? {},
          session: c?.session ?? null,
          sessionDate: c?.session_date ?? null,
          excluded: c?.session_excluded ?? [],
          coherent: c?.session_coherent ?? null,
        })
      })
      .catch((e: Error) => { if (alive) setAnswer({ for: symbol, error: e.message }) })
    return () => { alive = false }
  }, [symbol])

  const settled = answer?.for === symbol ? answer : null
  if (!settled) {
    return <Panel title="Market" subtitle="what is happening now" state="waking">
      <StateBlock state="waking" title="Reading the price series" />
    </Panel>
  }
  if ('error' in settled) {
    return (
      <Panel title="Market" subtitle="what is happening now" state="unavailable">
        <StateBlock
          state="unavailable"
          title="The price statistics could not be read"
          detail={`${settled.error}. The price and chart above come from a different provider path and are unaffected.`}
        />
      </Panel>
    )
  }

  const t = settled.t
  const session = settled.session
  const has = Object.values(t).some((v) => typeof v === 'number' && Number.isFinite(v))
  if (!has && !session) {
    return (
      <EmptyLine label="Market statistics">
        No price statistics were returned for this security. That is an absence
        in the provider response, not a statement that the series is flat.
      </EmptyLine>
    )
  }

  const lo = t.week_52_low
  const hi = t.week_52_high
  const px = t.current_price
  /* Where the last price sits between the annual extremes. Not a signal and
     not a score — a position, which is what a range is for. */
  const position = typeof lo === 'number' && typeof hi === 'number'
    && typeof px === 'number' && hi > lo
    ? Math.min(100, Math.max(0, ((px - lo) / (hi - lo)) * 100))
    : null

  const rows: {
    label: string
    node: React.ReactNode
    display: string
    claim: string
    method: string
    assumptions?: string[]
    failsWhen?: string[]
  }[] = []

  const add = (
    label: string, value: number | null, kind: 'percent' | 'ratio' | 'multiple' | 'currency',
    opts: { digits?: number; signed?: boolean; tone?: boolean; claim: string; method: string; assumptions?: string[]; failsWhen?: string[] },
  ) => {
    if (value === null) return
    rows.push({
      label,
      node: <Value value={value} kind={kind} digits={opts.digits} signed={opts.signed} tone={opts.tone} />,
      display: format(value, kind, { digits: opts.digits, signed: opts.signed }).text,
      claim: opts.claim,
      method: opts.method,
      assumptions: opts.assumptions,
      failsWhen: opts.failsWhen,
    })
  }

  add('Return · 5 sessions', pct(t.return_5d), 'percent', {
    digits: 2, signed: true, tone: true,
    claim: 'The close is this much above or below the close five sessions ago.',
    method: 'last close ÷ close five sessions earlier − 1. A price return: it excludes dividends.',
    failsWhen: ['The window spans a split the series was not adjusted for.'],
  })
  add('Return · 21 sessions', pct(t.return_21d), 'percent', {
    digits: 2, signed: true, tone: true,
    claim: 'The close is this much above or below the close twenty-one sessions ago.',
    method: 'last close ÷ close twenty-one sessions earlier − 1. A price return, excluding dividends.',
    failsWhen: ['The window spans a split the series was not adjusted for.'],
  })
  add('Realised volatility', pct(t.volatility), 'percent', {
    digits: 1,
    claim: 'Daily returns varied this much, expressed at an annual rate.',
    method: `Standard deviation of daily returns × √252, over ${WINDOW}.`,
    assumptions: ['Daily returns are independent — the √252 scaling assumes it, and returns are not.'],
    failsWhen: [
      'The window contains an earnings date or a shock, which raises the figure without the security having become permanently more volatile.',
      'Annualising three months of data reports a yearly figure from about sixty-three observations.',
    ],
  })
  add('Maximum drawdown', pct(t.max_drawdown), 'percent', {
    digits: 1, tone: true,
    claim: 'The worst peak-to-trough fall within the window.',
    method: `Largest decline from a running maximum, over ${WINDOW}. Reported negative.`,
    failsWhen: ['A drawdown confined to a three-month window says nothing about the worst this security has ever done.'],
  })
  add('Sharpe', t.sharpe_ratio ?? null, 'ratio', {
    digits: 2,
    claim: 'Return per unit of volatility, at an annual rate.',
    method: '(mean daily return × 252) ÷ (standard deviation × √252). No risk-free rate is subtracted.',
    assumptions: [
      'The risk-free rate is zero. It is not, and a positive rate would lower this figure.',
      'Returns are normally distributed, which they are not.',
    ],
    failsWhen: [
      `Annualised from ${WINDOW}, so the estimate is noisy — a Sharpe from sixty-three observations is not a Sharpe from a decade.`,
    ],
  })
  add('Sortino', t.sortino_ratio ?? null, 'ratio', {
    digits: 2,
    claim: 'Return per unit of downside volatility.',
    method: 'As Sharpe, but the denominator uses only negative daily returns.',
    failsWhen: ['Few negative days in the window make the denominator small and the ratio unstable.'],
  })
  add('RSI (14)', t.rsi_14 ?? null, 'ratio', {
    digits: 1,
    claim: 'Where recent gains sit against recent losses, on a nought-to-one-hundred index.',
    method: 'Relative strength index over fourteen sessions. An index, not a percentage.',
    failsWhen: ['It is bounded, so it saturates in a sustained trend and stops distinguishing.'],
  })
  add('Beta', t.beta ?? null, 'multiple', {
    digits: 2,
    claim: 'How much this security has moved for a given move in its benchmark.',
    method: 'Supplied by the vendor. The benchmark and the window are not stated by the provider.',
    failsWhen: ['The benchmark is unknown, so this cannot be compared with a beta computed against a named index.'],
  })

  return (
    <Panel
      title="Market"
      subtitle="what is happening now"
      state="live"
      flush
    >
      {/* Observed, not derived — and kept visibly apart from the table below
          for that reason. Every figure carries the vendor that supplied it
          and the session it belongs to, because assembling one session from
          several vendors' different days is exactly what produced a day
          range that excluded its own last price. */}
      {session ? (
        <div className="mkt__session">
          <div className="mkt__range-head">
            <span className="sys-label">Observed this session</span>
            <span className="sys-meta">
              {settled.sessionDate ?? 'date not stated'}
              {settled.coherent === false ? ' · range and price disagree' : ''}
            </span>
          </div>
          <dl className="mkt__obs">
            {SESSION_FIELDS.map(({ key, label, kind, digits }) => {
              const o = session[key]
              if (!o || typeof o.value !== 'number') return null
              return (
                <div key={key} className="mkt__obs-item">
                  <dt>{label}</dt>
                  <dd>
                    <Inspectable refValue={{
                      label,
                      display: format(o.value, kind, { digits }).text,
                      claim: `${label} for the session of ${settled.sessionDate ?? 'an unstated date'}.`,
                      observation: `Reported by ${o.provider ?? 'an unnamed vendor'}. Not reconciled with any other vendor — a session figure is a fact about one venue's tape.`,
                      source: o.provider,
                      asOf: settled.sessionDate ?? undefined,
                      providers: o.provider ? [o.provider] : undefined,
                      method: 'as the vendor reported it, for the most recent session any vendor observed — vendors answering with an earlier session contribute nothing here',
                      status: 'live',
                      freshness: 'read once per research request',
                      assumptions: [
                        'The vendor’s session is the same trading day this product pinned the block to.',
                        'The figure describes that vendor’s venue, which may not be the primary listing.',
                      ],
                      failsWhen: [
                        'Compared with a figure from a different vendor’s tape — volumes and ranges differ by venue.',
                        ...(settled.excluded.length
                          ? [`${settled.excluded.join(', ')} answered for a different session or carried no timestamp, so nothing here comes from them.`]
                          : []),
                      ],
                    }}>
                      <Value value={o.value} kind={kind} digits={digits} />
                    </Inspectable>
                    {o.provider ? <span className="mkt__who">{o.provider}</span> : null}
                  </dd>
                </div>
              )
            })}
          </dl>
          {settled.excluded.length ? (
            <Prose size="fine">
              {settled.excluded.join(', ')} answered for an earlier session or
              carried no timestamp, so {settled.excluded.length === 1 ? 'it contributes' : 'they contribute'} nothing
              above. That is a difference of timing, not a provider failure.
            </Prose>
          ) : null}
        </div>
      ) : null}

      {position !== null && typeof lo === 'number' && typeof hi === 'number' ? (
        <div className="mkt__range">
          <div className="mkt__range-head">
            <span className="sys-label">Fifty-two week range</span>
            <span className="sys-meta">{position.toFixed(0)}% of the range</span>
          </div>
          <div className="mkt__track" role="img"
            aria-label={`Last price ${px} between a low of ${lo} and a high of ${hi}`}>
            <span className="mkt__fill" style={{ width: `${position}%` }} />
            <span className="mkt__pin" style={{ left: `${position}%` }} />
          </div>
          <div className="mkt__ends">
            <span><Value value={lo} kind="currency" /> <em>low</em></span>
            <span><em>high</em> <Value value={hi} kind="currency" /></span>
          </div>
        </div>
      ) : null}

      <div className="sys-scroll-x">
        <table className="sys-table sys-table--compact">
          <thead>
            <tr><th scope="col">Measure</th><th scope="col" className="num">Value</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label}>
                <td>{r.label}</td>
                <td className="num">
                  <Inspectable refValue={{
                    label: r.label,
                    display: r.display,
                    claim: r.claim,
                    observation: `Computed from ${WINDOW} of this security's own closes.`,
                    method: r.method,
                    assumptions: r.assumptions,
                    failsWhen: r.failsWhen,
                    source: 'derived by this product from the price series — not reported by a vendor',
                    status: 'recorded',
                    freshness: 'recomputed with each research read',
                  }}>
                    {r.node}
                  </Inspectable>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Prose size="fine">
        The session figures above are reported: each is one vendor&apos;s
        observation of one venue&apos;s tape, attributed and dated, and none of
        them is reconciled against another. Everything in the table is
        derived — this product&apos;s own arithmetic on {WINDOW}, each figure
        carrying its method and the conditions under which it should not be
        trusted. Returns are price returns and exclude dividends. The
        annualised figures are annualised from three months, which is a noisy
        basis for a yearly number.
      </Prose>
    </Panel>
  )
}
