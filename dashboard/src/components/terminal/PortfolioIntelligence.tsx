'use client'

/**
 * Portfolio intelligence — what the whole book says, as opposed to what each
 * row says.
 *
 * The positions table answers "what do I own". It cannot answer the
 * questions a book actually raises: how much of this is one bet, which names
 * carry the risk rather than the capital, and how much of the book has never
 * been looked at. Those are arithmetic over every holding at once.
 *
 * ## Everything here is computed server-side
 *
 * The figures come from `/api/portfolio/intelligence`, which runs
 * `src/services/portfolio_intelligence.py` against stored positions and
 * stored analyses. None of it is recomputed in the browser — one
 * implementation, with tests pinned to hand-worked values, rather than two
 * that can disagree.
 *
 * ## Two honesty constraints the design carries
 *
 * **Weights are cost basis, not market value**, because average price is what
 * the product stores. The panel says so rather than letting a reader assume
 * it is mark-to-market.
 *
 * **Risk concentration is not portfolio volatility.** No covariance is
 * estimated anywhere in this system, so the weighted risk figure is labelled
 * as a weighted mean of per-name scores and nothing more. A number called
 * "portfolio risk" here would be a fabrication wearing a statistic's
 * clothes.
 *
 * Uncovered positions are shown, not hidden. A book where four of nine names
 * have never been scored is a fact about the book, and every figure above
 * that line silently excludes them.
 */

import { useCallback, useEffect, useState } from 'react'

import CompanyMark from '@/components/ui/CompanyMark'
import EmptyState from '@/components/ui/EmptyState'
import PortfolioPerformanceChart from '@/components/terminal/PortfolioPerformanceChart'
import { POSITIONS_CHANGED } from '@/components/terminal/PositionsPanel'
import { Segmented } from '@/components/ui/Controls'
import Skeleton from '@/components/ui/Skeleton'
import { StatusPill, TrendMark, type StatusTone } from '@/components/ui/DataMarks'
import {
  fetchPortfolioIntel,
  type HoldingValuation,
  type PortfolioIntel,
} from '@/lib/persistence'

type Status = 'loading' | 'ready' | 'error'

/* ── money ─────────────────────────────────────────────────────────────────
   The currency code comes from the server, so nothing here hardcodes a
   symbol. Intl is given the code and picks the symbol, grouping and
   placement for the reader's locale; a hand-rolled `$${n}` would be wrong
   the moment a non-USD venue is added, and wrong for every reader whose
   locale groups differently. */
function money(value: number | null | undefined, currency: string, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    }).format(value)
  } catch {
    return value.toFixed(digits)
  }
}

/** Signed money, with the sign carried by a character rather than only by
 *  colour — colour alone fails a greyscale print and a colour-blind reader. */
function signedMoney(value: number | null | undefined, currency: string): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const sign = value > 0 ? '+' : value < 0 ? '−' : ''
  return `${sign}${money(Math.abs(value), currency)}`
}

function signedPct(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const sign = value > 0 ? '+' : value < 0 ? '−' : ''
  return `${sign}${Math.abs(value).toFixed(2)}%`
}

/** One of the four headline figures.
 *
 *  Zero is deliberately neutral rather than green: a book exactly at cost has
 *  not gained, and tinting it positive would be a small lie repeated on every
 *  render. */
function SummaryCard({
  label, value, sub, tone = 'neutral',
}: {
  label: string
  value: string
  sub?: string | null
  tone?: 'pos' | 'neg' | 'neutral'
}) {
  return (
    <div className={`pf-sum pf-sum--${tone}`}>
      <span className="pf-sum__label">{label}</span>
      <span className="num pf-sum__value">{value}</span>
      {sub && <span className="num pf-sum__sub">{sub}</span>}
    </div>
  )
}

const toneOf = (n: number | null | undefined): 'pos' | 'neg' | 'neutral' =>
  n === null || n === undefined || !Number.isFinite(n) || n === 0 ? 'neutral' : n > 0 ? 'pos' : 'neg'

/** The holdings table, valued.
 *
 *  An unpriced row is rendered as a row with no valuation rather than
 *  dropped: a book is not smaller because a vendor was unreachable, and the
 *  reader needs to see which name is missing. */
function HoldingsTable({ rows, currency }: { rows: HoldingValuation[]; currency: string }) {
  return (
    <div className="pf-table-wrap">
      <table className="data-table pf-table">
        <caption className="visually-hidden">
          Holdings valued against current market prices
        </caption>
        <thead>
          <tr>
            <th scope="col">Ticker</th>
            <th scope="col" className="num">Shares</th>
            <th scope="col" className="num">Avg price</th>
            <th scope="col" className="num">Current</th>
            <th scope="col" className="num">Invested</th>
            <th scope="col" className="num">Value</th>
            <th scope="col" className="num">P&amp;L</th>
            <th scope="col" className="num">Return</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.ticker} className={row.priced ? undefined : 'pf-table__row--unpriced'}>
              <td>
                <span className="u-row" style={{ gap: 8, flexWrap: 'nowrap' }}>
                  <CompanyMark ticker={row.ticker} size={18} />
                  <span className="mono" style={{ fontWeight: 600 }}>{row.ticker}</span>
                  {row.stale && <span className="badge badge--warn" style={{ height: 17, fontSize: '0.5625rem' }}>stale</span>}
                </span>
              </td>
              <td className="num">{row.shares}</td>
              <td className="num">{money(row.avg_price, currency)}</td>
              <td className="num">
                {row.priced ? (
                  money(row.current_price, currency)
                ) : (
                  <span className="u-note" title={row.price_note ?? undefined}>unavailable</span>
                )}
              </td>
              <td className="num">{money(row.invested, currency)}</td>
              <td className="num">{row.priced ? money(row.current_value, currency) : '—'}</td>
              <td className="num" style={{ color: `var(--${toneOf(row.pnl) === 'neutral' ? 'muted' : toneOf(row.pnl)})` }}>
                {signedMoney(row.pnl, currency)}
              </td>
              <td className="num">
                <span className="u-row" style={{ gap: 6, justifyContent: 'flex-end', flexWrap: 'nowrap' }}>
                  <TrendMark value={row.pnl_pct} />
                  <span style={{ color: `var(--${toneOf(row.pnl_pct) === 'neutral' ? 'muted' : toneOf(row.pnl_pct)})` }}>
                    {signedPct(row.pnl_pct)}
                  </span>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const BAND_TONE: Record<string, StatusTone> = {
  diversified: 'pos',
  moderate: 'warn',
  concentrated: 'neg',
}

const TONE_MAP: Record<string, StatusTone> = {
  warn: 'warn',
  accent: 'accent',
  muted: 'muted',
  pos: 'pos',
  neg: 'neg',
}

/** A weight, as a bar the width of its share of the book.
 *
 *  Scaled to the largest row rather than to 100%: a ten-name book has no row
 *  above 30%, and bars that never leave their first third convey nothing. */
/**
 * A bar can only draw a number it has.
 *
 * An unmeasured share used to arrive here as zero, which drew an empty bar —
 * and an empty bar in a list of contributions reads as "this position moved
 * nothing", which is a measurement. It is not the same claim as "we do not
 * know what this position contributed", and the second must not be able to
 * masquerade as the first.
 *
 * An unknown share draws a hatched track instead of a fill, and says so to a
 * screen reader.
 */
function WeightBar({ pct, max, tone = 'accent' }: {
  pct: number | null | undefined
  max: number | null | undefined
  tone?: string
}) {
  const known = typeof pct === 'number' && Number.isFinite(pct)
  const scale = typeof max === 'number' && Number.isFinite(max) && max > 0 ? max : null

  if (!known || scale === null) {
    return (
      <span
        className="pf-bar pf-bar--unknown"
        role="img"
        aria-label={known ? 'share not comparable: no scale' : 'share not measured'}
        title={known ? 'No comparable scale for this row.' : 'This share was not measured.'}
      />
    )
  }
  return (
    <span className={`pf-bar pf-bar--${tone}`}>
      <span className="pf-bar__fill" style={{ transform: `scaleX(${Math.min(1, pct / scale)})` }} />
    </span>
  )
}

export default function PortfolioIntelligence() {
  const [data, setData] = useState<PortfolioIntel | null>(null)
  const [status, setStatus] = useState<Status>('loading')
  // A refresh keeps the figures on screen while it runs. Blanking the panel
  // back to skeletons on every refresh would make the one action a holder
  // takes repeatedly feel like a page reload.
  const [refreshing, setRefreshing] = useState(false)
  // Range and benchmark are server-side query params, not client filters: the
  // server decides how much history to fetch, so slicing here would show a
  // 1Y window trimmed from a 3M fetch.
  const [range, setRange] = useState('3M')
  const [benchmark, setBenchmark] = useState('SPY')

  const load = useCallback((quiet = false, opts: { range?: string; benchmark?: string } = {}) => {
    queueMicrotask(() => (quiet ? setRefreshing(true) : setStatus('loading')))
    fetchPortfolioIntel({ range: opts.range ?? range, benchmark: opts.benchmark ?? benchmark })
      .then((report) => {
        setData(report)
        setStatus('ready')
      })
      .catch(() => {
        // A failed *refresh* must not throw away figures that were valid a
        // moment ago; only a failed first load has nothing to fall back to.
        if (!quiet) setStatus('error')
      })
      .finally(() => setRefreshing(false))
  }, [range, benchmark])

  useEffect(() => { load() }, [load])

  /* Revalue when the book changes. Without this the panel kept showing the
     previous book's valuation after an add or a delete — the positions table
     said four holdings and the summary above it said three, which is the
     kind of disagreement that makes a reader distrust both. Quiet, so the
     figures stay on screen while the new ones are computed. */
  useEffect(() => {
    const onChange = () => load(true)
    window.addEventListener(POSITIONS_CHANGED, onChange)
    return () => window.removeEventListener(POSITIONS_CHANGED, onChange)
  }, [load])

  if (status === 'loading') {
    return (
      <section className="panel panel--pad" aria-busy="true" aria-label="Portfolio intelligence">
        <Skeleton height={18} width={210} style={{ marginBottom: 14 }} />
        <Skeleton height={96} />
      </section>
    )
  }

  if (status === 'error') {
    return (
      <section className="panel panel--pad" aria-labelledby="pf-intel-h">
        <h2 id="pf-intel-h" className="h-panel" style={{ marginBottom: 12 }}>
          Portfolio intelligence
        </h2>
        <EmptyState
          title="Book-level figures couldn't be computed"
          description="The persistence service didn't respond. Your positions are safe on the server — the table above is unaffected."
          action={
            <button type="button" className="btn btn--secondary btn--sm" onClick={() => load()}>
              Try again
            </button>
          }
        />
      </section>
    )
  }

  // No positions is not an error and not an empty state worth a dashed box —
  // the positions panel directly above already says the book is empty, and
  // repeating it here would be two empty states stacked.
  if (!data || !data.covered || !data.concentration) return null

  const { concentration: conc, coverage, risk, sectors, verdict_mix: mix } = data
  const maxWeight = conc.top_three[0]?.weight_pct ?? 100
  const maxRiskShare = risk?.top_contributors[0]?.risk_share_pct ?? 100
  const currency = data.currency ?? 'USD'
  const val = data.valuation
  const totals = val?.totals

  return (
    <section className="panel panel--pad pf" aria-labelledby="pf-intel-h">
      <header className="pf__head">
        <div>
          <h2 id="pf-intel-h" className="h-panel">Portfolio intelligence</h2>
          <p className="pf__lede">
            Book-level figures across {data.positions} position{data.positions === 1 ? '' : 's'}.
            Weights are {data.weight_basis} — not mark-to-market.
          </p>
        </div>
        <div className="pf__head-actions">
          <StatusPill tone={BAND_TONE[conc.band] ?? 'muted'} label={conc.band} />
          {/* The same provider path the watchlist refresh uses — one quote
              system, not two. */}
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => load(true)}
            disabled={refreshing}
            data-loading={refreshing || undefined}
          >
            {refreshing ? 'Refreshing…' : 'Refresh quotes'}
          </button>
        </div>
      </header>

      {/* ── valuation ─────────────────────────────────────────────────────
          Cost against today's market value. Every figure below the first
          card covers only the holdings that could actually be priced, which
          is why the coverage line exists rather than being implied. */}
      {totals && (
        <>
          <div className="pf__summary">
            <SummaryCard
              label="Total invested"
              value={money(totals.invested, currency)}
              sub={`${data.positions} position${data.positions === 1 ? '' : 's'}`}
            />
            <SummaryCard
              label="Current value"
              value={money(totals.current_value, currency)}
              sub={
                val && val.coverage.unpriced > 0
                  ? `${val.coverage.priced} of ${val.coverage.priced + val.coverage.unpriced} priced`
                  : 'marked to market'
              }
            />
            <SummaryCard
              label="Today"
              value={signedMoney(totals.day_pnl, currency)}
              sub={signedPct(totals.day_pnl_pct)}
              tone={toneOf(totals.day_pnl)}
            />
            <SummaryCard
              label="Total P&L"
              value={signedMoney(totals.pnl, currency)}
              sub={signedPct(totals.pnl_pct)}
              tone={toneOf(totals.pnl)}
            />
          </div>

          {val && val.coverage.unpriced > 0 && (
            <p className="pf__coverage">
              No current price for {val.coverage.unpriced_tickers.join(', ')} — those holdings are
              excluded from every valuation figure above, which therefore covers{' '}
              {val.coverage.priced_pct.toFixed(1)}% of the book&rsquo;s cost. They are not valued at
              their purchase price, which would report them as exactly break-even.
            </p>
          )}
        </>
      )}

      {/* ── performance ───────────────────────────────────────────────────
          Real closes, today's share counts. Absent rather than faked when
          the holdings do not share enough price history to plot. */}
      {data.curve && data.curve.points.length > 1 ? (
        <div className="pf__block pf__block--chart">
          <div className="pf__chart-head">
            <h3 className="pf__block-title">
              {data.benchmark ? `Portfolio vs ${data.benchmark.label}` : 'Value vs cost'}
            </h3>
            <div className="pf__chart-controls">
              {data.benchmarks && data.benchmarks.length > 0 && (
                <Segmented
                  label="Benchmark"
                  value={benchmark}
                  onChange={(next) => { setBenchmark(next); load(true, { benchmark: next }) }}
                  options={[
                    { value: 'none', label: 'Cost', title: 'Compare against what you paid' },
                    ...data.benchmarks.map((b) => ({
                      value: b.symbol, label: b.symbol, title: b.label,
                    })),
                  ]}
                />
              )}
              {data.ranges && (
                <Segmented
                  label="Range"
                  value={range}
                  onChange={(next) => { setRange(next); load(true, { range: next }) }}
                  options={data.ranges.map((r) => ({ value: r, label: r }))}
                />
              )}
            </div>
          </div>
          {/* Benchmark mode rebases both series to 100; cost mode plots money
              against the cost line. Two different questions, two axes. */}
          <PortfolioPerformanceChart
            curve={data.curve}
            currency={currency}
            benchmark={benchmark === 'none' ? null : data.benchmark}
          />
          {data.benchmark && benchmark !== 'none' && (
            <div className="pf__bench">
              <span className="pf__bench-cell">
                <span className="pf__bench-label">Portfolio</span>
                <span className={`num pf__bench-val pf__bench-val--${toneOf(data.benchmark.portfolio_return_pct)}`}>
                  {signedPct(data.benchmark.portfolio_return_pct)}
                </span>
              </span>
              <span className="pf__bench-cell">
                <span className="pf__bench-label">{data.benchmark.label}</span>
                <span className={`num pf__bench-val pf__bench-val--${toneOf(data.benchmark.benchmark_return_pct)}`}>
                  {signedPct(data.benchmark.benchmark_return_pct)}
                </span>
              </span>
              <span className="pf__bench-cell">
                <span className="pf__bench-label">Difference</span>
                <span className={`num pf__bench-val pf__bench-val--${toneOf(data.benchmark.outperformance_pct)}`}>
                  {signedPct(data.benchmark.outperformance_pct)}
                </span>
              </span>
            </div>
          )}
        </div>
      ) : val && val.rows.length > 0 ? (
        <p className="pf__block-note">
          Not enough overlapping price history across these holdings to plot a value
          curve. The valuation above is current and unaffected.
        </p>
      ) : null}

      {val && val.rows.length > 0 && <HoldingsTable rows={val.rows} currency={currency} />}

      {/* Prose first: each line fires on its own threshold, so a balanced
          book produces none of them rather than three sentences straining
          to find something alarming to say. */}
      {data.headlines && data.headlines.length > 0 && (
        <ul className="pf__notes">
          {data.headlines.map((note) => (
            <li key={note.text} className={`pf__note pf__note--${TONE_MAP[note.tone] ?? 'muted'}`}>
              {note.text}
            </li>
          ))}
        </ul>
      )}

      <div className="pf__grid">
        {/* ── concentration ───────────────────────────────────────────── */}
        <div className="pf__block">
          <h3 className="pf__block-title">Capital concentration</h3>
          <p className="pf__metric">
            <span className="num pf__metric-value">{conc.hhi.toFixed(0)}</span>
            <span className="pf__metric-unit">
              Herfindahl · {conc.band}
            </span>
          </p>
          <p className="pf__block-note">
            Sum of squared weights on a 0–10,000 scale. Below 1,500 is diversified,
            above 2,500 concentrated — the published competition-policy thresholds.
          </p>
          <ul className="pf__rows">
            {conc.top_three.map((row) => (
              <li key={row.ticker} className="pf__row">
                <CompanyMark ticker={row.ticker} size={18} />
                <span className="mono pf__row-name">{row.ticker}</span>
                <WeightBar pct={row.weight_pct} max={maxWeight} />
                <span className="num pf__row-val">{row.weight_pct.toFixed(1)}%</span>
              </li>
            ))}
          </ul>
        </div>

        {/* ── risk concentration ──────────────────────────────────────── */}
        {risk && risk.top_contributors.length > 0 && (
          <div className="pf__block">
            <h3 className="pf__block-title">Risk concentration</h3>
            <p className="pf__metric">
              <span className="num pf__metric-value">
                {risk.weighted_score !== null ? risk.weighted_score.toFixed(0) : '—'}
              </span>
              <span className="pf__metric-unit">weighted risk score</span>
            </p>
            {/* The disclaimer is part of the figure, not a footnote under it. */}
            <p className="pf__block-note">{risk.basis}.</p>
            <ul className="pf__rows">
              {risk.top_contributors.map((row) => (
                <li key={row.ticker} className="pf__row">
                  <CompanyMark ticker={row.ticker} size={18} />
                  <span className="mono pf__row-name">{row.ticker}</span>
                  <WeightBar pct={row.risk_share_pct} max={maxRiskShare} tone="neg" />
                  <span className="num pf__row-val">{row.risk_share_pct.toFixed(0)}%</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* ── measured risk ────────────────────────────────────────────
            From the same daily closes the curve is drawn from. Each figure
            is named for what it is: annualised stdev is called volatility,
            not "risk", and there is no Sharpe because there is no defensible
            risk-free series here to subtract. */}
        {risk && (risk.volatility_pct != null || risk.max_drawdown) && (
          <div className="pf__block">
            <h3 className="pf__block-title">Measured risk</h3>
            <div className="pf__stat-row">
              <span className="pf__stat">
                <span className="pf__stat-label">Volatility</span>
                <span className="num pf__stat-value">
                  {risk.volatility_pct != null ? `${risk.volatility_pct.toFixed(1)}%` : '—'}
                </span>
                <span className="pf__stat-sub">annualised</span>
              </span>
              <span className="pf__stat">
                <span className="pf__stat-label">Max drawdown</span>
                <span className="num pf__stat-value pf__stat-value--neg">
                  {risk.max_drawdown ? `${risk.max_drawdown.pct.toFixed(1)}%` : '—'}
                </span>
                {risk.max_drawdown && risk.max_drawdown.pct !== 0 && (
                  <span className="pf__stat-sub num">
                    {money(risk.max_drawdown.peak, currency, 0)} → {money(risk.max_drawdown.trough, currency, 0)}
                  </span>
                )}
              </span>
            </div>
            {risk.volatility_pct == null && (
              <p className="pf__block-note">
                Too few sessions in this range to annualise a standard deviation. Widen the
                range rather than reading a figure from a handful of days.
              </p>
            )}
            {risk.holding_drawdowns && risk.holding_drawdowns.length > 0 && (
              <ul className="pf__rows">
                {risk.holding_drawdowns.slice(0, 3).map((d) => (
                  <li key={d.ticker} className="pf__row">
                    <CompanyMark ticker={d.ticker} size={18} />
                    <span className="mono pf__row-name">{d.ticker}</span>
                    <WeightBar
                      pct={Math.abs(d.pct ?? 0)}
                      max={Math.abs(risk.holding_drawdowns?.[0]?.pct ?? 1)}
                      tone="neg"
                    />
                    <span className="num pf__row-val">{(d.pct ?? 0).toFixed(1)}%</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* ── correlation ──────────────────────────────────────────────
            Computed on returns, never on price levels: two stocks that both
            drift upward correlate at ~0.99 on levels regardless of whether
            their daily moves are related, which is the classic way to make a
            concentrated book look diversified. */}
        {data.correlation && data.correlation.pairs.length > 0 && (
          <div className="pf__block">
            <h3 className="pf__block-title">Diversification</h3>
            <p className="pf__metric">
              <span className="num pf__metric-value">{data.correlation.mean_rho.toFixed(2)}</span>
              <span className="pf__metric-unit">mean pairwise correlation</span>
            </p>
            <p className="pf__block-note">
              {data.correlation.high_count > 0
                ? `${data.correlation.high_count} pair${data.correlation.high_count === 1 ? '' : 's'} above 0.70 — those holdings move together, so they diversify each other less than their separate weights suggest.`
                : 'No pair above 0.70 in this window.'}
            </p>
            <ul className="pf__rows">
              {data.correlation.pairs.slice(0, 4).map((pair) => (
                <li key={`${pair.a}-${pair.b}`} className="pf__row pf__row--pair">
                  <span className="mono pf__row-name">{pair.a} ↔ {pair.b}</span>
                  <WeightBar pct={Math.max(0, pair.rho) * 100} max={100}
                             tone={pair.rho >= 0.7 ? 'neg' : 'accent'} />
                  <span className="num pf__row-val">{pair.rho.toFixed(2)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* ── contribution ─────────────────────────────────────────────
            Share of the book's P&L in money, not weight × return: money adds
            up once positions have moved and the weighted-return identity
            does not. */}
        {data.contributions && data.contributions.length > 0 && (
          <div className="pf__block">
            <h3 className="pf__block-title">P&amp;L contribution</h3>
            <ul className="pf__rows">
              {data.contributions.slice(0, 5).map((c) => (
                <li key={c.ticker} className="pf__row">
                  <CompanyMark ticker={c.ticker} size={18} />
                  <span className="mono pf__row-name">{c.ticker}</span>
                  <WeightBar
                    pct={c.share_of_movement_pct}
                    max={data.contributions?.[0]?.share_of_movement_pct}
                    tone={c.pnl >= 0 ? 'accent' : 'neg'}
                  />
                  <span className={`num pf__row-val pf__bench-val--${toneOf(c.pnl)}`}>
                    {signedMoney(c.pnl, currency)}
                  </span>
                </li>
              ))}
            </ul>
            <p className="pf__block-note">
              {data.contributions.some((c) => c.contribution_pct === null)
                ? 'Winners and losers roughly cancel, so shares of the net P&L are undefined — bars show share of total movement instead.'
                : `${data.contributions[0].ticker} accounts for ${Math.abs(data.contributions[0].contribution_pct ?? 0).toFixed(0)}% of the book's net P&L.`}
            </p>
          </div>
        )}

        {/* ── sector exposure ─────────────────────────────────────────── */}
        {sectors && sectors.rows.length > 0 && (
          <div className="pf__block">
            <h3 className="pf__block-title">Sector exposure</h3>
            <ul className="pf__rows pf__rows--tall">
              {sectors.rows.slice(0, 6).map((row) => (
                <li key={row.sector} className="pf__row">
                  <span className="pf__row-name pf__row-name--wide">{row.sector}</span>
                  <WeightBar pct={row.weight_pct} max={sectors.rows[0].weight_pct} />
                  <span className="num pf__row-val">{row.weight_pct.toFixed(1)}%</span>
                </li>
              ))}
            </ul>
            {sectors.unknown_pct > 0 && (
              <p className="pf__block-note">
                {sectors.unknown_pct.toFixed(1)}% of the book has no sector recorded and is
                excluded from this breakdown.
              </p>
            )}
          </div>
        )}

        {/* ── verdict mix ─────────────────────────────────────────────── */}
        {mix && (
          <div className="pf__block">
            <h3 className="pf__block-title">Verdict mix</h3>
            <p className="pf__block-note">
              Share of capital, not share of names — one large position outweighs two
              small ones, and the money is what is at stake.
            </p>
            <span className="pf__mix" role="img"
                  aria-label={`Bullish ${mix.bullish}%, neutral ${mix.neutral}%, bearish ${mix.bearish}%`}>
              {(['bullish', 'neutral', 'bearish'] as const).map((k) =>
                mix[k] > 0 ? (
                  <span key={k} className={`pf__mix-seg pf__mix-seg--${k}`} style={{ flexGrow: mix[k] }} />
                ) : null,
              )}
            </span>
            <ul className="pf__legend">
              {(['bullish', 'neutral', 'bearish'] as const).map((k) => (
                <li key={k} className={`pf__legend-item pf__legend-item--${k}`}>
                  <span className="pf__legend-dot" aria-hidden />
                  {k} <span className="num">{mix[k].toFixed(1)}%</span>
                </li>
              ))}
            </ul>
            {coverage && coverage.unscored > 0 && (
              <p className="pf__block-note">
                Excludes {coverage.unscored} unanalysed position
                {coverage.unscored === 1 ? '' : 's'}: {coverage.unscored_tickers.join(', ')}.
              </p>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
