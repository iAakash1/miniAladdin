/**
 * Portfolio workbench.
 *
 * Book, exposure, return, cost and attribution — with the cost section stated
 * on both bases, because the two figures published there sit on different ones
 * and multiplying the wrong pair understates the charge by exactly two.
 *
 * Risk lives in its own workspace and is linked to rather than duplicated here.
 * Two implementations of the same table eventually disagree.
 *
 * The allocator is selectable, and that is the argument rather than a
 * convenience. A reader who suspects the construction is what makes the signal
 * look poor can change it and watch the answer stay poor. Equal weight is in
 * the list for the same reason — it does no estimation, so it has no estimation
 * error to blame, and a signal that cannot beat it has not shown anything.
 */
'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { Grid, Panel, Prose, Section, StateBlock, Status, Strip, Value } from '@/components/system'
import { DataTable, type DataColumn } from '@/components/system/DataTable'
import { BarRows, Histogram } from '@/components/system/charts'
import { recordVisit } from '@/lib/research/history'
import { ObjectHeader, StripSkeleton, TableSkeleton } from '@/components/system/composition'

interface Method { name: string; description: string }
interface Weight { symbol: string; weight: number; side: string; signal?: number | null; risk_share: number | null }
interface Payload {
  status: string
  experiment_id?: string
  model_id?: string
  target?: string
  as_of?: string
  method?: string
  allocation?: Record<string, unknown>
  weights?: Weight[]
  risk?: { metrics?: Record<string, { value: number | null; method: string }> }
  risk_contributions_unavailable?: string | null
  cost?: {
    breakdown?: Record<string, number>
    waterfall?: Record<string, unknown>
    assumptions?: Record<string, unknown>
  }
  note?: string
}

export default function PortfolioWorkbench() {
  // The response is tagged with the allocator it was requested for. A result
  // for a method the reader has already moved on from is ignored at render
  // rather than cleared inside the effect, which keeps the loading state
  // truthful without a synchronous setState during the effect.
  const [result, setResult] = useState<{ method: string; data?: Payload; error?: string } | null>(null)
  const [methods, setMethods] = useState<Method[]>([])
  const [method, setMethod] = useState('risk_parity')

  useEffect(() => {
    let alive = true
    fetch('/api/quant/portfolio/methods')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: { methods?: Method[] } | Method[]) => {
        if (alive) setMethods(Array.isArray(d) ? d : (d.methods ?? []))
      })
      // The allocator list failing is not a reason to hide the book. The
      // current allocator still renders; the reader just cannot switch.
      .catch(() => { if (alive) setMethods([]) })
    return () => { alive = false }
  }, [])

  useEffect(() => {
    let alive = true
    fetch(`/api/quant/portfolio?method=${encodeURIComponent(method)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: Payload) => { if (alive) setResult({ method, data: d }) })
      .catch((e: Error) => { if (alive) setResult({ method, error: e.message }) })
    return () => { alive = false }
  }, [method])

  const current = result?.method === method ? result : null
  const data = current?.data ?? null
  const error = current?.error ?? null

  if (error) {
    return (
      <Panel title="Book" state="unavailable">
        <StateBlock state="unavailable" title="No book is available" detail={`Request failed: ${error}. Nothing is shown in its place.`} />
      </Panel>
    )
  }
  if (!data) {
    return (
      <>
        <StripSkeleton />
        <Panel title="Book" subtitle="constructing from the latest predictions" state="waking" flush>
          <TableSkeleton rows={10} columns={5} />
        </Panel>
      </>
    )
  }

  const weights = data.weights ?? []
  const longs = weights.filter((w) => w.weight > 0)
  const shorts = weights.filter((w) => w.weight < 0)
  const gross = weights.reduce((s, w) => s + Math.abs(w.weight), 0)
  const net = weights.reduce((s, w) => s + w.weight, 0)
  const assumptions = (data.cost?.assumptions ?? {}) as Record<string, unknown>

  // Concentration on gross weight shares. Squared shares, so one large position
  // moves this far more than several small ones — which is the point.
  const shares = gross > 0 ? weights.map((w) => Math.abs(w.weight) / gross) : []
  const herfindahl = shares.length ? shares.reduce((s, v) => s + v * v, 0) : null
  const effectiveNames = herfindahl && herfindahl > 0 ? 1 / herfindahl : null
  const topFive = shares.length
    ? [...shares].sort((a, b) => b - a).slice(0, 5).reduce((s, v) => s + v, 0)
    : null

  const columns: DataColumn<Weight>[] = [
    {
      key: 'sym', header: 'Symbol', width: '18%',
      sort: (w) => w.symbol, text: (w) => w.symbol,
      // Every holding is a link into its own workspace. This is the edge that
      // makes the book part of the object graph rather than a terminal list.
      render: (w) => (
        <Link href={`/terminal/security?symbol=${encodeURIComponent(w.symbol)}`} style={{ color: 'inherit', fontFamily: 'var(--font-mono)' }}>
          {w.symbol}
        </Link>
      ),
    },
    { key: 'side', header: 'Side', width: '12%', sort: (w) => w.side, text: (w) => w.side, render: (w) => <Status state={w.weight >= 0 ? 'recorded' : 'experimental'} label={w.side} /> },
    { key: 'w', header: 'Weight', unit: 'share of capital', numeric: true, sort: (w) => w.weight, render: (w) => <Value value={w.weight} digits={6} signed tone /> },
    { key: 'abs', header: 'Gross weight', unit: 'share of capital', numeric: true, optional: true, sort: (w) => Math.abs(w.weight), render: (w) => <Value value={Math.abs(w.weight)} digits={6} /> },
    { key: 'sig', header: 'Signal', unit: 'rank', numeric: true, sort: (w) => w.signal ?? null, render: (w) => <Value value={w.signal ?? null} digits={6} signed /> },
    {
      key: 'rc', header: 'Risk share', unit: 'share of vol', numeric: true, sort: (w) => w.risk_share,
      render: (w) => <Value value={w.risk_share} digits={4} title={w.risk_share === null ? 'Not available: the covariance could not describe this book' : undefined} />,
    },
    {
      key: 'ratio', header: 'Risk per unit weight', unit: 'ratio', numeric: true, optional: true,
      sort: (w) => (w.risk_share !== null && Math.abs(w.weight) > 0 ? w.risk_share / Math.abs(w.weight) : null),
      render: (w) => (
        <Value
          value={w.risk_share !== null && Math.abs(w.weight) > 0 ? w.risk_share / Math.abs(w.weight) : null}
          digits={3}
          title="Above 1 means the position carries more risk than its size suggests"
        />
      ),
    },
  ]

  return (
    <>
      <ObjectHeader
        glyph="B"
        name="Book"
        kind={[data.model_id, data.target].filter(Boolean).join(' · ') || 'research allocation'}
        state={data.status === 'ok' ? 'recorded' : 'unavailable'}
        detail={data.as_of ? `as of ${data.as_of}` : undefined}
        facts={[
          { label: 'Positions', value: weights.length, digits: 0 , kind: 'count'},
          { label: 'Long', value: longs.length, digits: 0, kind: 'count' },
          { label: 'Short', value: shorts.length, digits: 0, kind: 'count' },
          { label: 'Gross', value: gross, digits: 4, kind: 'magnitude', title: 'Sum of absolute weights. The size of the bet, and never negative.' },
          { label: 'Net', value: net, digits: 4, kind: 'weight', title: 'Sum of signed weights. Near zero for a dollar-neutral book.' },
          { label: 'Method', value: data.method ?? null, digits: 0 },
        ]}
        actions={
          <>
            {methods.length ? (
              <label className="sys-run">
                <span className="sys-label">Allocator</span>
                <select
                  className="sys-input"
                  value={method}
                  onChange={(e) => setMethod(e.target.value)}
                  title="Change how the book is constructed from the same signal"
                >
                  {methods.map((m) => (
                    <option key={m.name} value={m.name}>{m.name.replace(/_/g, ' ')}</option>
                  ))}
                </select>
              </label>
            ) : null}
            <Link href="/terminal/risk" className="sys-btn">risk</Link>
          </>
        }
      />

      {/* What the selected allocator assumes, in its own words. Reading a book
          without knowing whether its construction ignores correlation, or will
          short, or consumes an expected-return vector it did not create, is
          reading a result without its method. */}
      {methods.find((m) => m.name === (data.method ?? method)) ? (
        <Panel title="What this allocator assumes" state="recorded">
          <Prose>
            <strong className="sys-mono">{(data.method ?? method).replace(/_/g, ' ')}</strong>
            {' — '}
            {methods.find((m) => m.name === (data.method ?? method))?.description}
          </Prose>
          <Prose size="tight">
            Changing the allocator rebuilds the book from the same signal. If the
            result stays poor across every construction, the construction is not
            what is wrong with it — and equal weight is in this list because it
            does no estimation, so it has no estimation error to blame.
          </Prose>
        </Panel>
      ) : null}

      <Strip metrics={[
      ]} />

      {data.risk_contributions_unavailable ? (
        <Panel title="Risk share" state="unavailable">
          <StateBlock
            state="unavailable"
            title="Risk contributions are not available for this book"
            detail={data.risk_contributions_unavailable}
          />
        </Panel>
      ) : null}

      <Panel
        title="Book"
        subtitle={[data.model_id, data.target, data.as_of].filter(Boolean).join(' · ')}
        state={data.status === 'ok' ? 'recorded' : 'unavailable'}
        flush
        actions={<Link href="/terminal/risk" className="sys-meta sys-meta--strong">Risk →</Link>}
      >
        <DataTable
          columns={columns} rows={weights} rowKey={(w) => w.symbol}
          density="compact" filterPlaceholder="filter positions"
          initialSort={{ key: 'abs', direction: 'desc' }}
          onSelect={(w) => recordVisit({ kind: 'security', id: w.symbol, label: w.symbol, detail: w.side })}
        />
      </Panel>

      <Grid>
        <Panel title="Largest positions" subtitle="by gross weight">
          <BarRows
            unit="weight"
            rows={[...weights]
              .sort((a, b) => Math.abs(b.weight) - Math.abs(a.weight))
              .slice(0, 12)
              .map((w) => ({ label: w.symbol, value: w.weight, note: `${w.side}, risk share ${w.risk_share?.toFixed(4) ?? 'not available'}` }))}
          />
        </Panel>

        <Panel title="Weight distribution">
          <Histogram
            values={weights.map((w) => w.weight)}
            unit="weight"
            bins={20}
            title=""
            marks={[{ at: 0, label: '0', color: 'var(--rule-focus)' }]}
          />
          <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
            A book that is dollar-neutral by construction should be roughly
            symmetric here; a lean to one side is a net exposure the gross figure
            above does not show.
          </p>
        </Panel>

        <Panel title="Concentration">
          <Section title="Effective breadth">
            <table className="sys-table sys-table--compact">
              <tbody>
                <tr><td>Positions</td><td className="num"><Value value={weights.length} kind="count" /></td></tr>
                <tr>
                  <td>Herfindahl</td>
                  <td className="num"><Value value={herfindahl} digits={5} title="Sum of squared gross weight shares" /></td>
                </tr>
                <tr>
                  <td>Effective names</td>
                  <td className="num"><Value value={effectiveNames} digits={2} title="1 / Herfindahl. Counting positions overstates breadth when sizes are uneven." /></td>
                </tr>
                <tr>
                  <td>Top 5 share</td>
                  <td className="num"><Value value={topFive} digits={4} /></td>
                </tr>
              </tbody>
            </table>
            <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
              Effective names counts by size, not by ticker. It is a statement
              about weights only — whether those names are really independent bets
              is a covariance question, answered in Risk.
            </p>
          </Section>
        </Panel>

        <Panel title="Cost assumptions" state="recorded">
          <table className="sys-table sys-table--compact">
            <tbody>
              {Object.entries(assumptions)
                .filter(([, v]) => typeof v === 'number' || typeof v === 'string')
                .map(([k, v]) => (
                  <tr key={k}>
                    <td style={{ fontFamily: 'var(--font-mono)', width: '46%' }}>{k}</td>
                    <td className="num" style={{ whiteSpace: 'normal', textAlign: 'left' }}>
                      {typeof v === 'number'
                        ? <Value value={v} digits={2} />
                        : <span className="sys-meta sys-meta--strong">{String(v)}</span>}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
          <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-micro)', color: 'var(--ink-faint)', lineHeight: 'var(--lh-body)' }}>
            Costs are charged on the round-trip notional. Reported turnover is
            one-way, so the two differ by exactly two and only the round-trip
            figure reproduces the charge.
          </p>
        </Panel>

        <Panel title="Cost breakdown">
          {data.cost?.breakdown && Object.keys(data.cost.breakdown).length ? (
            <table className="sys-table sys-table--compact">
              <tbody>
                {Object.entries(data.cost.breakdown).map(([k, v]) => (
                  <tr key={k}>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{k}</td>
                    <td className="num"><Value value={typeof v === 'number' ? v : null} digits={4} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <StateBlock
              state="unavailable"
              title="No breakdown recorded"
              detail="The cost model returned a total without its commission, spread, slippage and impact components — which happens when no trade was charged for this rebalance."
            />}
        </Panel>

        <Panel title="Allocation">
          {data.allocation && Object.keys(data.allocation).length ? (
            <table className="sys-table sys-table--compact">
              <tbody>
                {Object.entries(data.allocation)
                  .filter(([, v]) => typeof v === 'number' || typeof v === 'string' || typeof v === 'boolean')
                  .map(([k, v]) => (
                    <tr key={k}>
                      <td style={{ fontFamily: 'var(--font-mono)', width: '52%' }}>{k}</td>
                      <td className="num">
                        {typeof v === 'number' ? <Value value={v} digits={4} /> : <span className="sys-meta sys-meta--strong">{String(v)}</span>}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          ) : <StateBlock
              state="unavailable"
              title="No allocation diagnostics recorded"
              detail="The optimiser returned weights without its constraint report, so which constraints bound and which were slack is unknown for this book."
            />}
        </Panel>
      </Grid>

      {data.note ? (
        <Panel title="Note">
          <Prose>{data.note}</Prose>
        </Panel>
      ) : null}
    </>
  )
}
