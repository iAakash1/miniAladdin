/**
 * Covariance laboratory.
 *
 * Every risk number a book reports rests on a covariance matrix, and which
 * estimator produced it is a choice nobody was being shown. On the research
 * book the four estimators disagree about portfolio volatility by roughly a
 * fifth — so the comparison is the surface, not a footnote under one matrix.
 *
 * The default is listed first and is never silently replaced. It is here
 * because it is the one that can fail to be positive semi-definite, and seeing
 * that beside three that cannot is the point.
 */
'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

import { Matrix } from '@/components/system/charts'
import { Panel, StateBlock, Status, Strip, Value } from '@/components/system'
import { DataTable, type DataColumn } from '@/components/system/DataTable'
import { ObjectHeader, StripSkeleton, TableSkeleton, Toolbar, ToolbarGroup, ToolbarSpacer } from '@/components/system/composition'

interface Row {
  estimator: string
  names: number
  observations: number
  complete_rows: number | null
  shrinkage: number | null
  positive_semi_definite: boolean
  min_eigenvalue: number | null
  condition_number: number | null
  non_finite_entries: number
  portfolio_volatility: number | null
  diversification_ratio: number | null
  diversification_ratio_below_one: boolean
  impossible_reason: string | null
  unusable_reason: string | null
  note: string | null
}

interface Payload {
  status?: string
  message?: string
  estimators?: Row[]
  panel?: { names: number; rows: number; complete_rows: number }
  correlation?: { estimator: string; labels: string[]; values: (number | null)[][]; complete_rows: number; note: string | null }
  note?: string
}

export default function CovarianceLab() {
  const [data, setData] = useState<Payload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    fetch('/api/quant/covariance')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: Payload) => { if (alive) setData(d) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [])

  const columns: DataColumn<Row>[] = [
    {
      key: 'est', header: 'Estimator', width: '20%',
      sort: (r) => r.estimator, text: (r) => r.estimator,
      render: (r) => <span style={{ fontFamily: 'var(--font-mono)' }}>{r.estimator}</span>,
    },
    {
      key: 'psd', header: 'PSD', width: '10%', sort: (r) => (r.positive_semi_definite ? 1 : 0),
      render: (r) => <Status state={r.positive_semi_definite ? 'recorded' : 'blocked'} label={r.positive_semi_definite ? 'yes' : 'no'} />,
    },
    {
      key: 'eig', header: 'Min eigenvalue', unit: 'variance units', numeric: true, sort: (r) => r.min_eigenvalue,
      render: (r) => (
        <span className={`sys-num${r.min_eigenvalue !== null && r.min_eigenvalue < 0 ? ' sys-neg' : ''}`}>
          {r.min_eigenvalue === null ? <span className="sys-null">—</span> : r.min_eigenvalue.toExponential(2)}
        </span>
      ),
    },
    {
      key: 'cond', header: 'Condition', unit: 'λmax/λmin', numeric: true, sort: (r) => r.condition_number,
      render: (r) => <Value value={r.condition_number} digits={0} title="Large means near-singular in some direction, where an optimiser puts its least justified bets" />,
    },
    {
      key: 'shrink', header: 'Shrinkage', unit: 'intensity 0 to 1', numeric: true, sort: (r) => r.shrinkage,
      render: (r) => <Value value={r.shrinkage} digits={3} />,
    },
    {
      key: 'rows', header: 'Rows used', unit: 'complete / total', numeric: true, sort: (r) => r.complete_rows ?? r.observations,
      render: (r) => (
        <span className="sys-num" title={r.complete_rows === null ? 'pairwise: each entry uses whichever rows that pair shares' : 'complete rows only'}>
          {r.complete_rows === null ? `${r.observations} pairwise` : `${r.complete_rows} / ${r.observations}`}
        </span>
      ),
    },
    {
      key: 'vol', header: 'Portfolio vol', unit: 'per period', numeric: true, sort: (r) => r.portfolio_volatility,
      render: (r) => <Value value={r.portfolio_volatility} digits={6} />,
    },
    {
      key: 'dr', header: 'Diversification', unit: '≥ 1', numeric: true, sort: (r) => r.diversification_ratio,
      render: (r) => (
        <span title={r.impossible_reason ?? undefined}>
          <Value value={r.diversification_ratio} digits={4} tone={false} />
          {r.diversification_ratio_below_one ? <span className="sys-neg" style={{ marginLeft: 4, fontSize: 'var(--t-micro)' }}>impossible</span> : null}
        </span>
      ),
    },
  ]

  if (error) {
    return <Panel title="Covariance" state="unavailable"><StateBlock state="unavailable" title="The comparison could not be read" detail={`Request failed: ${error}.`} /></Panel>
  }
  if (!data) {
    return (
      <>
        <StripSkeleton items={6} />
        <Toolbar>
        <ToolbarGroup label="trace">
          <Link href="/terminal/risk" className="sys-btn" style={{ textDecoration: 'none' }}>risk</Link>
          <Link href="/terminal/book" className="sys-btn" style={{ textDecoration: 'none' }}>book</Link>
          <Link href="/terminal/handbook" className="sys-btn" style={{ textDecoration: 'none' }}>handbook</Link>
        </ToolbarGroup>
        <ToolbarSpacer />
        <span className="sys-meta">the estimator is a choice, not a property of the book</span>
      </Toolbar>

      <Panel title="Estimators" subtitle="estimating on the book's panel" state="waking" flush>
          <TableSkeleton rows={4} columns={8} />
        </Panel>
      </>
    )
  }
  if (data.status !== 'ok' || !data.estimators?.length) {
    return <Panel title="Covariance" state="unavailable"><StateBlock state="unavailable" title="No book to estimate on" detail={data.message} /></Panel>
  }

  const rows = data.estimators
  const vols = rows.map((r) => r.portfolio_volatility).filter((v): v is number => v !== null)
  const spread = vols.length > 1 ? (Math.max(...vols) - Math.min(...vols)) / Math.min(...vols) : null
  const impossible = rows.filter((r) => r.diversification_ratio_below_one)
  const chosen = rows.find((r) => r.estimator === selected)

  return (
    <>
      <ObjectHeader
        glyph="Σ"
        name="Covariance"
        kind="four estimators, one panel"
        state={rows.some((r) => !r.positive_semi_definite) ? 'blocked' : 'recorded'}
        detail={spread !== null ? `${(spread * 100).toFixed(1)}% volatility spread across methods` : undefined}
        facts={[
          { label: 'Estimators', value: rows.length, digits: 0 , kind: 'count'},
          { label: 'Names', value: data.panel?.names ?? null, digits: 0 },
          { label: 'Rows', value: data.panel?.rows ?? null, digits: 0 , kind: 'count'},
          { label: 'Complete', value: data.panel?.complete_rows ?? null, digits: 0, title: 'Rows with no missing name' },
          { label: 'Not PSD', value: rows.filter((r) => !r.positive_semi_definite).length, digits: 0 },
        ]}
      />

      <Strip metrics={[
        { label: 'Estimators', value: rows.length, digits: 0 , kind: 'count'},
        { label: 'Names', value: data.panel?.names ?? null, digits: 0 },
        { label: 'Observations', value: data.panel?.rows ?? null, digits: 0 },
        { label: 'Complete rows', value: data.panel?.complete_rows ?? null, digits: 0, title: 'Rows with no missing name. Complete-case estimators use only these.' },
        { label: 'Volatility spread', value: spread, digits: 4, tone: true, title: 'How much the reported portfolio volatility moves purely from the estimator chosen' },
        { label: 'Not PSD', value: rows.filter((r) => !r.positive_semi_definite).length, digits: 0 },
      ]} />

      {spread !== null && spread > 0.02 ? (
        <Panel title="The estimator is a choice" state="stale">
          <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)', maxWidth: '84ch' }}>
            Portfolio volatility moves by {(spread * 100).toFixed(1)}% across these
            four matrices, on identical returns and identical weights. Any single
            risk number quoted from this book carries that uncertainty and is not
            usually shown with it.
          </p>
        </Panel>
      ) : null}

      {impossible.length ? (
        <Panel title="Impossible values" state="blocked">
          <p style={{ margin: '0 0 var(--d-2)', fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)', maxWidth: '84ch' }}>
            A diversification ratio has a hard floor of 1: correlation can only
            push portfolio volatility below the weighted average of its parts,
            never above. A value under 1 is the matrix reporting that it is not a
            covariance matrix, and it looks like an ordinary number.
          </p>
          <table className="sys-table sys-table--compact">
            <tbody>
              {impossible.map((r) => (
                <tr key={r.estimator}>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>{r.estimator}</td>
                  <td className="num sys-neg"><Value value={r.diversification_ratio} digits={4} /></td>
                  <td><span className="sys-meta" style={{ color: 'var(--ink)' }}>{r.impossible_reason}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      ) : null}

      <Panel title="Estimators" subtitle="same panel, same weights" flush>
        <DataTable
          columns={columns} rows={rows} rowKey={(r) => r.estimator}
          density="normal" selectedKey={selected ?? undefined}
          onSelect={(r) => setSelected(r.estimator === selected ? null : r.estimator)}
          filterPlaceholder="filter estimators"
          initialSort={{ key: 'cond', direction: 'asc' }}
        />
      </Panel>

      {chosen ? (
        <Panel title="Estimator" subtitle={chosen.estimator} state={chosen.positive_semi_definite ? 'recorded' : 'blocked'}>
          <table className="sys-table sys-table--compact">
            <tbody>
              <tr><td>Note</td><td style={{ whiteSpace: 'normal', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)' }}>{chosen.note ?? '—'}</td></tr>
              <tr><td>Non-finite entries</td><td className="num"><Value value={chosen.non_finite_entries} digits={0} /></td></tr>
              <tr><td>Names</td><td className="num"><Value value={chosen.names} digits={0} /></td></tr>
              {chosen.unusable_reason ? (
                <tr><td>Refused</td><td style={{ whiteSpace: 'normal', fontSize: 'var(--t-meta)', color: 'var(--e-neg)' }}>{chosen.unusable_reason}</td></tr>
              ) : null}
            </tbody>
          </table>
        </Panel>
      ) : null}

      {data.correlation ? (
        <Panel
          title="Correlation"
          subtitle={`${data.correlation.estimator} · ${data.correlation.complete_rows} complete rows`}
        >
          <Matrix
            labels={data.correlation.labels}
            values={data.correlation.values}
            unit="correlation"
          />
          <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)', maxWidth: '84ch' }}>
            A hatched cell is a pair that was never observed together. It is left
            unmeasured rather than shaded as zero, because an unobserved pair is
            not an uncorrelated one.
          </p>
        </Panel>
      ) : null}

      <Panel title="Why the default is unchanged">
        <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)', maxWidth: '84ch' }}>
          {data.note}
        </p>
      </Panel>
    </>
  )
}
