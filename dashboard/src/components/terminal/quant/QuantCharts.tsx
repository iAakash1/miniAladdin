'use client'

/**
 * Chart primitives for the quant terminal.
 *
 * Inline SVG, no charting library. Three reasons: the existing terminal has no
 * chart dependency and adding one for six small plots is a poor trade; these
 * shapes are simple enough that the drawing code is shorter than the config
 * would be; and every mark can then carry its own units and sample size, which
 * is the property that actually matters here.
 *
 * **Every chart takes a `caption` and `units` and renders them.** A quant chart
 * without units is a decoration, and one without its sample size invites exactly
 * the inference the rest of this page exists to prevent.
 */

import type { ReactNode } from 'react'

// ── shared ───────────────────────────────────────────────────────────────────

function Frame({
  title, units, sample, caption, children, height = 180,
}: {
  title: string
  units: string
  sample?: string
  caption: ReactNode
  children: ReactNode
  height?: number
}) {
  return (
    <figure className="qc">
      <figcaption className="qc__head">
        <span className="qc__title">{title}</span>
        <span className="qc__units">{units}{sample ? ` · ${sample}` : ''}</span>
      </figcaption>
      <div className="qc__plot" style={{ height }}>{children}</div>
      <p className="qc__caption">{caption}</p>
    </figure>
  )
}

const fmt = (v: number, d = 4) => (v >= 0 ? '+' : '') + v.toFixed(d)

// ── per-fold IC ──────────────────────────────────────────────────────────────

export function FoldIcChart({
  folds, meanIc,
}: {
  folds: Array<{ fold: number; mean_ic: number | null; dates: number }>
  meanIc?: number | null
}) {
  const usable = folds.filter((f) => f.mean_ic !== null) as Array<{
    fold: number; mean_ic: number; dates: number
  }>
  if (!usable.length) return null
  const max = Math.max(...usable.map((f) => Math.abs(f.mean_ic))) * 1.25 || 0.01
  const w = 100 / usable.length
  const positive = usable.filter((f) => f.mean_ic > 0).length

  return (
    <Frame
      title="Rank IC by fold"
      units="Spearman IC"
      sample={`${usable.length} folds · ${usable.reduce((a, f) => a + f.dates, 0)} validation dates`}
      caption={
        <>
          Out-of-sample information coefficient in each expanding walk-forward fold.
          <strong> {positive} of {usable.length} folds positive.</strong> A model that
          works in one fold and dies in the rest is not robust — the dispersion here
          matters more than the mean{meanIc != null ? ` (${fmt(meanIc)})` : ''}.
        </>
      }
    >
      <svg viewBox="0 0 100 60" preserveAspectRatio="none" className="qc__svg" role="img"
           aria-label={`Rank IC across ${usable.length} folds`}>
        <line x1="0" y1="30" x2="100" y2="30" className="qc__axis" />
        {usable.map((f, i) => {
          const h = (Math.abs(f.mean_ic) / max) * 28
          const up = f.mean_ic > 0
          return (
            <rect
              key={f.fold}
              x={i * w + w * 0.22} y={up ? 30 - h : 30}
              width={w * 0.56} height={Math.max(h, 0.4)}
              className={up ? 'qc__bar--pos' : 'qc__bar--neg'}
            >
              <title>{`fold ${f.fold}: IC ${fmt(f.mean_ic)} over ${f.dates} dates`}</title>
            </rect>
          )
        })}
      </svg>
      <div className="qc__xlabels">
        {usable.map((f) => <span key={f.fold}>{f.fold}</span>)}
      </div>
    </Frame>
  )
}

// ── train vs validation ──────────────────────────────────────────────────────

export function OverfitScatter({
  rows,
}: {
  rows: Array<{
    model_id: string; train_mean_ic?: number | null; mean_ic?: number | null; kind?: string
  }>
}) {
  const pts = rows.filter(
    (r) => r.train_mean_ic != null && r.mean_ic != null,
  ) as Array<{ model_id: string; train_mean_ic: number; mean_ic: number; kind?: string }>
  if (!pts.length) return null

  const maxTrain = Math.max(...pts.map((p) => p.train_mean_ic), 0.05) * 1.1
  const vals = pts.map((p) => p.mean_ic)
  const lo = Math.min(...vals, -0.01)
  const hi = Math.max(...vals, 0.03)
  const x = (v: number) => (v / maxTrain) * 92 + 4
  const y = (v: number) => 54 - ((v - lo) / (hi - lo || 1)) * 48

  return (
    <Frame
      title="Train IC vs validation IC"
      units="Spearman IC, both axes"
      sample={`${pts.length} models`}
      caption={
        <>
          A model sits near the dashed <em>train = validation</em> line only if it
          generalises. Points far right and flat have memorised the training fold;
          the vertical distance below the line is the overfitting gap.
        </>
      }
    >
      <svg viewBox="0 0 100 60" className="qc__svg" role="img"
           aria-label="Train versus validation IC">
        <line x1="4" y1="54" x2="96" y2="54" className="qc__axis" />
        <line x1="4" y1="6" x2="4" y2="54" className="qc__axis" />
        {hi > 0 && lo < 0 && (
          <line x1="4" y1={y(0)} x2="96" y2={y(0)} className="qc__axis qc__axis--faint" />
        )}
        <line x1={x(0)} y1={y(0)} x2={x(Math.min(maxTrain, hi))} y2={y(Math.min(maxTrain, hi))}
              className="qc__diag" />
        {pts.map((p) => (
          <circle key={p.model_id} cx={x(p.train_mean_ic)} cy={y(p.mean_ic)} r="1.5"
                  className={p.kind === 'baseline' ? 'qc__dot--base' : 'qc__dot'}>
            <title>{`${p.model_id}: train ${fmt(p.train_mean_ic, 3)}, validation ${fmt(p.mean_ic, 4)}`}</title>
          </circle>
        ))}
      </svg>
    </Frame>
  )
}

// ── ablation ─────────────────────────────────────────────────────────────────

export function AblationChart({
  arms, baseArm,
}: {
  arms: Array<{ arm: string; best_ic?: number | null; feature_count: number; skipped: boolean }>
  baseArm: string
}) {
  const usable = arms.filter((a) => !a.skipped && a.best_ic != null) as Array<{
    arm: string; best_ic: number; feature_count: number
  }>
  if (!usable.length) return null
  const max = Math.max(...usable.map((a) => a.best_ic)) * 1.2 || 0.01
  const w = 100 / usable.length

  return (
    <Frame
      title="Best IC by feature arm"
      units="Spearman IC · best of 6 models"
      sample={`${usable.length} pre-registered arms`}
      height={190}
      caption={
        <>
          Each arm adds one data family to a fixed base. The peak is{' '}
          <strong>{baseArm}</strong> — everything derivable from the price panel and
          the rate curve. <strong>Every additional source lowers it.</strong> These
          bars are a best-of-six and therefore biased upward; the per-model contrast
          below is the honest comparison.
        </>
      }
    >
      <svg viewBox="0 0 100 60" preserveAspectRatio="none" className="qc__svg" role="img"
           aria-label="Best IC per ablation arm">
        <line x1="0" y1="56" x2="100" y2="56" className="qc__axis" />
        {usable.map((a, i) => {
          const h = (a.best_ic / max) * 50
          return (
            <rect key={a.arm} x={i * w + w * 0.2} y={56 - h} width={w * 0.6}
                  height={Math.max(h, 0.4)}
                  className={a.arm === baseArm ? 'qc__bar--base' : 'qc__bar--pos'}>
              <title>{`${a.arm}: IC ${fmt(a.best_ic)} with ${a.feature_count} features`}</title>
            </rect>
          )
        })}
      </svg>
      <div className="qc__xlabels qc__xlabels--tilt">
        {usable.map((a) => <span key={a.arm}>{a.arm.replace(/^[A-G]_/, '')}</span>)}
      </div>
    </Frame>
  )
}

// ── cumulative rank spread ───────────────────────────────────────────────────

export function SpreadCurve({
  periods, units,
}: {
  periods: Array<{
    date: string; gross_cumulative: number; net_cumulative: number; net_drawdown: number
  }>
  units: string
}) {
  if (periods.length < 2) return null
  const all = periods.flatMap((p) => [p.gross_cumulative, p.net_cumulative])
  const lo = Math.min(...all, 0)
  const hi = Math.max(...all, 0)
  const x = (i: number) => (i / (periods.length - 1)) * 100
  const y = (v: number) => 46 - ((v - lo) / (hi - lo || 1)) * 42
  const path = (key: 'gross_cumulative' | 'net_cumulative') =>
    periods.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(2)},${y(p[key]).toFixed(2)}`).join(' ')

  const ddLo = Math.min(...periods.map((p) => p.net_drawdown), -1e-9)
  const ddY = (v: number) => 60 - (v / ddLo) * 12

  return (
    <Frame
      title="Cumulative rank spread, gross and net"
      units={units}
      sample={`${periods.length} rebalances · ${periods[0].date} → ${periods[periods.length - 1].date}`}
      height={200}
      caption={
        <>
          <strong>This is not a P&amp;L.</strong> The target is a cross-sectional rank
          in [−1, 1], so the accumulation is additive and its units are rank points,
          not currency. It shows whether the ranking worked steadily or in one stretch.
          The gap between the lines is transaction cost; the band below is drawdown
          from the running peak. Every Sharpe and return figure on this page comes from
          the artifact&apos;s costed backtest, not from this curve.
        </>
      }
    >
      <svg viewBox="0 0 100 62" preserveAspectRatio="none" className="qc__svg" role="img"
           aria-label="Cumulative rank spread, gross versus net">
        <line x1="0" y1={y(0)} x2="100" y2={y(0)} className="qc__axis qc__axis--faint" />
        <path
          d={`M0,60 ${periods.map((p, i) => `L${x(i).toFixed(2)},${ddY(p.net_drawdown).toFixed(2)}`).join(' ')} L100,60 Z`}
          className="qc__dd"
        />
        <path d={path('gross_cumulative')} className="qc__line--gross" />
        <path d={path('net_cumulative')} className="qc__line--net" />
      </svg>
      <div className="qc__legend">
        <span className="qc__key qc__key--gross">gross</span>
        <span className="qc__key qc__key--net">net of cost</span>
        <span className="qc__key qc__key--dd">drawdown</span>
      </div>
    </Frame>
  )
}

// ── regime ───────────────────────────────────────────────────────────────────

export function RegimeChart({
  rows, minDates,
}: {
  rows: Array<{ regime: string; dates: number; mean_ic?: number | null; ic_t_stat?: number | null }>
  minDates: number
}) {
  if (!rows.length) return null
  const max = Math.max(...rows.map((r) => Math.abs(r.mean_ic ?? 0)), 0.01) * 1.25
  const w = 100 / rows.length
  const quotable = rows.filter((r) => r.dates >= minDates)

  return (
    <Frame
      title="IC by market regime"
      units="Spearman IC"
      sample={`${rows.length} regimes · ${quotable.length} above the ${minDates}-date floor`}
      height={190}
      caption={
        <>
          Hatched bars fall below the {minDates}-date evidence floor and are{' '}
          <strong>not quotable</strong> — drawn only so the small sample is visible,
          never as a claim. In the one regime with enough dates the IC is near zero,
          which is where the headline comes from.
        </>
      }
    >
      <svg viewBox="0 0 100 60" preserveAspectRatio="none" className="qc__svg" role="img"
           aria-label="IC by regime with sample sizes">
        <defs>
          <pattern id="qcThin" width="3" height="3" patternTransform="rotate(45)"
                   patternUnits="userSpaceOnUse">
            <line x1="0" y1="0" x2="0" y2="3" className="qc__hatch" />
          </pattern>
        </defs>
        <line x1="0" y1="30" x2="100" y2="30" className="qc__axis" />
        {rows.map((r, i) => {
          const v = r.mean_ic ?? 0
          const h = (Math.abs(v) / max) * 26
          const thin = r.dates < minDates
          return (
            <rect key={r.regime} x={i * w + w * 0.22} y={v > 0 ? 30 - h : 30}
                  width={w * 0.56} height={Math.max(h, 0.4)}
                  className={thin ? 'qc__bar--thin' : v > 0 ? 'qc__bar--pos' : 'qc__bar--neg'}
                  fill={thin ? 'url(#qcThin)' : undefined}>
              <title>
                {`${r.regime}: IC ${fmt(v)} over ${r.dates} dates${thin ? ' — INSUFFICIENT' : ''}`}
              </title>
            </rect>
          )
        })}
      </svg>
      <div className="qc__xlabels qc__xlabels--tilt">
        {rows.map((r) => (
          <span key={r.regime} className={r.dates < minDates ? 'qc__thin' : ''}>
            {r.regime.replace(/_/g, ' ')}<br /><em>{r.dates}d</em>
          </span>
        ))}
      </div>
    </Frame>
  )
}

// ── cost sensitivity ─────────────────────────────────────────────────────────

export function CostCurve({
  rows, model,
}: {
  rows: Array<{ half_spread_bps: number; net_sharpe?: number | null; gross_sharpe?: number | null }>
  model: string
}) {
  if (rows.length < 2) return null
  const vals = rows.flatMap((r) => [r.net_sharpe ?? 0, r.gross_sharpe ?? 0])
  const lo = Math.min(...vals, 0)
  const hi = Math.max(...vals, 0)
  const x = (i: number) => (i / (rows.length - 1)) * 92 + 4
  const y = (v: number) => 50 - ((v - lo) / (hi - lo || 1)) * 44
  const line = (k: 'net_sharpe' | 'gross_sharpe') =>
    rows.map((r, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(2)},${y(r[k] ?? 0).toFixed(2)}`).join(' ')

  return (
    <Frame
      title="Sharpe against cost assumption"
      units="annualised Sharpe"
      sample={`${model} · ${rows.length} cost points`}
      caption={
        <>
          Net Sharpe as the assumed half-spread widens. The flat line is{' '}
          <strong>gross</strong> Sharpe — it does not move with cost, and it is already
          below zero. A strategy that loses before any cost is applied cannot be
          rescued by a friendlier cost assumption.
        </>
      }
    >
      <svg viewBox="0 0 100 56" className="qc__svg" role="img"
           aria-label="Sharpe versus cost assumption">
        <line x1="4" y1={y(0)} x2="96" y2={y(0)} className="qc__axis" />
        <path d={line('gross_sharpe')} className="qc__line--gross" />
        <path d={line('net_sharpe')} className="qc__line--net" />
        {rows.map((r, i) => (
          <circle key={r.half_spread_bps} cx={x(i)} cy={y(r.net_sharpe ?? 0)} r="1.2"
                  className="qc__dot">
            <title>{`${r.half_spread_bps} bp: net Sharpe ${fmt(r.net_sharpe ?? 0, 3)}`}</title>
          </circle>
        ))}
      </svg>
      <div className="qc__xlabels">
        {rows.map((r) => <span key={r.half_spread_bps}>{r.half_spread_bps}bp</span>)}
      </div>
    </Frame>
  )
}

// ── walk-forward timeline ────────────────────────────────────────────────────

export function WalkForwardTimeline({
  folds, holdoutStart, holdoutEnd, executionLag,
}: {
  folds: Array<{
    index: number; train_start: string; train_end: string; purge_end: string
    validation_start: string; validation_end: string
    train_rows: number; validation_rows: number; gap_sessions: number
  }>
  holdoutStart?: string | null
  holdoutEnd?: string | null
  executionLag: number
}) {
  if (!folds.length) return null
  const t = (d: string) => new Date(d).getTime()
  const start = Math.min(...folds.map((f) => t(f.train_start)))
  const end = t(holdoutEnd ?? folds[folds.length - 1].validation_end)
  const span = end - start || 1
  const pos = (d: string) => Math.max(0, Math.min(100, ((t(d) - start) / span) * 100))

  return (
    <Frame
      title="Expanding walk-forward"
      units="calendar time"
      sample={`${folds.length} folds · ${folds[0].gap_sessions}-session purge + embargo · execution lag ${executionLag} period`}
      height={folds.length * 20 + 46}
      caption={
        <>
          Each row is one fold. Training (solid) always ends before validation (open)
          begins, separated by a purge-and-embargo gap so no training label overlaps a
          validation date. The shaded band on the right is the{' '}
          <strong>locked holdout</strong> — no fold reaches it, and the firewall refuses
          holdout-dated rows at fit time. Nothing here is a random split.
        </>
      }
    >
      <svg viewBox={`0 0 100 ${folds.length * 12 + 6}`} preserveAspectRatio="none"
           className="qc__svg" role="img" aria-label="Walk-forward fold layout">
        {holdoutStart && holdoutEnd && (
          <rect x={pos(holdoutStart)} y="0" width={100 - pos(holdoutStart)}
                height={folds.length * 12 + 6} className="qc__holdout" />
        )}
        {folds.map((f, i) => {
          const yy = i * 12 + 3
          return (
            <g key={f.index}>
              <rect x={pos(f.train_start)} y={yy} width={pos(f.train_end) - pos(f.train_start)}
                    height="6" className="qc__train">
                <title>
                  {`fold ${f.index} train: ${f.train_start} → ${f.train_end} (${f.train_rows.toLocaleString()} rows)`}
                </title>
              </rect>
              <rect x={pos(f.train_end)} y={yy} width={Math.max(pos(f.purge_end) - pos(f.train_end), 0.3)}
                    height="6" className="qc__gap">
                <title>{`purge + embargo: ${f.gap_sessions} sessions`}</title>
              </rect>
              <rect x={pos(f.validation_start)} y={yy}
                    width={pos(f.validation_end) - pos(f.validation_start)}
                    height="6" className="qc__valid">
                <title>
                  {`fold ${f.index} validation: ${f.validation_start} → ${f.validation_end} (${f.validation_rows.toLocaleString()} rows)`}
                </title>
              </rect>
            </g>
          )
        })}
      </svg>
      <div className="qc__legend">
        <span className="qc__key qc__key--train">train</span>
        <span className="qc__key qc__key--gap">purge + embargo</span>
        <span className="qc__key qc__key--valid">validation</span>
        <span className="qc__key qc__key--holdout">holdout (locked)</span>
      </div>
    </Frame>
  )
}
