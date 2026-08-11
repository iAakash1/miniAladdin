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
import ResearchLoader, { FACTOR_LAB_STAGES } from '@/components/ui/ResearchLoader'
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

/** While a build runs the endpoint answers with progress, not the payload. */
interface BuildProgress {
  status: 'building'
  stage: string
  stage_index: number
  stages: string[]
  progress_done: number
  progress_total: number
  elapsed_seconds: number
}

interface FactorLab {
  status?: 'ready' | 'error'
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
  /** Estimators that raised. Present and empty on a clean build; a
   *  non-empty list means the page is showing real but partial results. */
  degraded?: Array<{ estimator: string; reason: string }>
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

export type EvidenceFilter = 'all' | 'significant' | 'inconclusive'

interface FilterableFactor { significant: boolean }

/** Split the evidence by what it actually concluded.
 *
 *  Eight factor cards read as eight equal claims, but they are not: some
 *  cleared |t| 2.0 after the overlap correction and most did not. Filtering
 *  is the fastest way to answer "what survived?" — and, deliberately, also
 *  "what failed?", because a lab that can only show its winners is a
 *  marketing page. Neither view is the default; `all` is, so nothing is
 *  hidden until the reader chooses to narrow. */
export function filterEvidence<T extends FilterableFactor>(
  factors: T[], filter: EvidenceFilter,
): T[] {
  if (filter === 'all') return factors
  const want = filter === 'significant'
  return factors.filter((f) => f.significant === want)
}

/** Two factors, the same statistics, side by side.
 *
 *  Reading two factor cards means scrolling between them and holding eleven
 *  numbers in your head. This pins the ones that decide whether a factor is
 *  worth anything and puts them on one line each, so the comparison is
 *  horizontal rather than remembered. Every value is the same figure the
 *  card shows — nothing is recomputed here.
 *
 *  The winning side of each row is marked, but only where "better" is
 *  actually defined: a higher |t| and a higher hit rate are better, while
 *  more observation dates is context rather than merit.
 */
function FactorCompare({
  factors, onClear,
}: {
  factors: FactorEvaluation[]
  onClear: () => void
}) {
  const rows: Array<{ label: string; get: (f: FactorEvaluation) => string; better?: (f: FactorEvaluation) => number }> = [
    { label: 'Mean rank IC', get: (f) => `${f.mean_ic >= 0 ? '+' : ''}${f.mean_ic.toFixed(4)}`, better: (f) => Math.abs(f.mean_ic) },
    { label: 'Newey–West t', get: (f) => f.t_stat.toFixed(2), better: (f) => Math.abs(f.t_stat) },
    { label: 'Uncorrected t', get: (f) => f.naive_t_stat.toFixed(2) },
    { label: 'Overlap inflation', get: (f) => `${f.overlap_inflation.toFixed(2)}x` },
    { label: 'Hit rate', get: (f) => `${(f.hit_rate * 100).toFixed(0)}%`, better: (f) => f.hit_rate },
    { label: 'Observation dates', get: (f) => String(f.dates) },
    { label: 'Clipped at bound', get: (f) => `${(f.saturation * 100).toFixed(0)}%`, better: (f) => -f.saturation },
  ]

  return (
    <section className="fcmp" aria-label="Factor comparison">
      <div className="fcmp__head">
        <span className="label">Comparing</span>
        <button type="button" className="btn btn--ghost btn--xs" onClick={onClear}>Clear</button>
      </div>
      <table className="data-table fcmp__table">
        <thead>
          <tr>
            <th scope="col" />
            {factors.map((f) => (
              <th key={f.factor} scope="col" className="num">{label(f.factor)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            // Only mark a winner when two are present and they differ.
            const scores = row.better ? factors.map(row.better) : []
            const top = scores.length === 2 && scores[0] !== scores[1]
              ? scores.indexOf(Math.max(...scores))
              : -1
            return (
              <tr key={row.label}>
                <th scope="row" className="fcmp__rowlabel">{row.label}</th>
                {factors.map((f, i) => (
                  <td key={f.factor} className={`num${i === top ? ' fcmp__win' : ''}`}>
                    {row.get(f)}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
      {factors.length === 1 && (
        <p className="u-note" style={{ padding: '0 14px 12px' }}>
          Pick a second factor to compare against.
        </p>
      )}
    </section>
  )
}

let statSeq = 0

/**
 * A statistic that explains itself on demand.
 *
 * The hint used to be a `title` attribute — a native OS tooltip, which means
 * roughly a second of delay, no styling, no keyboard access and nothing at
 * all on touch. For a page whose entire purpose is making a number
 * interrogable, that is the wrong mechanism: the explanation was technically
 * present and practically unreachable.
 *
 * Now it is inline content that expands on hover *or* focus, so a keyboard
 * user gets it by tabbing. `aria-describedby` ties it to the value so a
 * screen reader reads the meaning with the number rather than after it.
 */
function Stat({ label: text, value, hint }: { label: string; value: string; hint?: string }) {
  const [id] = useState(() => `stat-${(statSeq += 1)}`)
  if (!hint) {
    return (
      <div className="metric-row">
        <span className="label">{text}</span>
        <span className="num">{value}</span>
      </div>
    )
  }
  return (
    <div className="metric-row mreveal" tabIndex={0} aria-describedby={id}>
      <span className="label">{text}</span>
      <span className="num">{value}</span>
      <span className="mreveal__body">
        <span><span className="mreveal__note" id={id}>{hint}</span></span>
      </span>
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
    <section className="panel panel--pad" aria-label="Return attribution">
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
            <th scope="col" className="num">Mean return per 1σ</th>
            <th scope="col" className="num">t</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((factor) => (
            <tr key={factor}>
              <td>{label(factor)}</td>
              <td className="num">
                {(attribution.factor_returns[factor] * 100).toFixed(3)}%
              </td>
              <td className="num">
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
        {(attribution.overfit_gap * 100).toFixed(0)} points of fit that{' '}
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
    <section className="panel panel--pad" aria-label="Factor redundancy">
      <h2 className="h-panel">{factors.length} factors, or fewer?</h2>
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
/** Names whose factors agree at least this much.
 *
 *  Kept as a pure function so the threshold's effect is testable: the screen
 *  is a ranked list and quietly dropping the wrong rows would be invisible
 *  in the UI. Agreement is a 0-1 share, and the comparison is inclusive so
 *  a threshold set exactly on a row's value keeps it. */
export function aboveConviction<T extends { agreement: number }>(rows: T[], min: number): T[] {
  return min <= 0 ? rows : rows.filter((row) => row.agreement >= min)
}

function ScreenTable({ rows, dispersion: spread }: {
  rows: ScreenRow[]
  dispersion: { composite_spread: number; mean_agreement: number }
}) {
  /* A continuous control rather than another set of buttons. Conviction is a
     continuous quantity and the useful threshold is not knowable in advance —
     it depends on the day's dispersion. Dragging and watching the list shrink
     is how you find where the agreement actually falls off, which a fixed
     "high/medium/low" segmentation would hide. */
  const [minAgreement, setMinAgreement] = useState(0)
  if (!rows.length) {
    return <p className="body-copy">No names had enough factors to rank on this date.</p>
  }
  const shown = aboveConviction(rows, minAgreement)
  const flat = spread.composite_spread < 20
  return (
    <>
      <div className="thresh">
        <label className="thresh__label" htmlFor="conviction">
          Minimum factor agreement
        </label>
        <input
          id="conviction"
          className="thresh__range"
          type="range"
          min={0}
          max={100}
          step={5}
          value={Math.round(minAgreement * 100)}
          onChange={(event) => setMinAgreement(Number(event.target.value) / 100)}
        />
        <output className="thresh__value num" htmlFor="conviction">
          {Math.round(minAgreement * 100)}%
        </output>
        <span className="thresh__count u-note">
          {shown.length} of {rows.length} names
        </span>
        {minAgreement > 0 && (
          <button type="button" className="btn btn--ghost btn--xs" onClick={() => setMinAgreement(0)}>
            Reset
          </button>
        )}
      </div>
      {shown.length === 0 && (
        <p className="body-copy">
          No name on this date has {Math.round(minAgreement * 100)}% factor agreement. The
          highest is {Math.round(Math.max(...rows.map((r) => r.agreement)) * 100)}%.
        </p>
      )}
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
            <th scope="col" className="num">Composite</th>
            <th scope="col">Factors</th>
            <th scope="col">Strongest</th>
            <th scope="col">Weakest</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((row) => (
            <tr key={row.symbol}>
              <td className="num">{row.rank}</td>
              <td><a href={`/company/${row.symbol}`}>{row.symbol}</a></td>
              <td className="num">{row.composite.toFixed(0)}</td>
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
          <th scope="col" className="num">Score</th>
          <th scope="col" className="num">Percentile</th>
          <th scope="col" className="num">Next {horizon}d</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.symbol}>
            <td className="num">{row.rank}</td>
            <td><a href={`/company/${row.symbol}`}>{row.symbol}</a></td>
            <td className="num">{row.score.toFixed(3)}</td>
            <td className="num">{row.percentile.toFixed(0)}</td>
            <td className="num">
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

/**
 * Failures here are a small set of specific, explainable things. A raw
 * backend string tells a user nothing they can act on, so each cause gets
 * its own explanation and its own next step.
 *
 * The 404 case is the one that actually bit: `/api/factors` is proxied to
 * whichever backend `BACKEND_ORIGIN` names, and a deployment that predates
 * this endpoint answers 404. That is not a computation failure and must not
 * be described as one — the user needs to know the endpoint is missing from
 * the backend they are connected to, not that their universe was too small.
 */
function LabError({ message, universe, onRetry, onSwitch }: {
  message: string; universe: string
  onRetry: () => void; onSwitch: (u: string) => void
}) {
  // The backend reports a stalled build explicitly. It is the only error
  // here that is known-transient, so it gets its own copy and leads with the
  // retry rather than an explanation of what broke.
  const stalled = /stalled in the/i.test(message)
  const notDeployed = /^(404|405)$/.test(message.trim())
  const unreachable = /^(50\d|failed to fetch|networkerror|load failed)/i.test(message.trim())
  const tooSmall = /at least \d+ names|symbols; cross-sectional/i.test(message)
  const noReturns = /forward returns/i.test(message)
  const noPanel = /no panel data/i.test(message)

  const title = stalled ? 'The build stopped responding and was cancelled'
    : notDeployed ? 'This endpoint is not on the connected backend'
    : unreachable ? 'The research backend is not reachable'
    : tooSmall ? 'This universe is too small to rank'
    : noReturns ? 'Not enough history has elapsed yet'
    : noPanel ? 'No price history could be assembled'
    : 'The factor evaluation could not complete'

  const explanation = stalled
    ? `${message} Nothing was lost — the panel is rebuilt from scratch on the next attempt.`
    : notDeployed
    ? `The Factor Lab calls /api/factors, and the backend answering right now returned 404 — it is running a build that predates this endpoint. Everything else on the site works because those endpoints have been deployed. Point BACKEND_ORIGIN at a backend that has it, or deploy the current build.`
    : unreachable
    ? 'The request to /api/factors did not complete. If you are running locally, the FastAPI process may not be up — the dashboard proxies to whatever BACKEND_ORIGIN names.'
    : tooSmall
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
  const [progress, setProgress] = useState<BuildProgress | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [evidence, setEvidence] = useState<EvidenceFilter>('all')
  /* Factors held for side-by-side reading. Capped at two: the whole point is
     a direct comparison, and three columns of eleven statistics is a table,
     not a comparison. Adding a third replaces the older pick. */
  const [compare, setCompare] = useState<string[]>([])
  const toggleCompare = (factor: string) =>
    setCompare((current) =>
      current.includes(factor)
        ? current.filter((f) => f !== factor)
        : [...current.slice(-1), factor],
    )

  const loading = settled === null || settled.universe !== universe
  const data = loading ? null : settled.data
  const error = loading ? null : settled.error

  /* The endpoint never blocks: a cold build takes 30-60s, and holding an HTTP
     request open that long is a broken endpoint rather than a slow one — the
     dev proxy gives up first and a serverless function would time out. So this
     polls, and the stage it renders is the one the server reports actually
     running rather than a guess from a timer. */
  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined

    const poll = () => {
      fetch(`/api/factors?universe=${encodeURIComponent(universe)}`, { signal: controller.signal })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
        .then((json: FactorLab & Partial<BuildProgress>) => {
          if (json.status === 'building') {
            setProgress(json as BuildProgress)
            timer = setTimeout(poll, 1500)
            return
          }
          setProgress(null)
          if (json.error) { setSettled({ universe, data: null, error: json.error }); return }
          setSettled({ universe, data: json as FactorLab, error: null })
          setSelected((current) => current ?? (json as FactorLab).factors[0]?.factor ?? null)
        })
        .catch((e) => {
          if (e.name !== 'AbortError') {
            setProgress(null)
            setSettled({ universe, data: null, error: String(e.message ?? e) })
          }
        })
    }
    poll()

    return () => {
      controller.abort()
      if (timer) clearTimeout(timer)
    }
  }, [universe])

  const anySignificant = useMemo(
    () => Boolean(data?.factors.some((f) => f.significant)),
    [data],
  )

  if (loading) {
    return (
      <ResearchLoader
        title="Building factor panel"
        subject={universe}
        stages={FACTOR_LAB_STAGES}
        completed={progress?.stage_index ?? 0}
        active={progress?.stage_index}
        // Real counts from the builder: "12 / 30 symbols". A build is
        // dominated by vendor round trips, so this is the only thing that
        // visibly moves during the long stage.
        // Real, server-counted progress — the only kind that gets a
        // determinate rail. Stages with no countable unit get the sweep.
        fraction={
          progress && progress.progress_total > 0
            ? progress.progress_done / progress.progress_total
            : undefined
        }
        detail={
          progress && progress.progress_total > 0
            ? `${progress.progress_done} / ${progress.progress_total} symbols`
            : undefined
        }
        note="first run fetches full history; later runs are instant for an hour"
      />
    )
  }

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

      {/* Partial results are still results. A cold build spends ~34 s of
          vendor budget; discarding all of it because one estimator raised
          would be the wrong trade. What is not acceptable is showing the
          survivors without saying which sections are missing and why. */}
      {data.degraded && data.degraded.length > 0 && (
        <section className="lab-degraded" role="status">
          <p className="lab-degraded__title">
            {data.degraded.length === 1 ? 'One estimator' : `${data.degraded.length} estimators`} did
            not complete. Everything below was computed normally.
          </p>
          <ul className="lab-degraded__list">
            {data.degraded.map((entry) => (
              <li key={entry.estimator}>
                <span className="mono">{entry.estimator}</span>
                <span className="u-meta">{entry.reason}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="lab-headline">
        {anySignificant
          ? 'At least one factor clears |t| 2.0 after correcting for overlapping windows — read it against the multiple-comparison caveat below.'
          : 'No factor clears |t| 2.0 after correcting for overlapping windows. On this sample there is no statistical evidence that these rankings predict forward returns.'}
      </p>

      <section className="panel panel--pad" aria-label="Factor evidence">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
          <h2 className="h-panel">Evidence, factor by factor</h2>
          <div className="seg" role="group" aria-label="Filter factor evidence">
            {([
              ['all', 'All'],
              ['significant', 'Cleared |t| 2'],
              ['inconclusive', 'Did not clear'],
            ] as Array<[EvidenceFilter, string]>).map(([id, text]) => {
              const count = filterEvidence(data.factors, id).length
              return (
                <button
                  key={id}
                  type="button"
                  className="seg__btn"
                  aria-pressed={evidence === id}
                  disabled={count === 0}
                  onClick={() => setEvidence(id)}
                  style={{ fontSize: '0.6875rem' }}
                >
                  {text} <span className="num" style={{ opacity: 0.6 }}>{count}</span>
                </button>
              )
            })}
          </div>
        </div>
        <p className="body-copy" style={{ marginTop: 4, marginBottom: 14, maxWidth: '68ch' }}>
          Rank IC is the correlation between a factor&rsquo;s ordering on a date and
          what actually happened next. Both t-statistics are shown: the raw one, and
          the one corrected for the fact that {data.window.horizon_days}-day returns
          sampled every {data.window.step_days} days overlap heavily.
        </p>

        {compare.length > 0 && (
          <FactorCompare
            factors={data.factors.filter((f) => compare.includes(f.factor))}
            onClear={() => setCompare([])}
          />
        )}

        <div style={{ display: 'grid', gap: 14 }}>
          {filterEvidence(data.factors, evidence).map((evaluation) => (
            <article
              key={evaluation.factor}
              className={`lab-factor rail${selected === evaluation.factor ? ' is-selected' : ''}`}
              onClick={() => setSelected(evaluation.factor)}
              onKeyDown={(e) => { if (e.key === 'Enter') setSelected(evaluation.factor) }}
              tabIndex={0}
              role="button"
              aria-pressed={selected === evaluation.factor}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
                <strong>{label(evaluation.factor)}</strong>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <button
                    type="button"
                    className={`btn btn--ghost btn--xs${compare.includes(evaluation.factor) ? ' is-on' : ''}`}
                    aria-pressed={compare.includes(evaluation.factor)}
                    onClick={(event) => { event.stopPropagation(); toggleCompare(evaluation.factor) }}
                  >
                    {compare.includes(evaluation.factor) ? 'Comparing' : 'Compare'}
                  </button>
                  <span className={`badge ${icTone(evaluation.mean_ic)}`}>
                    IC {evaluation.mean_ic >= 0 ? '+' : ''}{evaluation.mean_ic.toFixed(4)}
                  </span>
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

      <section className="panel panel--pad" aria-label="Composite screen">
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
        <section className="panel panel--pad" aria-label="Latest cross-section">
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
