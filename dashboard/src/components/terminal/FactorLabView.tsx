'use client'

/**
 * Factor Lab — cross-sectional evidence for the scoring engine's factors.
 *
 * Every other view in OmniSignal examines one stock. That shape cannot answer
 * the question a factor actually makes: it does not claim NVDA will rise, it
 * claims names it ranks highly will outperform names it ranks poorly. Judging
 * that one ticker at a time cannot separate a working factor from a market
 * that went up.
 *
 * The design decision that shapes this page: **the naive and corrected
 * t-statistics are shown together, always.** Forward returns overlap between
 * observation dates, which inflates the uncomfortable statistic and flatters
 * the factor. Showing only the corrected number would be honest; showing both
 * teaches why the correction exists, and makes the gap impossible to miss.
 *
 * The page is expected to report that factors are *not* significant. That is
 * a finding, rendered as neutrally as a positive one — a research tool whose
 * UI only looks good when the answer is favourable is a marketing tool.
 */

import { useEffect, useMemo, useState } from 'react'
import PageHeader from '@/components/ui/PageHeader'
import Section from '@/components/ui/Section'
import { FACTOR_LABELS } from '@/lib/history'

interface FactorEvaluation {
  factor: string
  mean_ic: number
  std_ic: number
  t_stat: number
  naive_t_stat: number
  overlap_inflation: number
  newey_west_lags: number
  hit_rate: number
  dates: number
  names_median: number
  top_minus_bottom: number | null
  quantiles: number
  saturation: number
  significant: boolean
  assessment: string
  ic_series: Array<[string, number]>
  portfolio: Portfolio | null
  stability: Stability | null
}

interface Portfolio {
  buckets: number
  rebalances: number
  total_return: number
  annualised_return: number
  annualised_volatility: number
  sharpe: number
  max_drawdown: number
  hit_rate: number
  turnover: number
  long_leg_return: number
  short_leg_return: number
  benchmark_return: number
  beat_benchmark: boolean
  assessment: string
  equity_curve: Array<{ date: string; strategy: number; benchmark: number }>
}

interface Stability {
  window: number
  rolling: Array<{ date: string; ic: number }>
  first_half_ic: number | null
  second_half_ic: number | null
  best_window: { start: string; end: string; mean_ic: number } | null
  worst_window: { start: string; end: string; mean_ic: number } | null
  concentration: number
  sign_flips: number
  decayed: boolean
  assessment: string
}

interface RankRow {
  rank: number
  symbol: string
  score: number
  percentile: number
  forward_return: number | null
}

interface ScreenRow {
  rank: number
  symbol: string
  composite: number
  agreement: number
  conviction: 'aligned' | 'mixed' | 'conflicted'
  factors_used: number
  percentiles: Record<string, number>
  strongest: string | null
  weakest: string | null
}

interface AttributionData {
  factors: string[]
  factor_returns: Record<string, number>
  t_stats: Record<string, number>
  mean_r_squared: number
  mean_adjusted_r_squared: number
  overfit_gap: number
  names_median: number
  unexplained_share: number
  dates: number
  assessment: string
}

interface RedundancyData {
  factors: string[]
  matrix: Array<Array<number | null>>
  effective_factors: number
  redundant_pairs: Array<{ a: string; b: string; correlation: number }>
  dates: number
  assessment: string
}

interface FactorLab {
  universe: { name: string; symbols: string[]; point_in_time_membership: boolean }
  window: {
    start: string; end: string; observation_dates: number
    evaluable_cells: number; step_days: number; horizon_days: number
  }
  factors: FactorEvaluation[]
  latest_cross_section: { date: string; factors: Record<string, RankRow[]> }
  redundancy: RedundancyData | null
  attribution: AttributionData | null
  screen: {
    date: string
    dispersion: { composite_spread: number; mean_agreement: number }
    rows: ScreenRow[]
  }
  caveats: string[]
  engine_version: string
  build_seconds: number
  cached: boolean
  error?: string
}

const label = (name: string) => FACTOR_LABELS[name] ?? name

/** Colour states a fact about the data, never a mood: sign of the effect. */
function icTone(value: number): string {
  if (value > 0.02) return 'badge--pos'
  if (value < -0.02) return 'badge--neg'
  return 'badge--neutral'
}

function Stat({ label: text, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="metric-row">
      <span className="label">{text}</span>
      <span className="num" title={hint}>{value}</span>
    </div>
  )
}

/**
 * The centrepiece: naive versus corrected, side by side, with the shrink
 * drawn to scale. A number that moved from 1.70 to 1.16 is abstract; a bar
 * that visibly retreats past the significance line is not.
 */
function TStatBar({ evaluation }: { evaluation: FactorEvaluation }) {
  const scale = 3.0
  const width = (t: number) => `${Math.min(100, (Math.abs(t) / scale) * 100)}%`
  const threshold = `${(2.0 / scale) * 100}%`

  return (
    <div style={{ position: 'relative', padding: '6px 0' }}>
      <div style={{
        position: 'absolute', left: threshold, top: 0, bottom: 0, width: 1,
        background: 'var(--border-strong, #999)', zIndex: 1,
      }} aria-hidden />
      {([
        ['uncorrected', evaluation.naive_t_stat, 'var(--text-subtle, #999)'],
        ['Newey–West', evaluation.t_stat, 'var(--accent, #2f6feb)'],
      ] as const).map(([name, value, colour]) => (
        <div key={name} style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '3px 0' }}>
          <span className="label" style={{ width: 92, fontSize: '0.6875rem', flexShrink: 0 }}>
            {name}
          </span>
          <div style={{ flex: 1, height: 10, background: 'var(--surface-2, #f0f0f0)', borderRadius: 2 }}>
            <div style={{ width: width(value), height: '100%', background: colour, borderRadius: 2 }} />
          </div>
          <span className="num" style={{ width: 46, textAlign: 'right', fontSize: '0.75rem' }}>
            {value.toFixed(2)}
          </span>
        </div>
      ))}
      <div className="label" style={{ fontSize: '0.6875rem', marginTop: 4, opacity: 0.75 }}>
        vertical line = |t| 2.0 · overlap inflated the raw statistic{' '}
        {evaluation.overlap_inflation.toFixed(2)}× ({evaluation.newey_west_lags} lags)
      </div>
    </div>
  )
}

/** IC per observation date. Sparkline, because the shape is the point:
 *  a factor with mean IC 0.04 that alternates ±0.35 is not the same
 *  animal as one that is quietly positive every week. */
function IcSparkline({ series }: { series: Array<[string, number]> }) {
  if (series.length < 2) return null
  const values = series.map(([, v]) => v)
  const bound = Math.max(0.5, ...values.map(Math.abs))
  const width = 100
  const height = 28
  const points = values
    .map((v, i) => `${(i / (values.length - 1)) * width},${height / 2 - (v / bound) * (height / 2)}`)
    .join(' ')

  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height}
         preserveAspectRatio="none" role="img"
         aria-label={`Rank IC across ${series.length} observation dates`}>
      <line x1="0" y1={height / 2} x2={width} y2={height / 2}
            stroke="var(--border, #ddd)" strokeWidth="0.5" />
      <polyline points={points} fill="none" strokeWidth="1"
                stroke="var(--accent, #2f6feb)" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

/**
 * How much of what actually happened the factors account for.
 *
 * The unexplained share is deliberately the largest number on this panel. An
 * R² tucked into a corner invites nobody to look; "the factors explain 4% of
 * the cross-section" is a sentence a reader cannot skip past.
 */
function AttributionPanel({ attribution }: { attribution: AttributionData }) {
  const explained = 1 - attribution.unexplained_share
  const ordered = [...attribution.factors].sort(
    (x, y) => Math.abs(attribution.t_stats[y]) - Math.abs(attribution.t_stats[x]),
  )
  return (
    <section className="panel" style={{ padding: '20px 22px' }} aria-label="Return attribution">
      <h2 className="h-panel">How much of what happened do the factors explain?</h2>
      <p className="body-copy" style={{ marginTop: 4, marginBottom: 12, maxWidth: '68ch' }}>
        Each date&rsquo;s cross-section of returns regressed on that date&rsquo;s
        factor exposures, one date at a time, then averaged. Doing it per date
        rather than pooling matters: pooled, a day when everything rose would
        masquerade as a factor return.
      </p>

      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10 }}>
        <span className="display" style={{ fontSize: '2rem', lineHeight: 1 }}>
          {(attribution.unexplained_share * 100).toFixed(0)}%
        </span>
        <span className="label">unexplained — {attribution.assessment}</span>
      </div>
      <div style={{ height: 10, background: 'var(--surface-2, #f0f0f0)', borderRadius: 2, marginBottom: 14 }}>
        <div style={{ width: `${Math.max(0, explained) * 100}%`, height: '100%',
                      background: 'var(--accent, #2f6feb)', borderRadius: 2 }} />
      </div>

      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">Factor</th>
            <th scope="col" style={{ textAlign: 'right' }}>Mean return per 1σ</th>
            <th scope="col" style={{ textAlign: 'right' }}>t</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((factor) => (
            <tr key={factor}>
              <td>{label(factor)}</td>
              <td className="num" style={{ textAlign: 'right' }}>
                {(attribution.factor_returns[factor] * 100).toFixed(3)}%
              </td>
              <td className="num" style={{ textAlign: 'right' }}>
                {attribution.t_stats[factor].toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="label" style={{ marginTop: 8, fontSize: '0.6875rem' }}>
        Exposures are z-scored within each date, so a coefficient is the return
        to a one-standard-deviation tilt. {attribution.dates} dates,{' '}
        {attribution.names_median} names each. Raw R² is{' '}
        {(attribution.mean_r_squared * 100).toFixed(0)}%; the figure above is
        adjusted for {attribution.factors.length} predictors, which removes{' '}
        {(attribution.overfit_gap * 100).toFixed(0)} points of fit that
        {attribution.factors.length} free parameters would produce on this many
        names by chance alone.
      </p>
    </section>
  )
}

/**
 * Correlation heat map. Sized by |correlation| rather than coloured on a
 * rainbow: the question is "how much do these two overlap", and a single
 * saturation axis answers it without asking the reader to decode a legend.
 */
function RedundancyPanel({ redundancy }: { redundancy: RedundancyData }) {
  const { factors, matrix } = redundancy
  const ratio = redundancy.effective_factors / factors.length
  return (
    <section className="panel" style={{ padding: '20px 22px' }} aria-label="Factor redundancy">
      <h2 className="h-panel">Seven factors, or fewer?</h2>
      <p className="body-copy" style={{ marginTop: 4, marginBottom: 12, maxWidth: '68ch' }}>
        The screen above averages every factor equally, which assumes each one
        contributes something new. Three of them are the same statistic over
        different horizons. {redundancy.assessment}.
        {ratio < 0.7 && ' Equal weighting therefore over-votes whichever family is duplicated.'}
      </p>

      <div style={{ overflowX: 'auto' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col" />
              {factors.map((f) => (
                <th key={f} scope="col" style={{ textAlign: 'center', fontSize: '0.6875rem' }}>
                  {f}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {factors.map((rowFactor, i) => (
              <tr key={rowFactor}>
                <th scope="row" className="label" style={{ whiteSpace: 'nowrap' }}>
                  {label(rowFactor)}
                </th>
                {factors.map((colFactor, j) => {
                  const v = matrix[i]?.[j]
                  const strength = v === null || v === undefined ? 0 : Math.abs(v)
                  return (
                    <td key={colFactor} className="num"
                        style={{
                          textAlign: 'center',
                          background: v === null || v === undefined
                            ? 'transparent'
                            : `color-mix(in srgb, var(--accent, #2f6feb) ${Math.round(strength * 70)}%, transparent)`,
                        }}
                        title={`${label(rowFactor)} vs ${label(colFactor)}: ${v ?? 'n/a'}`}>
                      {v === null || v === undefined ? '—' : v.toFixed(2)}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {redundancy.redundant_pairs.length > 0 && (
        <p className="body-copy" style={{ marginTop: 10, fontSize: '0.8125rem' }}>
          Substantially redundant:{' '}
          {redundancy.redundant_pairs
            .map((p) => `${label(p.a)} / ${label(p.b)} (${p.correlation.toFixed(2)})`)
            .join(' · ')}
        </p>
      )}
    </section>
  )
}

/** Rolling IC. Zero line drawn because the sign is the question:
 *  a curve that spends the recent half below it is a dead factor,
 *  and no summary statistic shows that as fast as the shape does. */
function RollingIc({ rolling }: { rolling: Stability['rolling'] }) {
  if (rolling.length < 2) return null
  const values = rolling.map((p) => p.ic)
  const bound = Math.max(0.05, ...values.map(Math.abs))
  const w = 100
  const h = 34
  const y = (v: number) => h / 2 - (v / bound) * (h / 2)
  const points = values.map((v, i) => `${(i / (values.length - 1)) * w},${y(v)}`).join(' ')

  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={52} preserveAspectRatio="none"
         role="img" aria-label={`Rolling ${rolling.length}-point mean information coefficient`}>
      <line x1="0" y1={h / 2} x2={w} y2={h / 2} stroke="var(--border-strong, #999)" strokeWidth="0.5" />
      <polyline points={points} fill="none" strokeWidth="1.5"
                stroke="var(--accent, #2f6feb)" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

function StabilityPanel({ stability }: { stability: Stability }) {
  return (
    <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--border, #e5e5e5)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
        <span className="label">Rolling {stability.window}-period mean IC</span>
        {stability.decayed && <span className="badge badge--warn">stopped working</span>}
      </div>
      <p className="body-copy" style={{ margin: '6px 0 4px' }}>{stability.assessment}</p>
      <RollingIc rolling={stability.rolling} />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginTop: 4 }}>
        {stability.first_half_ic !== null && (
          <>
            <Stat label="First half" value={stability.first_half_ic.toFixed(4)} />
            <Stat label="Second half" value={(stability.second_half_ic ?? 0).toFixed(4)} />
          </>
        )}
        <Stat label="Edge concentration" value={`${(stability.concentration * 100).toFixed(0)}%`}
              hint="Share of total IC contributed by the single best window. High means the edge lives in one stretch." />
        <Stat label="Sign flips" value={String(stability.sign_flips)}
              hint="Times the rolling mean crossed zero" />
      </div>
    </div>
  )
}

const pct = (v: number) => `${(v * 100).toFixed(1)}%`

/** Strategy against the equal-weight universe. Both lines, always: a
 *  long/short curve that merely tracks the benchmark is a market bet wearing
 *  a factor's name, and one line alone cannot show that. */
function EquityCurve({ curve }: { curve: Portfolio['equity_curve'] }) {
  if (curve.length < 2) return null
  const all = curve.flatMap((p) => [p.strategy, p.benchmark])
  const low = Math.min(...all)
  const high = Math.max(...all)
  const span = high - low || 1
  const w = 100
  const h = 46
  const path = (key: 'strategy' | 'benchmark') =>
    curve
      .map((p, i) => `${(i / (curve.length - 1)) * w},${h - ((p[key] - low) / span) * h}`)
      .join(' ')

  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={72} preserveAspectRatio="none"
         role="img" aria-label="Cumulative return of the long/short portfolio versus the equal-weight universe">
      <polyline points={path('benchmark')} fill="none" strokeWidth="1"
                stroke="var(--text-subtle, #999)" strokeDasharray="2 2"
                vectorEffect="non-scaling-stroke" />
      <polyline points={path('strategy')} fill="none" strokeWidth="1.5"
                stroke="var(--accent, #2f6feb)" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

function PortfolioPanel({ portfolio }: { portfolio: Portfolio }) {
  return (
    <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--border, #e5e5e5)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
        <span className="label">
          Long top / short bottom {portfolio.buckets === 5 ? 'quintile' : `1/${portfolio.buckets}`},
          rebalanced weekly
        </span>
        <span className={`badge ${portfolio.total_return > 0 ? 'badge--pos' : 'badge--neg'}`}>
          {pct(portfolio.total_return)}
        </span>
      </div>
      <p className="body-copy" style={{ margin: '6px 0 8px' }}>{portfolio.assessment}</p>
      <EquityCurve curve={portfolio.equity_curve} />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginTop: 6 }}>
        <Stat label="Sharpe" value={portfolio.sharpe.toFixed(2)}
              hint="Annualised return divided by annualised volatility. No autocorrelation correction is needed: holding periods do not overlap." />
        <Stat label="Max drawdown" value={pct(portfolio.max_drawdown)} />
        <Stat label="Turnover" value={pct(portfolio.turnover)}
              hint="Share of the book replaced at each rebalance. Trading costs are not modelled." />
        <Stat label="Long leg" value={pct(portfolio.long_leg_return)} />
        <Stat label="Short leg" value={pct(portfolio.short_leg_return)} />
        <Stat label="Universe (equal weight)" value={pct(portfolio.benchmark_return)} />
      </div>
      {!portfolio.beat_benchmark && (
        <p className="body-copy" style={{ fontSize: '0.75rem', marginTop: 6 }}>
          Did not beat simply holding the universe equally weighted — before any
          trading costs, which at {pct(portfolio.turnover)} turnover per week are
          not small.
        </p>
      )}
    </div>
  )
}

const CONVICTION_TONE: Record<ScreenRow['conviction'], string> = {
  aligned: 'badge--pos',
  mixed: 'badge--neutral',
  conflicted: 'badge--warn',
}

/**
 * The composite screen. Its most useful column is not the rank — it is
 * `conviction`: two names can share an identical composite while one has
 * every factor agreeing and the other is split down the middle. The mean
 * cannot tell them apart; this can.
 */
function ScreenTable({ rows, dispersion: spread }: {
  rows: ScreenRow[]
  dispersion: { composite_spread: number; mean_agreement: number }
}) {
  if (!rows.length) {
    return <p className="body-copy">No names had enough factors to rank on this date.</p>
  }
  const flat = spread.composite_spread < 20
  return (
    <>
      {flat && (
        <p className="body-copy" style={{ marginBottom: 10 }}>
          The universe is barely differentiated today — only{' '}
          {spread.composite_spread.toFixed(0)} percentile points separate the
          best-ranked name from the worst. The ordering below is close to noise.
        </p>
      )}
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">#</th>
            <th scope="col">Symbol</th>
            <th scope="col" style={{ textAlign: 'right' }}>Composite</th>
            <th scope="col">Factors</th>
            <th scope="col">Strongest</th>
            <th scope="col">Weakest</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.symbol}>
              <td className="num">{row.rank}</td>
              <td><a href={`/company/${row.symbol}`}>{row.symbol}</a></td>
              <td className="num" style={{ textAlign: 'right' }}>{row.composite.toFixed(0)}</td>
              <td>
                <span className={`badge ${CONVICTION_TONE[row.conviction]}`}
                      title={`Factor agreement ${(row.agreement * 100).toFixed(0)}% across ${row.factors_used} factors`}>
                  {row.conviction}
                </span>
              </td>
              <td className="label">{row.strongest ? label(row.strongest) : '—'}</td>
              <td className="label">{row.weakest ? label(row.weakest) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

function CrossSection({ rows, horizon }: { rows: RankRow[]; horizon: number }) {
  if (!rows.length) {
    return <p className="body-copy">No ranking available for this factor on the latest date.</p>
  }
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th scope="col">#</th>
          <th scope="col">Symbol</th>
          <th scope="col" style={{ textAlign: 'right' }}>Score</th>
          <th scope="col" style={{ textAlign: 'right' }}>Percentile</th>
          <th scope="col" style={{ textAlign: 'right' }}>Next {horizon}d</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.symbol}>
            <td className="num">{row.rank}</td>
            <td><a href={`/company/${row.symbol}`}>{row.symbol}</a></td>
            <td className="num" style={{ textAlign: 'right' }}>{row.score.toFixed(3)}</td>
            <td className="num" style={{ textAlign: 'right' }}>{row.percentile.toFixed(0)}</td>
            <td className="num" style={{ textAlign: 'right' }}>
              {row.forward_return === null
                ? <span style={{ opacity: 0.5 }}>not yet known</span>
                : `${(row.forward_return * 100).toFixed(2)}%`}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/** One settled fetch, tagged with the universe it describes.
 *
 *  Loading is *derived* from that tag rather than held in its own state and
 *  flipped at the top of the effect. That keeps every `setState` inside an
 *  async callback — no synchronous state write during an effect body, so no
 *  cascading render — and it removes the class of bug where a slow response
 *  for universe A lands after the user has already switched to B. */
interface Settled {
  universe: string
  data: FactorLab | null
  error: string | null
}

/* ── loading and failure ──────────────────────────────────────────────────── */

const BUILD_STEPS = [
  ['Fetching price history', 'every symbol in the universe, through the provider fallback chain'],
  ['Building the point-in-time panel', 'each factor recomputed from a window truncated at its own date'],
  ['Loading SEC filings', 'point-in-time fundamentals, dated by when each figure was published'],
  ['Measuring forward returns', 'what actually happened after each observation date'],
  ['Running the estimators', 'rank IC, Newey\u2013West correction, portfolios, attribution'],
] as const

/**
 * A cold build genuinely takes 30-60 seconds, most of it waiting on vendors.
 * A bare spinner for that long reads as broken, so this narrates the actual
 * pipeline and advances through it on a timer calibrated to the measured
 * stage durations. The steps are real and in execution order; the timing is
 * an estimate, and the footer says so rather than implying live progress.
 */
function BuildingPanel({ universe }: { universe: string }) {
  const [step, setStep] = useState(0)
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const tick = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(tick)
  }, [])

  useEffect(() => {
    if (step >= BUILD_STEPS.length - 1) return
    const advance = setTimeout(() => setStep((s) => s + 1), step === 0 ? 9000 : 7000)
    return () => clearTimeout(advance)
  }, [step])

  return (
    <div className="lab-state">
      <span className="eyebrow">Factor Lab</span>
      <h2 className="lab-state__title">Measuring every factor against what actually happened</h2>
      <p className="lab-state__lede">
        Building a point-in-time panel for <strong>{universe}</strong>, then testing each factor
        across the whole cross-section. The first run fetches full price history &mdash; later
        runs are instant for an hour.
      </p>

      <ol className="lab-steps">
        {BUILD_STEPS.map(([title, detail], index) => (
          <li key={title}
              className={`lab-steps__item${index < step ? ' is-done' : ''}${index === step ? ' is-active' : ''}`}>
            <span className="lab-steps__mark" aria-hidden>{index < step ? '\u2713' : ''}</span>
            <span className="lab-steps__text">
              <strong>{title}</strong>
              <span>{detail}</span>
            </span>
          </li>
        ))}
      </ol>

      <p className="lab-state__foot">
        {elapsed}s elapsed &middot; typically 30&ndash;60s cold. Stage timings are estimated, not live.
      </p>
    </div>
  )
}

/**
 * Failures here are usually one of three specific, explainable things.
 * A raw backend string tells a user nothing they can act on, so each known
 * cause gets its own explanation and its own next step.
 */
function LabError({ message, universe, onRetry, onSwitch }: {
  message: string; universe: string
  onRetry: () => void; onSwitch: (u: string) => void
}) {
  const tooSmall = /at least \d+ names|symbols; cross-sectional/i.test(message)
  const noReturns = /forward returns/i.test(message)
  const noPanel = /no panel data/i.test(message)

  const title = tooSmall ? 'This universe is too small to rank'
    : noReturns ? 'Not enough history has elapsed yet'
    : noPanel ? 'No price history could be assembled'
    : 'The factor evaluation could not complete'

  const explanation = tooSmall
    ? `A rank correlation across ${universe} is noise rather than a ranking \u2014 cross-sectional evidence needs at least ten names on every date. Rather than show a number that would look real, the lab reports nothing.`
    : noReturns
    ? 'Every observation date needs a realised forward return to measure against, and none of the requested window has closed yet. A longer window will have some.'
    : noPanel
    ? 'Price history for this universe could not be fetched. That is usually a vendor being rate-limited or briefly unavailable, and it normally clears within a minute.'
    : `Something upstream failed while assembling the panel. The server logs have the detail; the message returned was: \u201c${message}\u201d`

  return (
    <div className="lab-state">
      <span className="eyebrow">Factor Lab</span>
      <h2 className="lab-state__title">{title}</h2>
      <p className="lab-state__lede">{explanation}</p>
      <div className="lab-state__actions">
        {tooSmall
          ? (
            <button type="button" className="btn btn--primary btn--sm" onClick={() => onSwitch('mega30')}>
              Use mega30 instead
            </button>
          ) : (
            <button type="button" className="btn btn--primary btn--sm" onClick={onRetry}>
              Try again
            </button>
          )}
        <a className="btn btn--ghost btn--sm" href="/terminal/methodology">How the engine works</a>
      </div>
    </div>
  )
}

export default function FactorLabView() {
  const [universe, setUniverse] = useState('mega30')
  const [settled, setSettled] = useState<Settled | null>(null)
  const [selected, setSelected] = useState<string | null>(null)

  const loading = settled === null || settled.universe !== universe
  const data = loading ? null : settled.data
  const error = loading ? null : settled.error

  useEffect(() => {
    const controller = new AbortController()
    fetch(`/api/factors?universe=${encodeURIComponent(universe)}`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((json: FactorLab) => {
        if (json.error) { setSettled({ universe, data: null, error: json.error }); return }
        setSettled({ universe, data: json, error: null })
        setSelected((current) => current ?? json.factors[0]?.factor ?? null)
      })
      .catch((e) => {
        if (e.name !== 'AbortError') {
          setSettled({ universe, data: null, error: String(e.message ?? e) })
        }
      })
    return () => controller.abort()
  }, [universe])

  const anySignificant = useMemo(
    () => Boolean(data?.factors.some((f) => f.significant)),
    [data],
  )

  if (loading) return <BuildingPanel universe={universe} />

  if (error) {
    return (
      <LabError message={error} universe={universe}
                onRetry={() => setSettled(null)} onSwitch={setUniverse} />
    )
  }

  if (!data) return null

  const selectedEvaluation = data.factors.find((f) => f.factor === selected) ?? null

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Factor Lab"
        title="Does the engine&rsquo;s ranking predict anything?"
        lede={`A factor does not claim one stock will rise. It claims the names it ranks highly will outperform the names it ranks poorly. This measures exactly that, across ${data.universe.symbols.length} names and ${data.window.observation_dates} observation dates, using only information that was knowable on each date.`}
        actions={
          <>
            <label htmlFor="lab-universe" className="visually-hidden">Universe to evaluate</label>
            <select id="lab-universe" className="input" value={universe}
                    onChange={(event) => setUniverse(event.target.value)}>
              <option value="dev">dev (5 names)</option>
              <option value="mega30">mega30 (30 names)</option>
            </select>
          </>
        }
        meta={
          <>
            <span>{data.window.start} &rarr; {data.window.end}</span>
            <span>{data.window.horizon_days}-day horizon</span>
            <span>{data.window.evaluable_cells.toLocaleString()} evaluable cells</span>
            <span>{data.engine_version}</span>
          </>
        }
      />

      <p className="lab-headline">
        {anySignificant
          ? 'At least one factor clears |t| 2.0 after correcting for overlapping windows — read it against the multiple-comparison caveat below.'
          : 'No factor clears |t| 2.0 after correcting for overlapping windows. On this sample there is no statistical evidence that these rankings predict forward returns.'}
      </p>

      <section className="panel" style={{ padding: '20px 22px' }} aria-label="Factor evidence">
        <h2 className="h-panel">Evidence, factor by factor</h2>
        <p className="body-copy" style={{ marginTop: 4, marginBottom: 14, maxWidth: '68ch' }}>
          Rank IC is the correlation between a factor&rsquo;s ordering on a date and
          what actually happened next. Both t-statistics are shown: the raw one, and
          the one corrected for the fact that {data.window.horizon_days}-day returns
          sampled every {data.window.step_days} days overlap heavily.
        </p>

        <div style={{ display: 'grid', gap: 14 }}>
          {data.factors.map((evaluation) => (
            <article
              key={evaluation.factor}
              className="card"
              style={{
                padding: '14px 16px', cursor: 'pointer',
                outline: selected === evaluation.factor ? '2px solid var(--accent, #2f6feb)' : 'none',
              }}
              onClick={() => setSelected(evaluation.factor)}
              onKeyDown={(e) => { if (e.key === 'Enter') setSelected(evaluation.factor) }}
              tabIndex={0}
              role="button"
              aria-pressed={selected === evaluation.factor}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                <strong>{label(evaluation.factor)}</strong>
                <span className={`badge ${icTone(evaluation.mean_ic)}`}>
                  IC {evaluation.mean_ic >= 0 ? '+' : ''}{evaluation.mean_ic.toFixed(4)}
                </span>
              </div>

              <p className="body-copy" style={{ margin: '6px 0 8px' }}>{evaluation.assessment}</p>
              <TStatBar evaluation={evaluation} />

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginTop: 8 }}>
                <Stat label="Hit rate" value={`${(evaluation.hit_rate * 100).toFixed(0)}%`}
                      hint="Share of dates where the IC was positive" />
                <Stat
                  label={`Top−bottom (${evaluation.quantiles} buckets)`}
                  value={evaluation.top_minus_bottom === null
                    ? '—'
                    : `${(evaluation.top_minus_bottom * 100).toFixed(2)}%`}
                  hint="Mean forward return of the top bucket minus the bottom"
                />
                <Stat label="Dates" value={String(evaluation.dates)} />
                <Stat label="Names / date" value={String(evaluation.names_median)} />
                <Stat
                  label="Clipped at bound"
                  value={`${(evaluation.saturation * 100).toFixed(0)}%`}
                  hint="Share of scores sitting exactly on the winsorization bound. Those names carry an identical score, so the factor does not rank them relative to each other."
                />
              </div>
              {evaluation.saturation > 0.15 && (
                <p className="body-copy" style={{ fontSize: '0.75rem', marginTop: 6 }}>
                  {(evaluation.saturation * 100).toFixed(0)}% of scores sit on the
                  winsorization bound, so this factor does not distinguish between
                  those names — ordering information is discarded at exactly the end
                  a long/short reading depends on.
                </p>
              )}
              <IcSparkline series={evaluation.ic_series} />
              {evaluation.stability && <StabilityPanel stability={evaluation.stability} />}
              {evaluation.portfolio && <PortfolioPanel portfolio={evaluation.portfolio} />}
            </article>
          ))}
        </div>
      </section>

      {data.attribution && <AttributionPanel attribution={data.attribution} />}
      {data.redundancy && <RedundancyPanel redundancy={data.redundancy} />}

      <section className="panel" style={{ padding: '20px 22px' }} aria-label="Composite screen">
        <h2 className="h-panel">The universe today, ranked — and where the factors disagree</h2>
        <p className="body-copy" style={{ marginTop: 4, marginBottom: 12, maxWidth: '68ch' }}>
          Every name scored on the mean of its factor percentiles on{' '}
          {data.screen.date}. Weights are equal on purpose: none of these factors
          is statistically significant above, so weighting by measured IC would be
          fitting to noise. <strong>Read the conviction column before the rank</strong> —
          two names can share a composite while one has every factor agreeing and
          the other is split down the middle.
        </p>
        <ScreenTable rows={data.screen.rows} dispersion={data.screen.dispersion} />
      </section>

      {selectedEvaluation && (
        <section className="panel" style={{ padding: '20px 22px' }} aria-label="Latest cross-section">
          <h2 className="h-panel">
            {label(selectedEvaluation.factor)} — every name, ranked on {data.latest_cross_section.date}
          </h2>
          <p className="body-copy" style={{ marginTop: 4, marginBottom: 12, maxWidth: '68ch' }}>
            The view the panel&rsquo;s layout exists to serve: one factor column read
            across the whole universe on a single date. Forward returns are blank
            where the {data.window.horizon_days}-day window has not finished yet —
            absent, not zero.
          </p>
          <CrossSection
            rows={data.latest_cross_section.factors[selectedEvaluation.factor] ?? []}
            horizon={data.window.horizon_days}
          />
        </section>
      )}

      <Section
        id="factor-lab-caveats"
        title="How to read these numbers"
        summary={`${data.caveats.length} caveats`}
        defaultOpen
      >
        <ul style={{ display: 'grid', gap: 10, paddingLeft: 18 }}>
          {data.caveats.map((caveat) => (
            <li key={caveat} className="body-copy">{caveat}</li>
          ))}
        </ul>
      </Section>
    </div>
  )
}
