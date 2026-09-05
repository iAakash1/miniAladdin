'use client'

/**
 * What the vendors report, as opposed to what the company filed.
 *
 * Kept separate from `Financials` above it on purpose. That panel shows XBRL
 * facts a company filed with the SEC; this one shows figures data vendors
 * computed and published. Putting them in one grid would make it impossible
 * to say which a given number is, and they disagree often enough that the
 * distinction matters.
 *
 * These figures were arriving on every research request and being discarded.
 * `merge_fundamentals` looked for fourteen field names on a model that
 * carries one of them, so `statements.fields` could never hold more than
 * `eps`; the figures themselves sat in `vendor_metrics` — 131 keys from
 * Finnhub, 10 from yfinance — and were dropped at the API boundary. Twenty-
 * seven comparable groups came back for Apple from one surviving field.
 *
 * The reason this is a table of *groups* rather than of figures is that the
 * same concept arrives on incompatible measurements. "Revenue" comes back
 * three times for Apple: per share for the fiscal year, per share trailing
 * twelve months, and as an absolute with no period stated at all. Those are
 * three different measurements, and the backend groups them by concept,
 * basis, period and unit together so that nothing here can difference two of
 * them. Where a group holds more than one vendor the spread is a real
 * disagreement; where it holds one, no agreement is claimed.
 *
 * Two things are deliberately not done. Nothing is converted between bases —
 * dividing an absolute revenue by a share count to compare it with a
 * per-share figure would manufacture a number no vendor reported. And no
 * group is merged with another because their values happen to match:
 * yfinance's book value of 7.36 equals Finnhub's most-recent-quarter book
 * value to the cent, and yfinance does not say what period it covers, so
 * they stay apart.
 */

import { useEffect, useState } from 'react'

import { EmptyLine, Inspectable, Panel, Prose, StateBlock, Value } from '@/components/system'
import { fetchResearch } from '@/lib/research-cache'
import { format } from '@/lib/quantity'

interface Observation {
  provider?: string
  value?: number
  vendor_key?: string
  vendor_value?: number
  scale?: number
}

interface Group {
  concept?: string
  basis?: string
  period?: string
  unit?: string
  observations?: Observation[]
  providers?: string[]
  spread_pct?: number | null
  agrees?: boolean | null
}

/** The vendor's own word for a period, spelled out once, here. */
const PERIOD: Record<string, string> = {
  TTM: 'trailing twelve months',
  FY: 'fiscal year',
  MRQ: 'most recent quarter',
}

const periodLabel = (p?: string): string => (p ? PERIOD[p] ?? p : 'not stated')

type Answer =
  | { for: string; groups: Group[]; providers: string[] }
  | { for: string; error: string }

export default function Reported({ symbol }: { symbol: string }) {
  const [answer, setAnswer] = useState<Answer | null>(null)

  useEffect(() => {
    let alive = true
    fetchResearch(symbol)
      .then((raw) => {
        if (!alive) return
        const d = (raw as { statements?: { reported?: Group[]; providers?: string[] } }).statements
        setAnswer({ for: symbol, groups: d?.reported ?? [], providers: d?.providers ?? [] })
      })
      .catch((e: Error) => { if (alive) setAnswer({ for: symbol, error: e.message }) })
    return () => { alive = false }
  }, [symbol])

  const settled = answer?.for === symbol ? answer : null
  if (!settled) {
    return (
      <Panel title="Reported figures" subtitle="what the vendors publish" state="waking">
        <StateBlock state="waking" title="Reading vendor statement figures" />
      </Panel>
    )
  }
  if ('error' in settled) {
    return (
      <Panel title="Reported figures" subtitle="what the vendors publish" state="unavailable">
        <StateBlock
          state="unavailable"
          title="Vendor statement figures could not be read"
          detail={`${settled.error}. The filed facts above come from the SEC directly and are unaffected.`}
        />
      </Panel>
    )
  }

  const groups = settled.groups
  if (!groups.length) {
    return (
      <EmptyLine label="Reported figures">
        No vendor returned statement figures for this security. That is an
        absence in the vendor responses, not a statement that the company
        reported nothing — the filed facts above come from the SEC directly.
      </EmptyLine>
    )
  }

  /* Ordered by concept so the three revenues sit together and the reader can
     see that they are three measurements rather than three attempts at one. */
  const rows = [...groups].sort((a, b) =>
    (a.concept ?? '').localeCompare(b.concept ?? '')
    || (a.basis ?? '').localeCompare(b.basis ?? '')
    || (a.period ?? '').localeCompare(b.period ?? ''))

  const disputed = rows.filter((g) => g.agrees === false).length
  const single = rows.filter((g) => (g.observations?.length ?? 0) < 2).length

  return (
    <Panel
      title="Reported figures"
      subtitle={`${settled.providers.join(' · ') || 'vendor'} — published, not filed`}
      flush
    >
      <div className="sys-scroll-x">
        <table className="sys-table sys-table--compact rep">
          <thead>
            <tr>
              <th scope="col">Figure</th>
              <th scope="col">Basis</th>
              <th scope="col">Period</th>
              <th scope="col" className="num">Value</th>
              <th scope="col">Sources</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((g) => {
              const obs = g.observations ?? []
              const first = obs[0]
              const v = first?.value
              const perShare = g.basis === 'per share'
              const key = `${g.concept}|${g.basis}|${g.period}`
              return (
                <tr key={key} className={g.agrees === false ? 'rep__split' : undefined}>
                  <td>{g.concept}</td>
                  <td className="rep__basis">{g.basis}</td>
                  <td className={g.period ? undefined : 'rep__unstated'}>
                    {periodLabel(g.period)}
                  </td>
                  <td className="num">
                    {typeof v === 'number' ? (
                      <Inspectable refValue={{
                        label: `${g.concept} · ${g.basis} · ${periodLabel(g.period)}`,
                        display: format(v, 'currency', { digits: perShare ? 2 : 0 }).text,
                        unit: g.unit,
                        claim: `${g.concept} on a ${g.basis} basis, ${g.period ? `for the ${periodLabel(g.period)}` : 'over a period the vendor did not state'}.`,
                        observation: obs.length > 1
                          ? `${obs.length} vendors published a figure for this measurement.`
                          : `One vendor published this figure${first?.vendor_key ? `, as \`${first.vendor_key}\`` : ''}.`,
                        providers: g.providers,
                        source: g.providers?.join(', '),
                        method: first && first.scale && first.scale !== 1
                          ? `as published, rescaled by ${first.scale.toLocaleString()} — the vendor reports this in millions and every other figure here is in units`
                          : 'as published by the vendor — not derived, not converted between bases',
                        /* The existing conflict primitive, fed rather than
                           reimplemented: it draws the disputed marker and
                           lists every observation in the drawer. */
                        conflict: obs.length > 1 ? {
                          observations: obs.map((o) => ({
                            provider: o.provider ?? 'unnamed',
                            value: o.value ?? null,
                          })),
                          spreadPct: g.spread_pct ?? null,
                        } : undefined,
                        assumptions: [
                          `The vendor's ${(g.concept ?? 'figure').toLowerCase()} means what its name says — this is the vendor's own computation, not a filed figure.`,
                          g.period
                            ? `The ${periodLabel(g.period)} is the vendor's own, on the company's fiscal calendar.`
                            : 'No period was supplied, so what span this covers is unknown.',
                        ],
                        failsWhen: [
                          `Compared with the same concept on any other basis or period — this is ${g.basis}${g.period ? `, ${periodLabel(g.period)}` : ' with no stated period'}, and the other rows for this figure are not.`,
                          ...(g.period ? [] : ['With no period stated, this cannot be placed on a timeline or compared with a dated figure.']),
                          ...(obs.length > 1 && g.agrees === false
                            ? [`The vendors disagree by ${g.spread_pct}% here, so at most one of them is right.`]
                            : []),
                        ],
                        status: 'recorded',
                        freshness: 're-read with each research request',
                      }}>
                        <Value value={v} kind="currency" digits={perShare ? 2 : 0} />
                      </Inspectable>
                    ) : <span className="sys-null">—</span>}
                  </td>
                  <td className="rep__src">
                    {(g.providers ?? []).join(', ')}
                    {obs.length > 1 ? (
                      <span className={g.agrees === false ? 'rep__warn' : 'rep__ok'}>
                        {g.agrees === false ? `${g.spread_pct}% apart` : 'agree'}
                      </span>
                    ) : null}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <Prose size="fine">
        Vendor-published figures, not filed ones — the SEC facts above are the
        primary source and these are each vendor&apos;s own computation. The
        same concept appears more than once where vendors measure it
        differently: revenue arrives per share for the fiscal year, per share
        trailing twelve months, and as an absolute with no period stated, and
        those are three measurements rather than three attempts at one.
        Nothing here is converted between bases and no two rows are
        differenced.{' '}
        {single ? `${single} of ${rows.length} rows rest on a single vendor and were cross-checked by nothing. ` : ''}
        {disputed ? `${disputed} show a disagreement of more than one per cent.` : ''}
      </Prose>
    </Panel>
  )
}
