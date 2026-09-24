'use client'

import Link from 'next/link'
import type { ReactNode } from 'react'

import { DepthControl } from './Depth'
import { companyHref } from '@/lib/context-commands'
import type { AiAnalysis, AiEvidenceItem, Analysis } from '@/lib/types'

const SOURCE_LABEL: Record<string, string> = {
  deterministic_engine: 'deterministic engine',
  macro_evidence: 'FRED macro',
  news_reconciliation: 'news reconciliation',
}

export function sourceLabel(source: string): string {
  return SOURCE_LABEL[source] ?? source
}

const PROVIDER_LABEL: Record<string, string> = { deepseek: 'DeepSeek', groq: 'Groq' }

export interface SynthesisStatus {
  generated: boolean
  /** Why no narrative was produced, as the backend stated it. */
  reason: string | null
  provider: string | null
  model: string | null
  mode: string | null
  /** True when the primary writer failed and another provider wrote it. */
  fallback: boolean
  validated: boolean
  /** Generated sections withheld by validation. */
  dropped: string[]
  /** The generated summary failed validation and the engine's own sentence
   *  stands in its place — deterministic text, not generated. */
  engineSummary: boolean
  cited: number
  cached: boolean
  depth: string | null
}

const ENGINE_SUMMARY = 'executive_summary.replaced_by_engine'

export function synthesisStatus(ai: AiAnalysis | null): SynthesisStatus {
  if (!ai) {
    return {
      generated: false, reason: 'the explanation layer was not requested for this run',
      provider: null, model: null, mode: null, fallback: false, validated: false, dropped: [], engineSummary: false, cited: 0, cached: false, depth: null,
    }
  }
  const fallbackReason = ai.executiveSummary.match(/\(AI narrative unavailable: ([^—)]+)/)
  const withheld = ai.validation?.droppedSections ?? []
  return {
    generated: ai.generated,
    reason: ai.generated ? null : (fallbackReason ? fallbackReason[1].trim() : 'no narrative provider answered'),
    provider: ai.provider ? PROVIDER_LABEL[ai.provider] ?? ai.provider : null,
    model: ai.model,
    mode: ai.pipelineMode,
    fallback: ai.pipelineMode === 'groq_fallback',
    validated: ai.validation?.status === 'PASSED',
    dropped: withheld.filter((d) => d !== ENGINE_SUMMARY),
    engineSummary: withheld.includes(ENGINE_SUMMARY),
    cited: new Set(Object.values(ai.evidenceLinks).flat(2)).size,
    cached: ai.cached,
    depth: ai.depth,
  }
}

const MODE_LABEL: Record<string, string> = {
  fast: 'fast pipeline',
  deep: 'analyst brief + writer',
  groq_fallback: 'fallback writer',
}

/** The order sections are read in, so references number 1, 2, 3 down the page. */
const READING_ORDER = [
  'executive_summary', 'investment_thesis', 'bull_case', 'bear_case',
  'key_risks', 'key_catalysts', 'things_to_watch',
]

/**
 * Numbered references in order of first citation. The order is canonical —
 * one numbering for the synthesis, the report and the evidence ledger — and
 * starts from whichever paragraph leads, which is the verdict rationale when
 * the generated summary was replaced by the engine's.
 */
export function citationIndex(ai: AiAnalysis | null): { number: (id: string) => number | null; items: Array<{ n: number; id: string; item: AiEvidenceItem | null }> } {
  const order: string[] = []
  if (ai) {
    const lead = (ai.validation?.droppedSections ?? []).includes(ENGINE_SUMMARY) ? ['verdict_rationale'] : []
    const keys = [...new Set([...lead, ...READING_ORDER, ...Object.keys(ai.evidenceLinks)])]
    for (const key of keys) {
      const ids = ai.evidenceLinks[key]
      if (!Array.isArray(ids)) continue
      for (const id of (ids as Array<string | string[]>).flat()) {
        if (typeof id === 'string' && !order.includes(id)) order.push(id)
      }
    }
  }
  const byId = new Map((ai?.evidence ?? []).map((e) => [e.id, e]))
  return {
    number: (id) => {
      const i = order.indexOf(id)
      return i === -1 ? null : i + 1
    },
    items: order.map((id, i) => ({ n: i + 1, id, item: byId.get(id) ?? null })),
  }
}

export function Cites({ ids, index, symbol, linked = true }: {
  ids: string[] | undefined
  index: ReturnType<typeof citationIndex>
  symbol: string
  /** False where there is no ledger to open, such as a public preview. */
  linked?: boolean
}) {
  if (!ids?.length) return null
  return (
    <span className="cite">
      {ids.map((id) => {
        const n = index.number(id)
        const item = index.items.find((x) => x.id === id)?.item
        const title = item ? `${id} · ${sourceLabel(item.source)} · ${String(item.value)}` : id
        return linked ? (
          <a key={id} href={`${companyHref(symbol, 'evidence')}#ledger`} className="cite__ref" title={title}>{n ?? '?'}</a>
        ) : (
          <span key={id} className="cite__ref" title={title}>{n ?? '?'}</span>
        )
      })}
    </span>
  )
}

export function SynthesisMeta({ status }: { status: SynthesisStatus }) {
  if (!status.generated) return <span className="syn-meta">not generated · {status.reason}</span>
  const parts = [
    status.provider ? `${status.provider}${status.model ? ` ${status.model}` : ''}` : status.model,
    status.mode ? MODE_LABEL[status.mode] ?? status.mode : null,
    status.depth ? `${status.depth} depth` : null,
    status.validated
      ? `validated${status.dropped.length ? ` · ${status.dropped.length} section${status.dropped.length === 1 ? '' : 's'} withheld` : ''}`
      : 'not validated',
    `${status.cited} evidence item${status.cited === 1 ? '' : 's'} cited`,
    status.cached ? 'cached for this evidence snapshot' : null,
  ].filter(Boolean)
  return <span className="syn-meta">{parts.join(' · ')}</span>
}

/**
 * The opening paragraph. When validation rejected the generated summary, the
 * engine's sentence that replaced it is labelled as the engine's, and the
 * validated verdict rationale — if one survived — leads instead.
 */
export function Lead({ ai, status, index, symbol, cites, className = 'syn-lead', linked = true }: {
  ai: AiAnalysis
  status: SynthesisStatus
  index: ReturnType<typeof citationIndex>
  symbol: string
  cites: (key: string) => string[] | undefined
  className?: string
  linked?: boolean
}) {
  if (!status.engineSummary) {
    return <p className={className}>{ai.executiveSummary}<Cites ids={cites('executive_summary')} index={index} symbol={symbol} linked={linked} /></p>
  }
  return (
    <>
      {ai.verdictRationale ? (
        <p className={className}>{ai.verdictRationale}<Cites ids={cites('verdict_rationale')} index={index} symbol={symbol} linked={linked} /></p>
      ) : null}
      <div className="syn-engine">
        <span className="sys-label">Engine summary · deterministic</span>
        <p>{ai.executiveSummary}</p>
        <p className="syn-engine__why">The generated summary failed evidence validation, so the engine&apos;s own sentence stands in its place.</p>
      </div>
    </>
  )
}

function List({ title, items, links, index, symbol, linked }: {
  title: string
  items: string[]
  links: string[][] | undefined
  index: ReturnType<typeof citationIndex>
  symbol: string
  linked: boolean
}) {
  if (!items.length) return null
  return (
    <div className="syn-list">
      <h4 className="sys-label">{title}</h4>
      <ul>
        {items.slice(0, 4).map((text, i) => (
          <li key={text}>
            {text}
            <Cites ids={links?.[i]} index={index} symbol={symbol} linked={linked} />
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * The explanation layer, marked as such. It narrates the deterministic output
 * and cites the evidence it used; it never sets the signal, confidence or risk.
 */
export default function Synthesis({ analysis, footer, preview = false }: {
  analysis: Analysis
  footer?: ReactNode
  /** A public preview: citations show their evidence on hover but open nothing. */
  preview?: boolean
}) {
  const linked = !preview
  const ai = analysis.ai
  const status = synthesisStatus(ai)
  const index = citationIndex(ai)
  const links = ai?.evidenceLinks ?? {}
  const one = (key: string) => (Array.isArray(links[key]) && !Array.isArray((links[key] as unknown[])[0]) ? links[key] as string[] : undefined)
  const many = (key: string) => (Array.isArray(links[key]) && Array.isArray((links[key] as unknown[])[0]) ? links[key] as string[][] : undefined)

  return (
    <section className="syn" aria-label="Grounded synthesis">
      <header className="syn-head">
        <div className="syn-head__title">
          <h3>Grounded synthesis</h3>
          <span className="syn-tag">Explanation layer · does not set the signal</span>
          {status.generated && !preview ? <DepthControl compact /> : null}
        </div>
        <SynthesisMeta status={status} />
      </header>

      {status.generated && ai ? (
        <div className="syn-body">
          {status.fallback ? (
            <p className="syn-note">The primary writer was unavailable for this run; the fallback provider shown above wrote this text under the same validation.</p>
          ) : null}
          <Lead ai={ai} status={status} index={index} symbol={analysis.ticker} cites={one} linked={linked} />
          {ai.bullCase || ai.bearCase ? (
            <div className="syn-cases">
              {ai.bullCase ? (
                <div className="syn-case" data-tone="pos">
                  <h4 className="sys-label">Bull case</h4>
                  <p>{ai.bullCase}<Cites ids={one('bull_case')} index={index} symbol={analysis.ticker} linked={linked} /></p>
                </div>
              ) : null}
              {ai.bearCase ? (
                <div className="syn-case" data-tone="neg">
                  <h4 className="sys-label">Bear case</h4>
                  <p>{ai.bearCase}<Cites ids={one('bear_case')} index={index} symbol={analysis.ticker} linked={linked} /></p>
                </div>
              ) : null}
            </div>
          ) : null}
          <div className="syn-lists">
            <List title="Key risks" items={ai.keyRisks} links={many('key_risks')} index={index} symbol={analysis.ticker} linked={linked} />
            <List title="Catalysts" items={ai.keyCatalysts} links={many('key_catalysts')} index={index} symbol={analysis.ticker} linked={linked} />
            <List title="Watch" items={ai.thingsToWatch} links={many('things_to_watch')} index={index} symbol={analysis.ticker} linked={linked} />
          </div>
        </div>
      ) : (
        <div className="syn-body">
          <p className="syn-note">
            No narrative was produced for this run ({status.reason}). Nothing is generated in its
            place. The engine&apos;s own deterministic rationale follows.
          </p>
          {analysis.rationale ? (
            <div className="syn-rationale">
              <h4 className="sys-label">Engine rationale · deterministic</h4>
              <p>{analysis.rationale}</p>
            </div>
          ) : null}
        </div>
      )}

      <footer className="syn-foot">
        {footer ?? (
          <>
            <Link href={companyHref(analysis.ticker, 'report')}>Read the full report</Link>
            <Link href={`${companyHref(analysis.ticker, 'evidence')}#ledger`}>Inspect cited evidence</Link>
          </>
        )}
      </footer>
    </section>
  )
}
