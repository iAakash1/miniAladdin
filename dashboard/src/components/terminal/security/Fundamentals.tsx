/**
 * Ratios, technicals and street coverage for one name.
 *
 * Migrated from the legacy report. The grouping is by what the number is a
 * claim about, because these three families are epistemically different and
 * flattening them into one page of figures loses that:
 *
 *   ratios      accounting facts, restated periodically, current not historical
 *   technicals  arithmetic on the price series — always computable, never news
 *   street      other people's opinions, which are data about opinion
 *
 * Every ratio carries its period in its own name — `_ttm`, `_3y`, `_yoy` — and
 * those suffixes are rendered rather than stripped. A schema calling both a
 * trailing margin and a five-year average "margin" would invite exactly the
 * comparison that is wrong, and hiding the suffix in the UI reintroduces it.
 */
'use client'

import { useMemo } from 'react'

import { BarRows } from '@/components/system/charts'
import { Grid, Panel, Prose, Section, StateBlock, Status, Strip, Value, type ResearchState } from '@/components/system'

interface Ratios { [key: string]: number | undefined }

/** The vendor pre-formats `value` as a string, so it is rendered as given
 *  rather than parsed and re-formatted — reformatting a number someone else
 *  already rounded is how a unit gets lost. */
interface IndicatorRow {
  key?: string
  label?: string
  value?: string | number | null
  detail?: string | null
  state?: string | null
  tone?: string | null
}

interface Regime { label?: string; state?: string; note?: string; tone?: string }

interface Technicals {
  indicators?: IndicatorRow[]
  regimes?: Record<string, Regime | string>
  levels?: {
    close?: number; support?: number; resistance?: number
    support_distance_pct?: number; resistance_distance_pct?: number; lookback_days?: number
  }
  findings?: Array<{ text: string; tone?: string }>
  as_of?: string
  bars?: number
}

interface Street {
  recommendations?: {
    period?: string; analysts?: number; strong_buy?: number; buy?: number
    hold?: number; sell?: number; strong_sell?: number
    buy_ratio?: number | null; trend?: string; months?: number
  }
  surprises?: { quarters?: number; beats?: number; avg_surprise_pct?: number; last_surprise_pct?: number | null; last_period?: string }
  insider?: { mspr?: number; net_shares?: number | null; read?: string }
  findings?: Array<{ text: string; tone?: string }>
}

const n = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

/** Split a ratio key into its measure and the period it covers. */
function splitPeriod(key: string): { measure: string; period: string | null } {
  const m = key.match(/^(.*?)_(ttm|yoy|\d+y|ttm_yoy)$/)
  if (!m) return { measure: key.replace(/_/g, ' '), period: null }
  return { measure: m[1].replace(/_/g, ' '), period: m[2].replace(/_/g, ' ') }
}

const RATIO_GROUPS: { title: string; match: (k: string) => boolean; note: string }[] = [
  { title: 'Valuation', match: (k) => /^(pe_|price_to|ev_to)/.test(k), note: 'A multiple compares a price to a fundamental. Both move; a change here does not say which.' },
  { title: 'Margin', match: (k) => k.includes('margin'), note: 'Accounting margins, restated when a filing revises them.' },
  { title: 'Return', match: (k) => /^(roe|roa|roi)/.test(k), note: 'Return on a balance-sheet base, which the same filings restate.' },
  { title: 'Growth', match: (k) => k.includes('growth'), note: 'Growth over the period named in each key, not a general rate.' },
]

function toneState(tone?: string): ResearchState {
  const t = (tone ?? '').toLowerCase()
  if (t.includes('pos') || t.includes('bull')) return 'candidate'
  if (t.includes('neg') || t.includes('bear')) return 'blocked'
  if (t.includes('warn') || t.includes('caution')) return 'stale'
  return 'recorded'
}

export default function Fundamentals({
  ratios, technicals, street,
}: {
  ratios?: Ratios | null
  technicals?: Technicals | null
  street?: Street | null
}) {
  const ratioEntries = useMemo(
    () => Object.entries(ratios ?? {}).filter(([, v]) => typeof v === 'number' && Number.isFinite(v)) as [string, number][],
    [ratios],
  )

  const grouped = useMemo(() => {
    const seen = new Set<string>()
    const out = RATIO_GROUPS.map((g) => {
      const rows = ratioEntries.filter(([k]) => g.match(k))
      rows.forEach(([k]) => seen.add(k))
      return { ...g, rows }
    }).filter((g) => g.rows.length)
    const rest = ratioEntries.filter(([k]) => !seen.has(k))
    if (rest.length) out.push({ title: 'Other', match: () => false, note: '', rows: rest })
    return out
  }, [ratioEntries])

  const rec = street?.recommendations
  const recTotal = rec
    ? (rec.strong_buy ?? 0) + (rec.buy ?? 0) + (rec.hold ?? 0) + (rec.sell ?? 0) + (rec.strong_sell ?? 0)
    : 0

  if (!ratioEntries.length && !technicals && !street) {
    return (
      <Panel title="Fundamentals" state="unavailable">
        <StateBlock
          state="unavailable"
          title="No ratios, technicals or coverage recorded"
          detail="No vendor returned these for this name. Nothing is shown in their place."
        />
      </Panel>
    )
  }

  return (
    <>
      {grouped.length ? (
        <>
          <Grid>
            {grouped.map((g) => (
              <Panel key={g.title} title={g.title} state="live">
                <table className="sys-table sys-table--compact">
                  <tbody>
                    {g.rows.map(([k, v]) => {
                      const { measure, period } = splitPeriod(k)
                      return (
                        <tr key={k}>
                          <td>
                            {measure}
                            {/* The period is the half that makes two of these
                                comparable, so it is never dropped. */}
                            {period ? <span className="sys-meta" style={{ marginLeft: 6 }}>{period}</span> : null}
                          </td>
                          <td className="num"><Value value={v} digits={4} /></td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                {g.note ? (
                  <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-micro)', color: 'var(--ink-faint)', lineHeight: 'var(--lh-body)' }}>
                    {g.note}
                  </p>
                ) : null}
              </Panel>
            ))}
          </Grid>

          <Panel title="Reading these">
            <Prose>
              Every key carries the period it covers, and the suffix is shown rather
              than stripped: a trailing-twelve-month margin and a five-year average
              are different measurements, and a display that called both
              &quot;margin&quot; would invite exactly the comparison that is wrong.
              These are current vendor values — they describe the company now, are
              restated when a filing revises them, and cannot reconstruct what was
              knowable on a past date, which is why no factor is built from them.
            </Prose>
          </Panel>
        </>
      ) : null}

      {technicals ? (
        <Panel
          title="Technicals"
          subtitle={technicals.as_of ? `${technicals.as_of}${technicals.bars ? ` · ${technicals.bars} bars` : ''}` : undefined}
          state="live"
        >
          {technicals.regimes && Object.keys(technicals.regimes).length ? (
            <Strip metrics={Object.entries(technicals.regimes).map(([k, v]) => ({
              label: k,
              value: typeof v === 'string' ? v : (v?.label ?? v?.state ?? '—'),
              digits: 0, kind: 'count',
              title: typeof v === 'object' ? v?.note : undefined,
            }))} />
          ) : null}

          {technicals.levels ? (
            <div style={{ marginTop: 'var(--d-3)' }}>
              <Section title="Levels">
                <table className="sys-table sys-table--compact">
                  <tbody>
                    <tr><td>Close</td><td className="num"><Value value={n(technicals.levels.close)} digits={2} /></td></tr>
                    <tr><td>Support</td><td className="num"><Value value={n(technicals.levels.support)} digits={2} /></td></tr>
                    <tr><td>Distance to support</td><td className="num"><Value value={n(technicals.levels.support_distance_pct)} digits={4} signed tone /></td></tr>
                    <tr><td>Resistance</td><td className="num"><Value value={n(technicals.levels.resistance)} digits={2} /></td></tr>
                    <tr><td>Distance to resistance</td><td className="num"><Value value={n(technicals.levels.resistance_distance_pct)} digits={4} signed tone /></td></tr>
                    <tr><td>Lookback</td><td className="num"><Value value={n(technicals.levels.lookback_days)} kind="count" unit="d" /></td></tr>
                  </tbody>
                </table>
                <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-micro)', color: 'var(--ink-faint)', lineHeight: 'var(--lh-body)' }}>
                  Support and resistance are extremes of the lookback window, not
                  forecasts. They say where the price has turned before, which is a
                  description of the past.
                </p>
              </Section>
            </div>
          ) : null}

          {technicals.indicators?.length ? (
            <div style={{ marginTop: 'var(--d-3)' }} className="sys-scroll-x">
              <table className="sys-table sys-table--compact">
                <thead><tr><th>Indicator</th><th className="num">Value</th><th>Reading</th><th>Note</th></tr></thead>
                <tbody>
                  {technicals.indicators.map((r, i) => (
                    <tr key={r.key ?? r.label ?? i}>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{r.label ?? r.key ?? '—'}</td>
                      <td className="num">
                        {r.value === null || r.value === undefined
                          ? <span className="sys-null">—</span>
                          : <span className="sys-num">{String(r.value)}</span>}
                      </td>
                      <td>{r.state ? <Status state={toneState(r.tone ?? r.state)} label={r.state} /> : <span className="sys-null">—</span>}</td>
                      <td style={{ fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', whiteSpace: 'normal' }}>{r.detail ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {technicals.findings?.length ? (
            <ul style={{ margin: 'var(--d-3) 0 0', paddingLeft: 'var(--d-4)', fontSize: 'var(--t-body)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
              {technicals.findings.map((f) => <li key={f.text}>{f.text}</li>)}
            </ul>
          ) : null}

          <p style={{ margin: 'var(--d-3) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-faint)', lineHeight: 'var(--lh-body)', maxWidth: '84ch' }}>
            Technicals are arithmetic on the price series. They are always
            computable and never contain news, which makes them the one family
            here that is genuinely point-in-time — and it is why the research
            features are built from price rather than from the ratios above.
          </p>
        </Panel>
      ) : null}

      {street ? (
        <Panel title="Street" subtitle={rec?.period} state="live">
          <Grid variant="halves">
            {rec && recTotal > 0 ? (
              <Section title={`Recommendations · ${rec.analysts ?? recTotal} analysts`}>
                <BarRows
                  unit="analysts"
                  rows={[
                    { label: 'strong buy', value: n(rec.strong_buy) },
                    { label: 'buy', value: n(rec.buy) },
                    { label: 'hold', value: n(rec.hold) },
                    { label: 'sell', value: n(rec.sell) },
                    { label: 'strong sell', value: n(rec.strong_sell) },
                  ]}
                />
                <table className="sys-table sys-table--compact" style={{ marginTop: 'var(--d-2)' }}>
                  <tbody>
                    <tr><td>Buy ratio</td><td className="num"><Value value={n(rec.buy_ratio)} digits={3} /></td></tr>
                    <tr><td>Trend</td><td className="num">{rec.trend ?? '—'}</td></tr>
                    <tr><td>Over</td><td className="num"><Value value={n(rec.months)} kind="count" unit="mo" /></td></tr>
                  </tbody>
                </table>
              </Section>
            ) : null}

            {street.surprises ? (
              <Section title="Earnings surprises">
                <table className="sys-table sys-table--compact">
                  <tbody>
                    <tr><td>Quarters</td><td className="num"><Value value={n(street.surprises.quarters)} kind="count" /></td></tr>
                    <tr><td>Beats</td><td className="num"><Value value={n(street.surprises.beats)} kind="count" /></td></tr>
                    <tr><td>Average surprise</td><td className="num"><Value value={n(street.surprises.avg_surprise_pct)} digits={3} signed tone /></td></tr>
                    <tr><td>Last surprise</td><td className="num"><Value value={n(street.surprises.last_surprise_pct)} digits={3} signed tone /></td></tr>
                    <tr><td>Last period</td><td className="num">{street.surprises.last_period ?? '—'}</td></tr>
                  </tbody>
                </table>
              </Section>
            ) : null}

            {street.insider ? (
              <Section title="Insider activity">
                <table className="sys-table sys-table--compact">
                  <tbody>
                    <tr><td>Net share purchase ratio</td><td className="num"><Value value={n(street.insider.mspr)} digits={3} signed tone /></td></tr>
                    <tr><td>Net shares</td><td className="num"><Value value={n(street.insider.net_shares)} digits={0} signed /></td></tr>
                    <tr><td>Reading</td><td className="num">{street.insider.read ?? '—'}</td></tr>
                  </tbody>
                </table>
              </Section>
            ) : null}
          </Grid>

          {street.findings?.length ? (
            <ul style={{ margin: 'var(--d-3) 0 0', paddingLeft: 'var(--d-4)', fontSize: 'var(--t-body)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
              {street.findings.map((f) => <li key={f.text}>{f.text}</li>)}
            </ul>
          ) : null}

          <p style={{ margin: 'var(--d-3) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-faint)', lineHeight: 'var(--lh-body)', maxWidth: '84ch' }}>
            These are other people&apos;s opinions. That makes them data about
            opinion rather than about the company, and they are recorded here
            without being treated as evidence — a consensus is a fact about
            analysts, and it is right about as often as it is wrong.
          </p>
        </Panel>
      ) : null}
    </>
  )
}
