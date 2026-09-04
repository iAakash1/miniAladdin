/**
 * Regime and universe context.
 *
 * Two things the command centre should say before any result: what market
 * conditions the evidence was gathered in, and whether the universe it was
 * gathered on is honest.
 *
 * The universe figures answer the second directly. A membership history where
 * almost every name that ever appeared has since left is the signature of a
 * point-in-time universe — one that includes the companies that failed. A
 * universe whose members never exit is a universe of survivors, and every
 * backtest run on it is measured on companies already known to have made it.
 *
 * The regime distribution matters for the first. A sample that is
 * overwhelmingly one regime has not tested a strategy against the others,
 * whatever its aggregate statistics say.
 */
'use client'

import { useEffect, useState } from 'react'

import { BarRows } from '@/components/system/charts'
import { Grid, Panel, Section, StateBlock, Status, Value } from '@/components/system'
import { readResource } from '@/lib/resource'

interface Regimes {
  method?: string
  states?: string[]
  observations?: number
  distribution?: Record<string, number>
}

interface Universe {
  name?: string
  size?: number
  snapshots?: number
  start?: string
  end?: string
  unique_members?: number
  ever_exited?: number
  mean_entries_per_rebalance?: number
  point_in_time?: boolean
  coverage_classes?: string[]
}

export default function ResearchContext({ experiment = 'EXP-006' }: { experiment?: string }) {
  const [regimes, setRegimes] = useState<Regimes | null>(null)
  const [universe, setUniverse] = useState<Universe | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    readResource<{ regimes?: Regimes | null; universe?: Universe | null }>(`/api/quant/experiments/${encodeURIComponent(experiment)}`, 'artifact')
      .then((d) => { if (alive) { setRegimes(d.regimes ?? null); setUniverse(d.universe ?? null) } })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [experiment])

  if (error) {
    return <Panel title="Research context" state="unavailable"><StateBlock state="unavailable" title="Context could not be read" detail={error} /></Panel>
  }
  if (!regimes && !universe) {
    return <Panel title="Research context" state="waking"><StateBlock state="waking" title="Reading experiment context" /></Panel>
  }

  const dist = regimes?.distribution ?? {}
  const total = Object.values(dist).reduce((s, v) => s + v, 0) || 1
  const dominant = Object.entries(dist).sort((a, b) => b[1] - a[1])[0]
  const exitShare = universe?.unique_members && universe.ever_exited
    ? universe.ever_exited / universe.unique_members
    : null

  return (
    <Grid>
      <Panel
        title="Regimes in the sample"
        subtitle={regimes?.method}
        state="recorded"
      >
        {Object.keys(dist).length ? (
          <>
            <BarRows
              unit="observations"
              rows={Object.entries(dist)
                .sort((a, b) => b[1] - a[1])
                .map(([state, n]) => ({
                  label: state.replace(/_/g, ' '),
                  value: n,
                  note: `${((n / total) * 100).toFixed(1)}% of ${total} observations`,
                }))}
            />
            {dominant ? (
              <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)', maxWidth: '78ch' }}>
                {((dominant[1] / total) * 100).toFixed(0)}% of the sample sits in{' '}
                {dominant[0].replace(/_/g, ' ')}. Whatever the aggregate statistics say,
                the other regimes are thinly tested — the rarest here has{' '}
                {Math.min(...Object.values(dist))} observations.
              </p>
            ) : null}
          </>
        ) : (
          <StateBlock
            state="unavailable"
            title="No regime distribution recorded"
            detail="This experiment stored no regime classification, so what market conditions its evidence was gathered in is unknown."
          />
        )}
      </Panel>

      <Panel
        title="Universe"
        subtitle={universe?.name}
        state={universe?.point_in_time === undefined ? 'unavailable' : universe.point_in_time ? 'recorded' : 'blocked'}
      >
        <table className="sys-table sys-table--compact">
          <tbody>
            <tr><td>Members per snapshot</td><td className="num"><Value value={universe?.size ?? null} kind="count" /></td></tr>
            <tr><td>Snapshots</td><td className="num"><Value value={universe?.snapshots ?? null} kind="count" /></td></tr>
            <tr><td>Window</td><td className="num">{universe?.start ?? '—'} → {universe?.end ?? '—'}</td></tr>
            <tr><td>Unique members ever</td><td className="num"><Value value={universe?.unique_members ?? null} kind="count" /></td></tr>
            <tr><td>Ever exited</td><td className="num"><Value value={universe?.ever_exited ?? null} kind="count" /></td></tr>
            <tr>
              <td>Point in time</td>
              <td className="num">
                <Status state={universe?.point_in_time === undefined ? 'unavailable' : universe.point_in_time ? 'recorded' : 'blocked'} label={String(universe?.point_in_time ?? 'unknown')} />
              </td>
            </tr>
          </tbody>
        </table>

        {exitShare !== null ? (
          <Section title="Why this matters">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)', maxWidth: '78ch' }}>
              {(exitShare * 100).toFixed(0)}% of every name that has ever been a member
              has since left it. That churn is the evidence the universe is
              point-in-time: it contains the companies that failed, not only the ones
              that survived. A membership list whose names never exit produces
              backtests measured on companies already known to have made it, and
              every result on such a list is flattered by construction.
            </p>
          </Section>
        ) : null}
      </Panel>
    </Grid>
  )
}
