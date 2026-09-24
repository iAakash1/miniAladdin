'use client'

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import { newsItem } from '../Activity'
import { SeriesUnavailable } from '../ChartPanel'
import { DepthControl } from '../Depth'
import { FilingDoc } from '../Filings'
import PriceChart from '../PriceChart'
import { Cites, Lead, SynthesisMeta, citationIndex, sourceLabel, synthesisStatus } from '../Synthesis'
import { DeterministicConclusion, FactorTable, Table } from '../Conclusion'
import { Diverging } from '../Panels'
import { FAMILY_LABEL, FAMILY_ORDER, familyScore, providerSet, signalTone } from '../derive'
import { usePriceSeries } from '../useCompany'
import { useEntitlement } from '@/components/system/Entitlement'
import CompanyMark from '@/components/ui/CompanyMark'
import SectorMark, { sectorKey } from '@/components/visual/SectorMark'
import Timeline from '@/components/visual/Timeline'
import { currentSectionId, pinnedSection, scrollToSection, workspaceRoot } from '@/lib/section-nav'
import { venueLabel } from '@/lib/text'
import type { Analysis } from '@/lib/types'

/** Height of the sticky tab bar the report scrolls beneath. */
const STICKY_OFFSET = 56

interface SectionDef { id: string; label: string }

function Section({ id, title, kind, children }: {
  id: string
  title: string
  /** Whether the section is deterministic output or generated explanation. */
  kind?: 'deterministic' | 'synthesis' | 'source'
  children: ReactNode
}) {
  return (
    <section id={id} className="rp-section" style={{ scrollMarginTop: STICKY_OFFSET }}>
      <header className="rp-section__head">
        <h2>{title}</h2>
        {kind ? (
          <span className="rp-kind" data-kind={kind}>
            {kind === 'deterministic' ? 'Deterministic' : kind === 'synthesis' ? 'Grounded synthesis' : 'Primary source'}
          </span>
        ) : null}
      </header>
      {children}
    </section>
  )
}

/** The reading line: just below the sticky tab bar, where a heading arrives. */
const READING_LINE = STICKY_OFFSET + 24

type Pin = { id: string; target: number; until: number } | null

function useSpy(ids: string[]): { current: string | null; pin: (id: string, target: number | null) => void } {
  const [current, setCurrent] = useState<string | null>(ids[0] ?? null)
  const pinRef = useRef<Pin>(null)
  useEffect(() => {
    const root = workspaceRoot()
    if (!root || !ids.length) return undefined
    let frame = 0
    const measure = () => {
      frame = 0
      const pinned = pinnedSection(pinRef.current, root.scrollTop, Date.now())
      if (pinned) { setCurrent(pinned); return }
      pinRef.current = null
      const rootTop = root.getBoundingClientRect().top
      const tops = ids
        .map((id) => {
          const el = document.getElementById(id)
          return el ? { id, top: el.getBoundingClientRect().top - rootTop } : null
        })
        .filter((x): x is { id: string; top: number } => x !== null)
      // At the very bottom the last section is current even if short.
      const atEnd = root.scrollTop + root.clientHeight >= root.scrollHeight - 4
      setCurrent(atEnd ? ids[ids.length - 1] : currentSectionId(tops, READING_LINE))
    }
    const onScroll = () => { if (!frame) frame = window.requestAnimationFrame(measure) }
    measure()
    root.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll, { passive: true })
    return () => {
      root.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
      if (frame) window.cancelAnimationFrame(frame)
    }
  }, [ids])
  const pin = (id: string, target: number | null) => {
    if (target === null) return
    pinRef.current = { id, target, until: Date.now() + 900 }
    setCurrent(id)
  }
  return { current, pin }
}

function Outline({ sections, current, onPick }: {
  sections: SectionDef[]
  current: string | null
  onPick: (id: string, target: number | null) => void
}) {
  return (
    <nav className="rp-outline" aria-label="Report sections">
      <p className="sys-label">Contents</p>
      <ol>
        {sections.map((s, i) => (
          <li key={s.id}>
            <a
              href={`#${s.id}`}
              aria-current={current === s.id ? 'location' : undefined}
              onClick={(e) => {
                e.preventDefault()
                onPick(s.id, scrollToSection(s.id, STICKY_OFFSET))
                window.history.replaceState(null, '', `#${s.id}`)
              }}
            >
              <span className="rp-outline__n">{String(i + 1).padStart(2, '0')}</span>
              {s.label}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  )
}

const signed = (v: number, d = 3) => `${v >= 0 ? '+' : ''}${v.toFixed(d)}`
const pct = (v: number | undefined, d = 1) => (v === undefined || !Number.isFinite(v) ? '—' : `${v.toFixed(d)}%`)
const mult = (v: number | undefined, d = 1) => (v === undefined || !Number.isFinite(v) ? '—' : `${v.toFixed(d)}×`)
function money(v: number): string {
  const a = Math.abs(v)
  if (a >= 1e12) return `${(v / 1e12).toFixed(2)}T`
  if (a >= 1e9) return `${(v / 1e9).toFixed(2)}B`
  if (a >= 1e6) return `${(v / 1e6).toFixed(1)}M`
  return v.toLocaleString('en-US')
}

/** Figure 1: the price the report is written against. */
function PriceFigure({ a }: { a: Analysis }) {
  const { series, loading } = usePriceSeries(a.ticker, '3mo')
  const points = series?.points ?? []
  if (loading) return <div className="sys-skeleton rp-figure__skeleton" aria-label="Loading price history" />
  if (points.length < 2) return <div className="rp-figure"><SeriesUnavailable series={series} /></div>
  const first = points[0].close
  const last = points[points.length - 1].close
  const change = first ? ((last - first) / first) * 100 : null
  const closes = points.map((p) => p.close)
  return (
    <figure className="rp-figure">
      <PriceChart points={points} height={240} label={`${a.ticker} daily close and volume, three months`} />
      <figcaption>
        <b>Figure 1.</b> {a.ticker} daily close and volume over three months ({points.length} sessions
        {series?.source ? `, ${series.source}` : ''}). Range {Math.min(...closes).toFixed(2)}–{Math.max(...closes).toFixed(2)}
        {change !== null ? `, ${change >= 0 ? '+' : ''}${change.toFixed(1)}% over the window` : ''}.
      </figcaption>
    </figure>
  )
}

function Masthead({ a }: { a: Analysis }) {
  const q = a.quant
  const p = a.profile
  const sector = p?.sector ?? a.sector
  const meta = [venueLabel(p?.exchange ?? null), sector, p?.industry && p.industry !== p.sector ? p.industry : null].filter(Boolean)
  const figures: Array<[string, string, string | undefined]> = [
    ['Signal', a.riskAdjusted, signalTone(a.riskAdjusted) ?? undefined],
    ['Confidence', a.engineConfidence !== null ? `${a.engineConfidence}/100` : '—', undefined],
    ['Risk', q ? `${q.riskScore} · ${(a.riskLevel ?? '').toLowerCase()}` : (a.riskLevel ?? '—').toLowerCase(), undefined],
    ['Evidence', a.decisionQuality ? a.decisionQuality.grade.toLowerCase() : '—', undefined],
    ['Price', a.consensusPrice ? a.consensusPrice.consensus.toFixed(2) : '—', undefined],
  ]
  return (
    <header className="rp-title" data-sector={sector ? sectorKey(sector) : undefined}>
      <div className="rp-title__id">
        <CompanyMark ticker={a.ticker} name={a.companyName} size={46} />
        <div className="rp-title__text">
          <p className="sys-label">Research report · {a.ticker}</p>
          <h1>{a.companyName}</h1>
          {meta.length ? (
            <p className="rp-title__sub">
              {sector ? <SectorMark sector={sector} size={16} /> : null}
              {meta.join(' · ')}
            </p>
          ) : null}
        </div>
      </div>
      <dl className="rp-keyfig" aria-label="Deterministic state">
        {figures.map(([k, v, tone]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd data-tone={tone}>{v}</dd>
          </div>
        ))}
      </dl>
      <p className="rp-title__meta">
        {a.provenance?.generated_at ? `Run ${new Date(a.provenance.generated_at).toUTCString().replace(' GMT', ' UTC')}` : null}
        {q?.modelVersion ? ` · engine ${q.modelVersion}` : null}
        {` · ${providerSet(a).length} providers`}
        {a.elapsedSeconds !== null ? ` · ${a.elapsedSeconds.toFixed(1)}s` : null}
        {' · the signal, confidence and risk above are the engine’s; narrative sections are marked'}
      </p>
    </header>
  )
}

/**
 * What the report's own figures mean, for a reader new to them. These are
 * fixed definitions of the engine's outputs — not generated text — so they are
 * the same for every company and every run.
 */
function ReadingGuide({ a }: { a: Analysis }) {
  const q = a.quant
  return (
    <aside className="rp-guide" aria-label="How to read this report">
      <p className="sys-label">How to read this report</p>
      <dl>
        <div>
          <dt>Signal <b>{a.riskAdjusted}</b></dt>
          <dd>The engine&apos;s conclusion, on a scale from Strong Sell to Strong Buy, from five weighted families of evidence. Market stress can only soften the momentum part.</dd>
        </div>
        <div>
          <dt>Confidence <b>{a.engineConfidence ?? '—'}/100</b></dt>
          <dd>Starts at 100 and loses points when the evidence families disagree, when data is missing or old, and while the model&apos;s track record on this company is unmeasured. Each deduction is listed below.</dd>
        </div>
        <div>
          <dt>Risk {q ? <b>{q.riskScore}/100</b> : null}</dt>
          <dd>How the stock has behaved — how far and how often it has fallen, how volatile it is, how much it moves with the market. Higher means riskier; it is not a forecast.</dd>
        </div>
        <div>
          <dt>Evidence quality {a.decisionQuality ? <b>{a.decisionQuality.grade.toLowerCase()}</b> : null}</dt>
          <dd>Whether the inputs behind the signal were complete, recent and consistent with each other.</dd>
        </div>
      </dl>
      <p className="rp-guide__note">The narrative sections are an explanation of these results, written afterwards. They never change them.</p>
    </aside>
  )
}

const ITEM_NAME: Record<string, string> = { key_catalysts: 'catalyst', key_risks: 'risk', things_to_watch: 'watch item' }

/** "key_catalysts.2" reads as "catalyst 3"; "bear_case" as "bear case". */
function sectionName(key: string): string {
  const [root, index] = key.split('.')
  return index !== undefined && ITEM_NAME[root] ? `${ITEM_NAME[root]} ${Number(index) + 1}` : root.replace(/_/g, ' ')
}

/** The narrative's own provenance, for a reader auditing it. */
function NarrativeMeta({ ai, cited }: { ai: NonNullable<Analysis['ai']>; cited: number }) {
  const withheld = (ai.validation?.droppedSections ?? []).filter((d) => d !== 'executive_summary.replaced_by_engine')
  const rows: Array<[string, string]> = [
    ['Narrative provider', ai.provider ?? '—'],
    ['Model', ai.model ?? '—'],
    ['Pipeline', ai.pipelineMode ?? '—'],
    ['Depth', ai.depth ?? 'intermediate'],
    ['Evidence items', `${ai.evidence.length} supplied · ${cited} cited`],
    ['Validation', ai.validation?.status?.toLowerCase() ?? 'not reported'],
    ['Withheld sections', withheld.length ? withheld.map(sectionName).join(', ') : 'none'],
    ['Snapshot', ai.snapshotId ? `${ai.snapshotId.slice(0, 12)}…${ai.cached ? ' · served from cache' : ''}` : 'not held'],
  ]
  return (
    <dl className="rp-meta">
      {rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
    </dl>
  )
}

export default function Report({ analysis: a }: { analysis: Analysis }) {
  const { isPro } = useEntitlement()
  const ai = a.ai
  const status = synthesisStatus(ai)
  const index = useMemo(() => citationIndex(ai), [ai])
  const links = ai?.evidenceLinks ?? {}
  const one = (k: string) => (Array.isArray(links[k]) && !Array.isArray((links[k] as unknown[])[0]) ? links[k] as string[] : undefined)
  const many = (k: string) => (Array.isArray(links[k]) && Array.isArray((links[k] as unknown[])[0]) ? links[k] as string[][] : undefined)
  const q = a.quant
  const gen = status.generated && ai !== null
  const depth = ai?.depth ?? 'intermediate'

  const conflicts: Array<{ what: string; detail: string }> = []
  if (a.consensusPrice?.conflict) {
    conflicts.push({ what: 'Last price', detail: `${a.consensusPrice.agreement} vendors agree · ${a.consensusPrice.dispersion_pct.toFixed(3)}% spread` })
  }
  for (const c of a.seriesIntegrity?.conflicts ?? []) {
    conflicts.push({ what: `Close on ${c.date}`, detail: `${c.divergence_pct.toFixed(2)}% divergence · ${Object.entries(c.readings).map(([p, v]) => `${p} ${v}`).join(', ')}` })
  }
  for (const m of a.seriesIntegrity?.adjustment_mismatch ?? []) {
    conflicts.push({ what: `${m.provider} history`, detail: `closes at ${m.ratio.toFixed(3)}× the others${m.likely_split ? ` — likely ${m.likely_split} split adjustment` : ''}` })
  }
  for (const c of a.statements?.conflicts ?? []) {
    conflicts.push({ what: c.field.replace(/_/g, ' '), detail: `${c.observations.map((o) => `${o.provider} ${o.value}`).join(' vs ')} · ${c.spread_pct.toFixed(1)}% spread` })
  }
  for (const c of a.profile?.conflicts ?? []) {
    conflicts.push({ what: `Profile: ${c.field.replace(/_/g, ' ')}`, detail: `${c.observations.map((o) => `${o.provider} ${o.value}`).join(' vs ')}` })
  }

  const sections: SectionDef[] = [
    { id: 'summary', label: 'Executive overview' },
    ...(q ? [{ id: 'conclusion', label: 'Deterministic conclusion' }, { id: 'drivers', label: 'Factor drivers' }] : []),
    ...(a.ratios || a.filings?.xbrl_trend?.length ? [{ id: 'fundamentals', label: 'Fundamentals' }] : []),
    ...(a.technicalIntelligence ? [{ id: 'technical', label: 'Technical state' }] : []),
    { id: 'macro', label: 'Macro context' },
    ...(a.headlines.length ? [{ id: 'news', label: 'News and events' }] : []),
    ...(a.filings?.filings.length ? [{ id: 'primary', label: 'Primary sources' }] : []),
    { id: 'risks', label: 'Risks' },
    { id: 'conflicts', label: 'Evidence conflicts' },
    ...(gen ? [{ id: 'synthesis', label: 'Grounded synthesis' }] : []),
    { id: 'sources', label: 'Sources' },
  ]
  const idKey = sections.map((s) => s.id).join('|')
  const ids = useMemo(() => idKey.split('|'), [idKey])
  const { current, pin } = useSpy(ids)

  const riskRows = [...(q?.riskComponents ?? [])].sort((x, y) => y.contribution - x.contribution)
  const r = a.ratios

  return (
    <div className="rp">
      <Outline sections={sections} current={current} onPick={pin} />

      <article className="rp-doc" aria-label={`${a.ticker} research report`}>
        <Masthead a={a} />

        {gen ? (
          <div className="rp-depth">
            <span className="sys-label">Explanation depth</span>
            <DepthControl />
          </div>
        ) : null}
        {depth === 'beginner' ? <ReadingGuide a={a} /> : null}

        <Section id="summary" title="Executive overview">
          <p className="rp-lede rp-lede--deterministic">
            The deterministic engine returns <strong>{a.riskAdjusted}</strong>
            {a.engineConfidence !== null ? <> at <strong>{a.engineConfidence}/100</strong> confidence</> : null}
            {a.riskLevel ? <> with <strong>{a.riskLevel.toLowerCase()}</strong> risk</> : null}
            {q ? <> (composite score <span className="sys-num">{signed(q.rawScore, 2)}</span>)</> : null}.
            {a.verdict !== a.riskAdjusted ? <> The raw signal was {a.verdict}; the macro regime dampened it.</> : null}
          </p>
          {gen && ai ? (
            <div className="rp-generated">
              <p className="rp-generated__label"><SynthesisMeta status={status} /></p>
              <Lead ai={ai} status={status} index={index} symbol={a.ticker} cites={one} className="rp-prose" />
              {ai.investmentThesis ? <p className="rp-prose">{ai.investmentThesis}<Cites ids={one('investment_thesis')} index={index} symbol={a.ticker} /></p> : null}
            </div>
          ) : (
            <p className="rp-note">No generated narrative for this run ({status.reason}). The sections below are the engine&apos;s output and the evidence it read.</p>
          )}
          <PriceFigure a={a} />
        </Section>

        {q ? (
          <Section id="conclusion" title="Deterministic conclusion" kind="deterministic">
            <DeterministicConclusion a={a} />
          </Section>
        ) : null}

        {q ? (
          <Section id="drivers" title="Factor drivers" kind="deterministic">
            <Table
              head={['Family', 'Weight', 'Score', '']}
              numeric={[1, 2]}
              rows={FAMILY_ORDER.map((f) => {
                const s = familyScore(a, f)
                return [FAMILY_LABEL[f], q.weightsUsed[f] !== undefined ? `${Math.round(q.weightsUsed[f] * 100)}%` : '—', s === null ? '—' : signed(s, 2), <Diverging key="b" value={s} />]
              })}
            />
            {depth === 'beginner' ? (
              <p className="rp-note">The families above are built from {q.factors.length} individual factors. Choose Intermediate or Advanced depth to see each one.</p>
            ) : (
              <>
                <h3 className="rp-h3">Every factor, by absolute contribution</h3>
                <FactorTable a={a} />
              </>
            )}
            <p className="rp-note">
              Momentum is gated by macro stress (×{q.macroGate.toFixed(2)}); value, quality and news are not.
              Data completeness {Math.round(q.dataCompleteness * 100)}%.
              {q.regimes.length ? ` Active regimes: ${q.regimes.join(', ')}.` : ''}
            </p>
          </Section>
        ) : null}

        {a.ratios || a.filings?.xbrl_trend?.length ? (
          <Section id="fundamentals" title="Fundamentals">
            {r ? (
              <Table
                head={['Measure', 'Value', 'Measure', 'Value']}
                numeric={[1, 3]}
                rows={[
                  ['P/E (TTM)', mult(r.pe_ratio), 'Gross margin (TTM)', pct(r.gross_margin_ttm)],
                  ['Price / sales', mult(r.price_to_sales), 'Operating margin (TTM)', pct(r.operating_margin_ttm)],
                  ['Price / book', mult(r.price_to_book), 'Net margin (TTM)', pct(r.net_margin_ttm)],
                  ['EV / EBITDA', mult(r.ev_to_ebitda), 'Return on equity (TTM)', pct(r.roe_ttm)],
                  ['Revenue growth (YoY)', pct(r.revenue_growth_ttm_yoy), 'Debt / equity', mult(r.debt_to_equity, 2)],
                  ['EPS growth (YoY)', pct(r.eps_growth_ttm_yoy), 'Current ratio', mult(r.current_ratio, 2)],
                ]}
              />
            ) : null}
            {r?.source ? <p className="rp-src">Ratios as computed by {r.source}; not reconciled across vendors.</p> : null}
            {a.filings?.xbrl_trend?.length ? (
              <>
                <h3 className="rp-h3">Filed with the SEC — year over year</h3>
                <Table
                  head={['Concept', 'Latest', 'Prior', 'Change', 'Form · filed']}
                  numeric={[1, 2, 3]}
                  rows={a.filings.xbrl_trend.map((t) => [
                    t.concept, `${money(t.latest_value)} FY${t.latest_year}`, `${money(t.prior_value)} FY${t.prior_year}`,
                    <span key="c" className={t.change_pct >= 0 ? 'sys-pos' : 'sys-neg'}>{t.change_pct >= 0 ? '+' : ''}{t.change_pct.toFixed(1)}%</span>,
                    `${t.form} · ${t.filed}`,
                  ])}
                />
              </>
            ) : null}
          </Section>
        ) : null}

        {a.technicalIntelligence ? (
          <Section id="technical" title="Technical state" kind="deterministic">
            <ul className="rp-findings">
              {a.technicalIntelligence.findings.map((f) => <li key={f.text} data-tone={f.tone}>{f.text}</li>)}
            </ul>
            <Table
              head={['Indicator', 'Reading', 'Detail', 'State']}
              rows={a.technicalIntelligence.indicators.map((i) => [i.label, <span key="v" className="sys-num">{i.value}</span>, i.detail, i.state])}
            />
            {gen && ai?.technicalReasoning ? <p className="rp-prose rp-prose--gen">{ai.technicalReasoning}<Cites ids={one('technical_reasoning')} index={index} symbol={a.ticker} /></p> : null}
          </Section>
        ) : null}

        <Section id="macro" title="Macro context">
          <p className="rp-prose">
            Regime <strong>{a.macro.status.toLowerCase()}</strong>
            {a.macro.srm !== null ? <>, risk multiplier <span className="sys-num">{a.macro.srm.toFixed(2)}</span></> : null}
            {a.macro.yieldSpread !== null ? <>, 10y–2y spread <span className="sys-num">{a.macro.yieldSpread.toFixed(2)}%</span></> : null}
            {a.macro.source ? <> — {a.macro.source.toUpperCase()}{a.macro.stale ? ', stale' : ''}</> : null}.
          </p>
          {a.macroContext?.rates.length ? (
            <Table
              head={['Series', 'Value', 'Change', 'As of', 'Why it matters']}
              numeric={[1, 2]}
              rows={a.macroContext.rates.map((m) => [m.label, `${m.value.toFixed(2)}${m.unit}`, m.change === null ? '—' : `${m.change >= 0 ? '+' : ''}${m.change.toFixed(2)}`, m.as_of, m.why])}
            />
          ) : null}
          {gen && ai?.macroReasoning ? <p className="rp-prose rp-prose--gen">{ai.macroReasoning}<Cites ids={one('macro_reasoning')} index={index} symbol={a.ticker} /></p> : null}
        </Section>

        {a.headlines.length ? (
          <Section id="news" title="News and events">
            {gen && ai?.newsReasoning ? <p className="rp-prose rp-prose--gen">{ai.newsReasoning}<Cites ids={one('news_reasoning')} index={index} symbol={a.ticker} /></p> : null}
            <Timeline items={a.headlines.map((h) => newsItem(h, { linked: isPro }))} limit={8} />
            {a.newsStream ? <p className="rp-src">{a.newsStream.unique} distinct stories from {a.newsStream.providers.join(', ')} · {a.newsStream.corroborated} corroborated by more than one vendor.</p> : null}
          </Section>
        ) : null}

        {a.filings?.filings.length ? (
          <Section id="primary" title="Primary sources" kind="source">
            <div className="fl-docs rp-docs">
              {a.filings.filings.slice(0, 8).map((f) => <FilingDoc key={f.accession} f={f} />)}
            </div>
            <p className="rp-src">Each document opens on SEC EDGAR. These are what the company filed; every vendor figure in this report is a reading of one.</p>
            {a.filings.restatements?.length ? (
              <>
                <h3 className="rp-h3">Restatements</h3>
                <Table
                  head={['Concept', 'Period end', 'Original', 'Revised', 'Change']}
                  numeric={[2, 3, 4]}
                  rows={a.filings.restatements.map((x) => [x.label, x.period_end, `${money(x.original_value)} (${x.original_filed})`, `${money(x.revised_value)} (${x.revised_filed})`, `${x.change_pct >= 0 ? '+' : ''}${x.change_pct.toFixed(2)}%`])}
                />
              </>
            ) : null}
          </Section>
        ) : null}

        <Section id="risks" title="Risks">
          {riskRows.length ? (
            <p className="rp-prose">
              The engine&apos;s risk score is <strong>{q?.riskScore}/100</strong>; its largest components are {riskRows.slice(0, 3).map((c) => `${c.name.replace(/_/g, ' ')} (${c.percentile.toFixed(0)}th percentile)`).join(', ')}.
            </p>
          ) : null}
          {gen && ai?.riskReasoning ? <p className="rp-prose rp-prose--gen">{ai.riskReasoning}<Cites ids={one('risk_reasoning')} index={index} symbol={a.ticker} /></p> : null}
          {gen && ai?.keyRisks.length ? (
            <ul className="rp-list">
              {ai.keyRisks.map((k, i) => <li key={k}>{k}<Cites ids={many('key_risks')?.[i]} index={index} symbol={a.ticker} /></li>)}
            </ul>
          ) : null}
        </Section>

        <Section id="conflicts" title="Evidence conflicts">
          {conflicts.length ? (
            <Table head={['Where', 'What disagrees']} rows={conflicts.map((c) => [c.what, c.detail])} />
          ) : (
            <p className="rp-prose">
              No material disagreement between providers on price, history, reported statements or identity
              {a.consensusPrice ? ` (${a.consensusPrice.agreement} price sources)` : ''}. Agreement is evidence that
              a figure was recorded consistently, not that it is right.
            </p>
          )}
        </Section>

        {gen && ai ? (
          <Section id="synthesis" title="Grounded synthesis" kind="synthesis">
            <p className="rp-generated__label"><SynthesisMeta status={status} /></p>
            {depth === 'advanced' && ai ? <NarrativeMeta ai={ai} cited={index.items.length} /> : null}
            <div className="rp-cols">
              {ai.bullCase ? <div className="rp-case" data-tone="pos"><h3 className="rp-h3">Bull case</h3><p className="rp-prose">{ai.bullCase}<Cites ids={one('bull_case')} index={index} symbol={a.ticker} /></p></div> : null}
              {ai.bearCase ? <div className="rp-case" data-tone="neg"><h3 className="rp-h3">Bear case</h3><p className="rp-prose">{ai.bearCase}<Cites ids={one('bear_case')} index={index} symbol={a.ticker} /></p></div> : null}
            </div>
            {ai.keyCatalysts.length ? (
              <>
                <h3 className="rp-h3">Catalysts</h3>
                <ul className="rp-list">{ai.keyCatalysts.map((k, i) => <li key={k}>{k}<Cites ids={many('key_catalysts')?.[i]} index={index} symbol={a.ticker} /></li>)}</ul>
              </>
            ) : null}
            {ai.thingsToWatch.length ? (
              <>
                <h3 className="rp-h3">Things to watch</h3>
                <ul className="rp-list">{ai.thingsToWatch.map((k, i) => <li key={k}>{k}<Cites ids={many('things_to_watch')?.[i]} index={index} symbol={a.ticker} /></li>)}</ul>
              </>
            ) : null}
            {ai.conclusion ? <p className="rp-prose">{ai.conclusion}<Cites ids={one('conclusion')} index={index} symbol={a.ticker} /></p> : null}
            {status.dropped.length ? <p className="rp-note">{status.dropped.length} generated section{status.dropped.length === 1 ? ' was' : 's were'} withheld because {status.dropped.length === 1 ? 'it' : 'they'} failed evidence validation.</p> : null}
          </Section>
        ) : null}

        <Section id="sources" title="Sources">
          {index.items.length ? (
            <>
              <h3 className="rp-h3">Cited evidence</h3>
              <ol className="rp-refs">
                {index.items.map(({ n, id, item }) => (
                  <li key={id} value={n}>
                    {depth !== 'beginner' ? <code>{id}</code> : null}
                    {item ? <>{depth !== 'beginner' ? ' — ' : ''}{sourceLabel(item.source)} · <span className="sys-num">{String(item.value)}</span>{item.unit ? ` ${item.unit}` : ''}{item.validation ? ` · ${item.validation.toLowerCase()}` : ''}</> : ' — not in the evidence envelope'}
                  </li>
                ))}
              </ol>
            </>
          ) : null}
          {a.provenance?.inputs.length && depth !== 'beginner' ? (
            <>
              <h3 className="rp-h3">Inputs</h3>
              <Table
                head={['Input', 'Answered by', 'Health', 'Used for']}
                rows={a.provenance.inputs.map((i) => [i.label, i.source ?? '—', i.health, i.used_for.join(', ')])}
              />
            </>
          ) : null}
          <p className="rp-note">{a.disclaimer ?? 'Research and education only — not investment advice.'}</p>
        </Section>
      </article>
    </div>
  )
}
