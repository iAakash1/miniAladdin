/**
 * Factor cross-section, screen and attribution.
 *
 * Migrated from the legacy factor lab, which computed all of this and rendered
 * it as three unrelated blocks. They belong together: the cross-section is what
 * a factor says about each name today, the screen is what the factors say
 * jointly, and attribution is how much of the cross-section they explain at all.
 *
 * The screen's conviction column is the one worth reading first. A name ranked
 * highly by factors that disagree is a different proposition from one ranked
 * highly by factors that agree, and a composite score alone cannot distinguish
 * them — averaging conflicting signals produces a confident-looking number from
 * an unresolved disagreement.
 */
'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'

import { BarRows, Histogram, Scatter } from '@/components/system/charts'
import { Grid, Panel, Prose, Section, StateBlock, Status, Strip, Value, type ResearchState } from '@/components/system'
import { DataTable, type DataColumn } from '@/components/system/DataTable'
import { recordVisit } from '@/lib/research/history'

export interface RankRow {
  rank: number
  symbol: string
  score: number
  percentile: number
  forward_return: number | null
}

export interface ScreenRow {
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

export interface Attribution {
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

const n = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

const CONVICTION: Record<string, ResearchState> = {
  aligned: 'candidate',
  mixed: 'stale',
  conflicted: 'blocked',
}

export default function CrossSection({
  crossSection, screen, attribution,
}: {
  crossSection?: { date: string; factors: Record<string, RankRow[]> } | null
  screen?: { date: string; dispersion?: { composite_spread: number; mean_agreement: number }; rows: ScreenRow[] } | null
  attribution?: Attribution | null
}) {
  const factorNames = useMemo(
    () => Object.keys(crossSection?.factors ?? {}).sort(),
    [crossSection],
  )
  const [factor, setFactor] = useState<string | null>(null)
  const active = factor && factorNames.includes(factor) ? factor : factorNames[0] ?? null
  const ranks = active ? crossSection?.factors[active] ?? [] : []

  const rankColumns: DataColumn<RankRow>[] = useMemo(() => [
    { key: 'rank', header: 'Rank', numeric: true, width: '8%', sort: (r) => r.rank, render: (r) => <Value value={r.rank} digits={0} /> },
    {
      key: 'sym', header: 'Symbol', width: '16%', sort: (r) => r.symbol, text: (r) => r.symbol,
      render: (r) => (
        <Link
          href={`/terminal/security?symbol=${encodeURIComponent(r.symbol)}`}
          style={{ color: 'inherit', fontFamily: 'var(--font-mono)' }}
          onClick={() => recordVisit({ kind: 'security', id: r.symbol, label: r.symbol })}
        >{r.symbol}</Link>
      ),
    },
    { key: 'score', header: 'Score', unit: 'factor score', numeric: true, sort: (r) => n(r.score), render: (r) => <Value value={n(r.score)} digits={4} signed tone /> },
    { key: 'pct', header: 'Percentile', unit: 'in the universe', numeric: true, sort: (r) => n(r.percentile), render: (r) => <Value value={n(r.percentile)} digits={3} /> },
    {
      key: 'fwd', header: 'Forward return', unit: 'realised', numeric: true, sort: (r) => n(r.forward_return),
      render: (r) => (
        <Value
          value={n(r.forward_return)}
          digits={4} signed tone
          title={r.forward_return === null ? 'The label horizon has not elapsed for this observation' : undefined}
        />
      ),
    },
  ], [])

  const screenColumns: DataColumn<ScreenRow>[] = useMemo(() => [
    { key: 'rank', header: 'Rank', numeric: true, width: '8%', sort: (r) => r.rank, render: (r) => <Value value={r.rank} digits={0} /> },
    {
      key: 'sym', header: 'Symbol', width: '14%', sort: (r) => r.symbol, text: (r) => r.symbol,
      render: (r) => (
        <Link
          href={`/terminal/security?symbol=${encodeURIComponent(r.symbol)}`}
          style={{ color: 'inherit', fontFamily: 'var(--font-mono)' }}
          onClick={() => recordVisit({ kind: 'security', id: r.symbol, label: r.symbol })}
        >{r.symbol}</Link>
      ),
    },
    { key: 'comp', header: 'Composite', unit: 'weighted score', numeric: true, sort: (r) => n(r.composite), render: (r) => <Value value={n(r.composite)} digits={4} signed tone /> },
    {
      key: 'agree', header: 'Agreement', unit: 'across factors', numeric: true, sort: (r) => n(r.agreement),
      render: (r) => <Value value={n(r.agreement)} digits={3} title="How much the contributing factors point the same way" />,
    },
    {
      key: 'conv', header: 'Conviction', width: '13%', sort: (r) => r.conviction, text: (r) => r.conviction,
      render: (r) => <Status state={CONVICTION[r.conviction] ?? 'unknown'} label={r.conviction} />,
    },
    { key: 'used', header: 'Factors used', numeric: true, sort: (r) => r.factors_used, render: (r) => <Value value={r.factors_used} digits={0} /> },
    { key: 'best', header: 'Strongest', width: '14%', optional: true, sort: (r) => r.strongest ?? null, render: (r) => <span className="sys-meta" style={{ color: 'var(--ink)' }}>{r.strongest ?? '—'}</span> },
    { key: 'worst', header: 'Weakest', width: '14%', optional: true, sort: (r) => r.weakest ?? null, render: (r) => <span className="sys-meta" style={{ color: 'var(--ink)' }}>{r.weakest ?? '—'}</span> },
  ], [])

  const conflicted = (screen?.rows ?? []).filter((r) => r.conviction === 'conflicted').length
  const aligned = (screen?.rows ?? []).filter((r) => r.conviction === 'aligned').length

  return (
    <>
      {crossSection && factorNames.length ? (
        <Panel
          title="Cross-section"
          subtitle={`${crossSection.date} · ${active ?? ''}`}
          flush
          actions={
            <select
              className="sys-input"
              value={active ?? ''}
              onChange={(e) => setFactor(e.target.value)}
              aria-label="Factor"
            >
              {factorNames.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          }
        >
          <DataTable
            columns={rankColumns} rows={ranks} rowKey={(r) => r.symbol}
            density="compact" filterPlaceholder="filter names"
            initialSort={{ key: 'rank', direction: 'asc' }}
            onSelect={(r) => recordVisit({ kind: 'security', id: r.symbol, label: r.symbol })}
          />
        </Panel>
      ) : null}

      {ranks.length > 4 ? (
        <Grid>
          <Panel title="Score distribution" subtitle={active ?? undefined}>
            <Histogram values={ranks.map((r) => r.score)} unit="factor score" title="" marks={[{ at: 0, label: '0', color: 'var(--rule-focus)' }]} />
          </Panel>
          <Panel title="Score against realised return" subtitle="one date, not evidence">
            {ranks.some((r) => r.forward_return !== null) ? (
              <>
                <Scatter
                  points={ranks
                    .filter((r) => r.forward_return !== null)
                    .map((r) => ({ x: r.score, y: r.forward_return as number, label: r.symbol }))}
                  xLabel="score" yLabel="forward return"
                  title=""
                />
                <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
                  One cross-section on one date. A slope here is not evidence of
                  predictive power — the information coefficient measured across
                  every date is, and it lives in the factor table above.
                </p>
              </>
            ) : (
              <StateBlock
                state="unavailable"
                title="No forward return yet"
                detail="The label horizon has not elapsed for this cross-section. Nothing is plotted in its place."
              />
            )}
          </Panel>
        </Grid>
      ) : null}

      {screen?.rows?.length ? (
        <>
          <Strip metrics={[
            { label: 'Names screened', value: screen.rows.length, digits: 0 },
            { label: 'Aligned', value: aligned, digits: 0, title: 'Factors point the same way' },
            { label: 'Conflicted', value: conflicted, digits: 0, title: 'Factors disagree; the composite averages that disagreement away' },
            { label: 'Composite spread', value: n(screen.dispersion?.composite_spread), digits: 4 },
            { label: 'Mean agreement', value: n(screen.dispersion?.mean_agreement), digits: 3 },
          ]} />

          <Panel title="Screen" subtitle={screen.date} flush>
            <DataTable
              columns={screenColumns} rows={screen.rows} rowKey={(r) => r.symbol}
              density="compact" filterPlaceholder="filter names"
              initialSort={{ key: 'rank', direction: 'asc' }}
              onSelect={(r) => recordVisit({ kind: 'security', id: r.symbol, label: r.symbol, detail: r.conviction })}
            />
          </Panel>

          <Panel title="Reading the screen">
            <Prose>
              Conviction is the column to read before the composite. A name ranked
              highly by factors that agree and one ranked highly by factors that
              disagree are different propositions, and a composite score cannot
              separate them — averaging a disagreement produces a confident-looking
              number from an unresolved one. {conflicted} of {screen.rows.length}{' '}
              names here are conflicted.
            </Prose>
          </Panel>
        </>
      ) : null}

      {attribution ? (
        <Panel title="Attribution" subtitle={`${attribution.dates} dates`} state="recorded">
          <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'minmax(0,1.2fr) minmax(0,1fr)' }}>
            <Section title="Factor returns">
              <BarRows
                unit="mean cross-sectional return per factor"
                rows={attribution.factors.map((f) => ({
                  label: f,
                  value: n(attribution.factor_returns[f]),
                  note: `t = ${n(attribution.t_stats[f])?.toFixed(2) ?? '—'}`,
                }))}
              />
            </Section>
            <Section title="How much is explained">
              <table className="sys-table sys-table--compact">
                <tbody>
                  <tr><td>Mean R²</td><td className="num"><Value value={n(attribution.mean_r_squared)} digits={4} /></td></tr>
                  <tr><td>Mean adjusted R²</td><td className="num"><Value value={n(attribution.mean_adjusted_r_squared)} digits={4} /></td></tr>
                  <tr>
                    <td>Overfit gap</td>
                    <td className="num">
                      <Value value={n(attribution.overfit_gap)} digits={4} tone title="R² minus adjusted R²: what the extra regressors bought that the adjustment takes back" />
                    </td>
                  </tr>
                  <tr><td>Unexplained share</td><td className="num"><Value value={n(attribution.unexplained_share)} digits={4} /></td></tr>
                  <tr><td>Median names</td><td className="num"><Value value={n(attribution.names_median)} digits={0} /></td></tr>
                </tbody>
              </table>
              <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
                {attribution.assessment}
              </p>
              <Prose size="fine">
                The unexplained share is the honest headline: it is the part of the
                cross-section these factors do not account for, and it is usually
                the larger number.
              </Prose>
            </Section>
          </div>
        </Panel>
      ) : null}
    </>
  )
}
