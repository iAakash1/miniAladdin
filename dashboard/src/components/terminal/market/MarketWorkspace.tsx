/**
 * Market workspace.
 *
 * The legacy market dashboard rendered the same payload as a stack of cards.
 * The data is good — breadth with history, eleven sectors with momentum and
 * volatility, a rule-based regime, dated events — and it deserves a workspace.
 *
 * Two decisions shape this. Breadth is drawn as a series rather than a number,
 * because a breadth score of 0.6 means something entirely different rising than
 * falling. And sectors are ranked in a sortable table rather than a grid, since
 * the question is always which is leading, and a grid makes that a scan.
 *
 * Every figure carries its source. Market data here is live vendor data, which
 * is a different kind of number from the recorded research everywhere else in
 * the product, and the rail says so.
 */
'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'

import { BarRows, TimeSeries } from '@/components/system/charts'
import { Grid, Panel, Prose, StateBlock, Status, Value, type ResearchState } from '@/components/system'
import { DataTable, type DataColumn } from '@/components/system/DataTable'
import { recordVisit } from '@/lib/research/history'
import { ObjectHeader, StripSkeleton, TableSkeleton } from '@/components/system/composition'
import WhatChanged from './WhatChanged'
import MarketMap from './MarketMap'
import type { SectorRow } from '@/lib/dashboardInsights'
import type { MapBreadth } from './MarketMap'

interface Sector {
  symbol: string
  name: string
  price: number | null
  strength_21d: number | null
  momentum_63d: number | null
  volatility: number | null
  above_50d: boolean | null
  verdict?: string | null
  source?: string | null
}

interface Breadth {
  /* As the dashboard payload actually shapes it. The table read `change`,
     which no row carries, so every index showed an em dash where its move
     should be — and its price rendered signed and green, because a bare
     `digits` falls through to the signed, toned default. */
  indexes?: {
    symbol: string
    name?: string
    price?: number | null
    change_1d?: number | null
    change_1w?: number | null
    source?: string | null
  }[]
  sectors_above_50d?: number | null
  sector_count?: number | null
  breadth_score?: number | null
  history?: { date: string; value: number }[] | number[]
  explain?: string | null
  leadership?: string | null
  laggard?: string | null
}

interface MacroCard { label?: string; value?: number | string | null; unit?: string | null; source?: string | null; as_of?: string | null }

interface Dashboard {
  macro?: { cards?: MacroCard[]; regime?: Record<string, unknown> | string | null; note?: string | null }
  breadth?: Breadth
  sectors?: Sector[]
  events?: { date: string; type?: string; title?: string; importance?: string; days_away?: number; explain?: string }[]
  generated_at?: string
  cached?: boolean
}

const n = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

function importanceState(v?: string): ResearchState {
  const s = (v ?? '').toLowerCase()
  if (s.includes('high')) return 'blocked'
  if (s.includes('med')) return 'stale'
  return 'recorded'
}

export default function MarketWorkspace() {
  const [data, setData] = useState<Dashboard | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    fetch('/api/dashboard')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: Dashboard) => { if (alive) setData(d) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [])

  const sectors = useMemo(() => data?.sectors ?? [], [data])

  const history = useMemo(() => {
    const h = data?.breadth?.history
    if (!Array.isArray(h) || !h.length) return []
    if (typeof h[0] === 'number') {
      return (h as number[]).map((v, i) => ({ x: i, y: v }))
    }
    return (h as { date: string; value: number }[]).map((p) => ({ x: p.date, y: p.value }))
  }, [data])

  const columns: DataColumn<Sector>[] = useMemo(() => [
    {
      key: 'sym', header: 'Sector', width: '22%', sort: (s) => s.name, text: (s) => `${s.symbol} ${s.name}`,
      render: (s) => (
        <Link
          href={`/terminal/security?symbol=${encodeURIComponent(s.symbol)}`}
          style={{ color: 'inherit' }}
          onClick={() => recordVisit({ kind: 'security', id: s.symbol, label: s.symbol, detail: s.name })}
        >
          <span className="sys-mono">{s.symbol}</span>
          <span className="sys-meta" style={{ marginLeft: 6 }}>{s.name}</span>
        </Link>
      ),
    },
    { key: 'price', header: 'Price', unit: 'currency', numeric: true, sort: (s) => n(s.price), render: (s) => <Value value={n(s.price)} digits={2} /> },
    {
      key: 's21', header: 'Strength', unit: '21d', numeric: true, sort: (s) => n(s.strength_21d),
      render: (s) => <Value value={n(s.strength_21d)} digits={4} signed tone />,
    },
    {
      key: 'm63', header: 'Momentum', unit: '63d', numeric: true, sort: (s) => n(s.momentum_63d),
      render: (s) => <Value value={n(s.momentum_63d)} digits={4} signed tone />,
    },
    {
      key: 'vol', header: 'Volatility', unit: 'ann.', numeric: true, sort: (s) => n(s.volatility),
      render: (s) => <Value value={n(s.volatility)} digits={4} />,
    },
    {
      key: 'ma', header: 'Above 50d', width: '11%', sort: (s) => (s.above_50d ? 1 : 0),
      render: (s) => s.above_50d === null || s.above_50d === undefined
        ? <span className="sys-null">—</span>
        : <Status state={s.above_50d ? 'recorded' : 'blocked'} label={s.above_50d ? 'yes' : 'no'} />,
    },
    {
      key: 'src', header: 'Source', width: '12%', optional: true, sort: (s) => s.source ?? null,
      render: (s) => <span className="sys-meta sys-meta--strong">{s.source ?? '—'}</span>,
    },
  ], [])

  if (error) {
    return (
      <Panel title="Market" state="unavailable">
        <StateBlock
          state="unavailable"
          title="Market data could not be read"
          detail={`Request failed: ${error}. Nothing is shown in its place — an unreachable feed is not a flat market.`}
        />
      </Panel>
    )
  }
  if (!data) {
    return (
      <>
        <StripSkeleton />
        <Panel title="Sectors" state="waking" flush><TableSkeleton rows={11} columns={6} /></Panel>
      </>
    )
  }

  const b = data.breadth ?? {}

  /* The market map needs complete rows: a price, a volatility, an above-50d
     flag, a verdict and — the one this workspace's payload type does not even
     name — ninety rebased closes per sector. Anything short of that is refused
     rather than coerced, because a sector drawn without its line reads as a
     flat sector rather than a missing one. */
  const mappable: { breadth: MapBreadth; sectors: SectorRow[] } | null = (() => {
    const rows = data.sectors ?? []
    if (!rows.length || b.breadth_score === undefined) return null
    // The map plots `score`; this payload may carry `value` or bare numbers.
    // A series in the wrong shape is converted, never reinterpreted.
    const raw = b.history ?? []
    const history = raw.every((h): h is { date: string; value: number } =>
      typeof h === 'object' && h !== null && 'date' in h && 'value' in h)
      ? raw.map((h) => ({ date: h.date, score: h.value }))
      : undefined
    const complete = rows.filter((r): r is Sector & { history: number[] } => {
      const h = (r as { history?: unknown }).history
      return Array.isArray(h) && h.length > 1
        && typeof r.price === 'number'
        && typeof r.volatility === 'number'
        && typeof r.above_50d === 'boolean'
    })
    if (complete.length !== rows.length) return null
    return {
      breadth: {
        breadth_score: b.breadth_score ?? null,
        sectors_above_50d: b.sectors_above_50d,
        sector_count: b.sector_count,
        explain: b.explain,
        history,
        // The map's tape reads change_1d, and so does the payload. It was
        // mapping from `i.change`, which no row carries, so every index on the
        // tape rendered without its move.
        indexes: b.indexes?.map((i) => ({ symbol: i.symbol, price: i.price, change_1d: i.change_1d })),
      },
      sectors: complete.map((r) => ({ ...r, verdict: r.verdict ?? '' })) as SectorRow[],
    }
  })()
  const above = n(b.sectors_above_50d)
  const count = n(b.sector_count)
  const regime = typeof data.macro?.regime === 'string'
    ? data.macro.regime
    : (data.macro?.regime as Record<string, unknown> | undefined)?.state as string | undefined

  return (
    <>
      <ObjectHeader
        glyph="M"
        name="Market"
        kind="live vendor data, not point-in-time"
        state="live"
        detail={data.generated_at ? `generated ${data.generated_at.slice(0, 19)}${data.cached ? ', cached' : ''}` : undefined}
        facts={[
          { label: 'Breadth', value: n(b.breadth_score), kind: 'percent', digits: 0, title: b.explain ?? undefined },
          { label: 'Above 50d', value: above, digits: 0, kind: 'count' },
          { label: 'Sectors', value: count, digits: 0, kind: 'count' },
          { label: 'Regime', value: regime ?? null, digits: 0, kind: 'count' },
          { label: 'Events', value: data.events?.length ?? null, digits: 0 , kind: 'count'},
        ]}
      />


      {/* Before the detail: what moved since this reader last looked. A daily
          user opens a market page to find the delta, and making them
          reconstruct it from six panels is making them do arithmetic the
          product already has the data to do. */}
      <WhatChanged data={data} />

      {/* Eleven sectors on a shared rebased scale. A number says where a
          sector ended; the line says how it got there, and a sector up four
          percent in a straight line is not the same market as one up four
          percent after a twelve percent round trip.

          The map draws a sparkline per sector from `history`, which this
          workspace's own payload type does not even declare — so the rows are
          checked for it rather than cast into the shape the map wants. A map
          with three of eleven sectors missing their line is a map that reports
          a flat sector as a quiet one. */}
      {mappable ? <MarketMap breadth={mappable.breadth} sectors={mappable.sectors} /> : null}

      <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'minmax(0, 1.4fr) minmax(0, 1fr)' }}>
        <Panel title="Breadth" subtitle={b.explain ? undefined : 'share of sectors above their 50-day average'} state="live">
          {history.length > 1 ? (
            <TimeSeries
              series={[{ name: 'breadth', points: history, color: 'var(--ink)' }]}
              unit="share of sectors above their 50-day average"
              method="count of sector ETFs trading above a 50-session simple moving average, over the tracked set"
              height={200}
            />
          ) : (
            <StateBlock state="unavailable" title="No breadth history recorded" detail="The current reading is shown above; the series behind it was not returned." />
          )}
          {b.explain ? (
            <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)', maxWidth: '82ch' }}>
              {b.explain}
            </p>
          ) : null}
          <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-faint)', lineHeight: 'var(--lh-body)' }}>
            A breadth score means something different rising than falling, which is
            why the series is shown rather than the number alone.
          </p>
        </Panel>

        <Panel title="Leadership" state="live">
          <table className="sys-table sys-table--compact">
            <tbody>
              <tr><td>Leading</td><td className="num" style={{ textAlign: 'left' }}>{b.leadership ?? <span className="sys-null">—</span>}</td></tr>
              <tr><td>Lagging</td><td className="num" style={{ textAlign: 'left' }}>{b.laggard ?? <span className="sys-null">—</span>}</td></tr>
            </tbody>
          </table>
          {b.indexes?.length ? (
            <div style={{ marginTop: 'var(--d-3)' }}>
              <div className="sys-label" style={{ marginBottom: 'var(--d-1)' }}>Indexes</div>
              <table className="sys-table sys-table--compact">
                <thead>
                  <tr>
                    <th>Index</th>
                    <th className="num">Last</th>
                    <th className="num">1 day</th>
                    <th className="num">1 week</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {b.indexes.map((i) => (
                    <tr key={i.symbol}>
                      <td className="sys-mono">{i.symbol}</td>
                      <td className="num"><Value value={n(i.price)} kind="currency" /></td>
                      <td className="num"><Value value={n(i.change_1d)} kind="percent" digits={2} signed tone /></td>
                      <td className="num"><Value value={n(i.change_1w)} kind="percent" digits={2} signed tone /></td>
                      <td><span className="sys-meta">{i.source ?? '—'}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </Panel>
      </div>

      <Panel title="Sectors" subtitle={`${sectors.length} tracked`} flush>
        <DataTable
          columns={columns} rows={sectors} rowKey={(s) => s.symbol}
          density="compact" filterPlaceholder="filter sectors"
          initialSort={{ key: 'm63', direction: 'desc' }}
          onSelect={(s) => recordVisit({ kind: 'security', id: s.symbol, label: s.symbol, detail: s.name })}
        />
      </Panel>

      <Grid>
        <Panel title="Momentum dispersion" subtitle="63-day, by sector">
          <BarRows
            unit="63-day momentum"
            rows={[...sectors]
              .sort((a, b2) => (n(b2.momentum_63d) ?? 0) - (n(a.momentum_63d) ?? 0))
              .map((s) => ({ label: s.symbol, value: n(s.momentum_63d), note: s.name }))}
          />
          <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
            The spread between the top and bottom sector is the cross-sectional
            opportunity a long/short book is trying to capture. A narrow spread
            means there is little to separate, whatever the index level does.
          </p>
        </Panel>

        <Panel title="Volatility by sector">
          <BarRows
            unit="annualised volatility"
            rows={[...sectors]
              .sort((a, b2) => (n(b2.volatility) ?? 0) - (n(a.volatility) ?? 0))
              .map((s) => ({ label: s.symbol, value: n(s.volatility), note: s.name }))}
          />
        </Panel>
      </Grid>

      {data.macro?.cards?.length ? (
        <Panel title="Macro" state="live" subtitle={data.macro.note ?? undefined}>
          <div className="sys-strip sys-strip--wrap">
            {data.macro.cards.map((c, i) => (
              <div className="sys-strip-item" key={c.label ?? i}>
                <span className="k">{c.label ?? '—'}</span>
                <span className="v">
                  {typeof c.value === 'number'
                    ? <Value value={c.value} digits={2} unit={c.unit ?? undefined} />
                    : <span className="sys-num">{c.value ?? '—'}</span>}
                </span>
                {c.source || c.as_of ? (
                  <span className="sys-meta" style={{ display: 'block', marginTop: 2 }}>
                    {[c.source, c.as_of?.slice(0, 10)].filter(Boolean).join(' · ')}
                  </span>
                ) : null}
              </div>
            ))}
          </div>
        </Panel>
      ) : null}

      {data.events?.length ? (
        <Panel title="Events" subtitle={`${data.events.length} ahead`} flush>
          <div className="sys-scroll-x">
            <table className="sys-table sys-table--compact">
              <thead>
                <tr><th>Date</th><th className="num">In</th><th>Type</th><th>Event</th><th>Importance</th></tr>
              </thead>
              <tbody>
                {data.events.map((e, i) => (
                  <tr key={`${e.date}-${i}`}>
                    <td className="num">{e.date}</td>
                    <td className="num"><Value value={n(e.days_away)} kind="count" unit="d" /></td>
                    <td><span className="sys-meta sys-meta--strong">{e.type ?? '—'}</span></td>
                    <td style={{ whiteSpace: 'normal' }} title={e.explain}>{e.title ?? '—'}</td>
                    <td><Status state={importanceState(e.importance)} label={e.importance ?? 'unknown'} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : null}

      <Panel title="What this is, and is not">
        <Prose>
          Live vendor data, generated {data.generated_at?.slice(0, 19) ?? 'at an unrecorded time'}
          {data.cached ? ' and served from cache' : ''}. It is a different kind of
          number from the recorded research elsewhere in this product: it describes
          the market now, changes between one view and the next, and is not
          point-in-time. No factor and no experiment is built from it.
        </Prose>
      </Panel>
    </>
  )
}
