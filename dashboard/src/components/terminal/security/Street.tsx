'use client'

/**
 * What the sell side says, from two vendors that are not asking the same
 * people.
 *
 * Both blocks were arriving on every research request and neither had any
 * rendering. `analyst` carries price targets from yfinance; `street_
 * intelligence` carries a rating distribution, earnings surprises and insider
 * sentiment from Finnhub.
 *
 * They disagree about something basic: yfinance counts 39 analysts covering
 * Apple and Finnhub counts 53. That is not an error in either, and it is not
 * a conflict to reconcile. Each vendor polls its own panel, so the counts
 * describe different populations — which is exactly why the price targets and
 * the rating distribution are shown as two separate observations with their
 * vendor named, and why no attempt is made to express the ratings as a view
 * on the targets or the reverse.
 *
 * Two scale conventions arrive in the same payload, which is the trap this
 * product keeps finding. `buy_ratio` is 0.642 — a fraction — while
 * `avg_surprise_pct` is 1.69, already a percentage. Reading either with the
 * other's convention is off by a hundred. They are scaled once, here, and
 * pinned in tests.
 *
 * The mean rating is shown beside the distribution rather than instead of it.
 * A 2.18 on a five-point scale hides whether that is fifty analysts clustered
 * on "buy" or a split between "strong buy" and "sell", and those are opposite
 * situations for anyone sizing a position — the same reason the provider
 * schema keeps the distribution whole.
 *
 * Deliberately not rendered: the vendor's pre-written `findings`, which are
 * narrative sentences carrying a tone. They restate the numbers below
 * accurately enough, and a coloured sentence beside a price reads as this
 * product's own view. The structured observations are shown and the reader
 * draws the conclusion, which is the same call made about the `ai` block.
 */

import { useEffect, useState } from 'react'

import { EmptyLine, Inspectable, Panel, Prose, StateBlock, Value } from '@/components/system'
import { fetchResearch } from '@/lib/research-cache'
import { format } from '@/lib/quantity'

interface Reading {
  target_mean?: number | null
  target_high?: number | null
  target_low?: number | null
  analyst_count?: number | null
  recommendation?: string | null
  recommendation_mean?: number | null
  source?: string | null
}

interface Recommendations {
  period?: string
  analysts?: number
  strong_buy?: number
  buy?: number
  hold?: number
  sell?: number
  strong_sell?: number
  /** A fraction. 0.642 is 64.2%. */
  buy_ratio?: number
  trend?: string
  months?: number
}

interface Surprises {
  quarters?: number
  beats?: number
  /** Already a percentage. 1.69 is 1.69%. */
  avg_surprise_pct?: number
  last_surprise_pct?: number
  last_period?: string
}

interface Insider {
  /** Finnhub's monthly share purchase ratio, bounded -100 to 100. Not a percentage. */
  mspr?: number
  net_shares?: number
  read?: string
}

/** A fraction the vendor supplies, scaled once, here. */
const pct = (v: number | null | undefined): number | null =>
  typeof v === 'number' && Number.isFinite(v) ? v * 100 : null

const RATINGS: { key: keyof Recommendations; label: string }[] = [
  { key: 'strong_buy', label: 'Strong buy' },
  { key: 'buy', label: 'Buy' },
  { key: 'hold', label: 'Hold' },
  { key: 'sell', label: 'Sell' },
  { key: 'strong_sell', label: 'Strong sell' },
]

type Answer =
  | { for: string; targets: Reading | null; recs: Recommendations | null
    surprises: Surprises | null; insider: Insider | null }
  | { for: string; error: string }

export default function Street({ symbol }: { symbol: string }) {
  const [answer, setAnswer] = useState<Answer | null>(null)

  useEffect(() => {
    let alive = true
    fetchResearch(symbol)
      .then((raw) => {
        if (!alive) return
        const d = raw as {
          analyst?: { readings?: Reading[] }
          street_intelligence?: {
            recommendations?: Recommendations
            surprises?: Surprises
            insider?: Insider
          }
        }
        setAnswer({
          for: symbol,
          targets: d.analyst?.readings?.[0] ?? null,
          recs: d.street_intelligence?.recommendations ?? null,
          surprises: d.street_intelligence?.surprises ?? null,
          insider: d.street_intelligence?.insider ?? null,
        })
      })
      .catch((e: Error) => { if (alive) setAnswer({ for: symbol, error: e.message }) })
    return () => { alive = false }
  }, [symbol])

  const settled = answer?.for === symbol ? answer : null
  if (!settled) {
    return (
      <Panel title="Street" subtitle="what the sell side says" state="waking">
        <StateBlock state="waking" title="Reading analyst coverage" />
      </Panel>
    )
  }
  if ('error' in settled) {
    return (
      <Panel title="Street" subtitle="what the sell side says" state="unavailable">
        <StateBlock
          state="unavailable"
          title="Analyst coverage could not be read"
          detail={`${settled.error}. Nothing is shown in its place.`}
        />
      </Panel>
    )
  }

  const { targets, recs, surprises, insider } = settled
  if (!targets && !recs && !surprises && !insider) {
    return (
      <EmptyLine label="Street">
        No configured vendor returned analyst coverage for this security. That
        is an absence in the vendor responses, not a statement that the name is
        uncovered.
      </EmptyLine>
    )
  }

  const lo = targets?.target_low
  const hi = targets?.target_high
  const mean = targets?.target_mean
  const targetSpread = typeof lo === 'number' && typeof hi === 'number' && lo > 0
    ? ((hi - lo) / lo) * 100
    : null
  const meanAt = typeof lo === 'number' && typeof hi === 'number'
    && typeof mean === 'number' && hi > lo
    ? Math.min(100, Math.max(0, ((mean - lo) / (hi - lo)) * 100))
    : null

  const ratedTotal = RATINGS.reduce((n, r) => n + (Number(recs?.[r.key]) || 0), 0)
  const buyPct = pct(recs?.buy_ratio)

  /* The two counts describe different analyst panels. Said once, plainly,
     rather than rendered as a conflict — nothing here is wrong. */
  const panelsDiffer = typeof targets?.analyst_count === 'number'
    && typeof recs?.analysts === 'number'
    && targets.analyst_count !== recs.analysts

  return (
    <Panel title="Street" subtitle="what the sell side says — two vendors, two panels" flush>

      {targets && typeof mean === 'number' ? (
        <div className="st__block">
          <div className="mkt__range-head">
            <span className="sys-label">Price targets</span>
            <span className="sys-meta">
              {targets.analyst_count ?? '—'} analysts · {targets.source ?? 'vendor'}
            </span>
          </div>
          {meanAt !== null && typeof lo === 'number' && typeof hi === 'number' ? (
            <>
              <div className="mkt__track" role="img"
                aria-label={`Target mean ${mean} between a low of ${lo} and a high of ${hi}`}>
                <span className="mkt__pin" style={{ left: `${meanAt}%` }} />
              </div>
              <div className="mkt__ends">
                <span><Value value={lo} kind="currency" /> <em>low</em></span>
                <span><em>high</em> <Value value={hi} kind="currency" /></span>
              </div>
            </>
          ) : null}
          <dl className="mkt__obs">
            <div className="mkt__obs-item">
              <dt>Mean target</dt>
              <dd>
                <Inspectable refValue={{
                  label: 'Mean price target',
                  display: format(mean, 'currency').text,
                  claim: `The ${targets.analyst_count ?? 'covering'} analysts this vendor polls average a target of ${format(mean, 'currency').text}.`,
                  observation: `One vendor's consensus of its own contributing analysts, spanning ${format(lo ?? 0, 'currency').text} to ${format(hi ?? 0, 'currency').text}.`,
                  source: targets.source ?? undefined,
                  providers: targets.source ? [targets.source] : undefined,
                  method: 'the vendor’s own mean of its own panel — not computed here, and not reconciled with any other vendor’s panel',
                  status: 'recorded',
                  assumptions: [
                    'The panel is the vendor’s, and another vendor polls a different set of analysts.',
                    'Targets carry no common horizon — contributors may be forecasting different periods.',
                  ],
                  failsWhen: [
                    'Read as a forecast rather than as a summary of opinion.',
                    targetSpread !== null
                      ? `The high is ${targetSpread.toFixed(0)}% above the low, so the mean summarises a wide disagreement rather than a settled view.`
                      : 'The spread of contributing targets is unknown.',
                    'Compared with another vendor’s mean — the two are means of different panels.',
                  ],
                }}>
                  <Value value={mean} kind="currency" />
                </Inspectable>
              </dd>
            </div>
            {targetSpread !== null ? (
              <div className="mkt__obs-item">
                <dt>High above low</dt>
                <dd><Value value={targetSpread} kind="percent" digits={0} /></dd>
              </div>
            ) : null}
            {typeof targets.recommendation_mean === 'number' ? (
              <div className="mkt__obs-item">
                <dt>Mean rating</dt>
                <dd>
                  <Value value={targets.recommendation_mean} kind="ratio" digits={2} />
                  <span className="mkt__who">1 = strong buy, 5 = strong sell</span>
                </dd>
              </div>
            ) : null}
          </dl>
        </div>
      ) : null}

      {recs && ratedTotal > 0 ? (
        <div className="st__block">
          <div className="mkt__range-head">
            <span className="sys-label">Rating distribution</span>
            <span className="sys-meta">
              {recs.analysts ?? ratedTotal} analysts · finnhub
              {recs.period ? ` · as of ${recs.period}` : ''}
            </span>
          </div>
          <div className="sys-scroll-x">
            <table className="sys-table sys-table--compact st">
              <thead>
                <tr>
                  <th scope="col">Rating</th>
                  <th scope="col" className="num">Analysts</th>
                  <th scope="col" className="num">Share</th>
                </tr>
              </thead>
              <tbody>
                {RATINGS.map((r) => {
                  const n = Number(recs[r.key]) || 0
                  return (
                    <tr key={r.key}>
                      <td>{r.label}</td>
                      <td className="num"><Value value={n} kind="count" digits={0} /></td>
                      <td className="num">
                        <Value value={(n / ratedTotal) * 100} kind="percent" digits={0} />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {buyPct !== null ? (
            <Prose size="fine">
              {buyPct.toFixed(1)}% rate it buy or better
              {recs.trend ? `, and the distribution has been ${recs.trend} over ${recs.months ?? 'several'} months` : ''}.
              That is a count of opinions held by other people, reported as
              they were given. It is not this product&apos;s view and nothing
              here is scored against it.
            </Prose>
          ) : null}
        </div>
      ) : null}

      {surprises || insider ? (
        <div className="st__block">
          <div className="mkt__range-head">
            <span className="sys-label">Reported history</span>
            <span className="sys-meta">finnhub</span>
          </div>
          <dl className="mkt__obs">
            {surprises && typeof surprises.beats === 'number' ? (
              <div className="mkt__obs-item">
                <dt>Earnings beats</dt>
                <dd>
                  {surprises.beats} of {surprises.quarters ?? '—'}
                  <span className="mkt__who">quarters reported</span>
                </dd>
              </div>
            ) : null}
            {surprises && typeof surprises.avg_surprise_pct === 'number' ? (
              <div className="mkt__obs-item">
                <dt>Average surprise</dt>
                <dd>
                  {/* Already a percentage in the payload — unlike buy_ratio,
                      which is a fraction, in the same block. */}
                  <Value value={surprises.avg_surprise_pct} kind="percent" digits={2} signed tone />
                </dd>
              </div>
            ) : null}
            {surprises && typeof surprises.last_surprise_pct === 'number' ? (
              <div className="mkt__obs-item">
                <dt>Most recent</dt>
                <dd>
                  <Value value={surprises.last_surprise_pct} kind="percent" digits={2} signed tone />
                  {surprises.last_period ? <span className="mkt__who">{surprises.last_period}</span> : null}
                </dd>
              </div>
            ) : null}
            {insider && typeof insider.mspr === 'number' ? (
              <div className="mkt__obs-item">
                <dt>Insider sentiment</dt>
                <dd>
                  <Inspectable refValue={{
                    label: 'Insider sentiment (MSPR)',
                    display: insider.mspr.toFixed(1),
                    claim: `Insider trading over the last six months reads as ${insider.read ?? 'unclassified'}.`,
                    observation: `Finnhub's monthly share purchase ratio, ${insider.mspr.toFixed(1)} on a scale from -100 to 100${typeof insider.net_shares === 'number' ? `, on net share movement of ${insider.net_shares.toLocaleString()}` : ''}.`,
                    source: 'finnhub',
                    unit: 'index, -100 to 100',
                    method: 'vendor-supplied index — bounded, and not a percentage despite its range',
                    status: 'recorded',
                    assumptions: [
                      'Insider filings are complete and timely for the period.',
                    ],
                    failsWhen: [
                      'Read as a percentage. It is a bounded index and -100 is its floor, not a total sale.',
                      'Read as a signal: routine compensation-related selling is the most common cause of a negative reading.',
                    ],
                  }}>
                    <Value value={insider.mspr} kind="ratio" digits={1} />
                  </Inspectable>
                  <span className="mkt__who">index, −100 to 100</span>
                </dd>
              </div>
            ) : null}
          </dl>
        </div>
      ) : null}

      {panelsDiffer ? (
        <Prose size="fine">
          The two vendors count different numbers of analysts —{' '}
          {targets?.analyst_count} for the price targets and {recs?.analysts} for
          the ratings. Neither is wrong: each polls its own panel, so the two
          blocks describe different populations and are not reconciled against
          one another. A single &ldquo;analysts covering&rdquo; figure here
          would have to discard one of them.
        </Prose>
      ) : null}
    </Panel>
  )
}
