'use client'

import { useEffect, useState } from 'react'

import AskOmniSignal from '@/components/beginner/AskOmniSignal'
import StockActions from '@/components/beginner/StockActions'
import EvidenceHealth from '@/components/evidence/EvidenceHealth'
import ResearchHistory from '@/components/research/ResearchHistory'
import { DecisionQualityDetail } from '@/components/research/DecisionQualityBadge'
import AgentObservatory from '@/components/terminal/observatory/AgentObservatory'
import { EmptyLine, Panel, Prose, StateBlock, Strip } from '@/components/system'
import WhatIfLab from '@/components/whatif/WhatIfLab'
import { fetchAnalysis, normalizeAnalysis } from '@/lib/api'
import { signalBoundary, whyNotStronger } from '@/lib/beginner'
import { signalTone } from '@/lib/explore'
import type { Analysis, QuantFactor } from '@/lib/types'

type Load =
  | { kind: 'loading' }
  | { kind: 'error'; detail: string }
  | { kind: 'ready'; analysis: Analysis }

function topFactors(factors: QuantFactor[], direction: 'positive' | 'negative'): QuantFactor[] {
  return factors
    .filter((factor) => direction === 'positive' ? factor.contribution > 0 : factor.contribution < 0)
    .sort((a, b) => direction === 'positive'
      ? b.contribution - a.contribution
      : a.contribution - b.contribution)
    .slice(0, 5)
}

function FactorList({ factors, direction }: { factors: QuantFactor[]; direction: 'positive' | 'negative' }) {
  const rows = topFactors(factors, direction)
  if (!rows.length) {
    return <EmptyLine label="No measured factors">No factor contributed in this direction.</EmptyLine>
  }
  return (
    <ol className="obs__stages">
      {rows.map((factor) => (
        <li key={`${factor.family}-${factor.name}`} className="obs__stage">
          <span className="obs__name">{factor.name.replaceAll('_', ' ')}</span>
          <span className="obs__num">{factor.family}</span>
          <span className={factor.contribution > 0 ? 'sys-pos' : 'sys-neg'}>
            {factor.contribution > 0 ? '+' : ''}{factor.contribution.toFixed(3)}
          </span>
          <span className="obs__note">
            score {factor.score === null ? '—' : factor.score.toFixed(2)}
          </span>
        </li>
      ))}
    </ol>
  )
}

/** The same decision surface as Advanced, with research detail between plain and dense. */
export default function IntermediateAnalysis({ ticker }: { ticker: string }) {
  const [load, setLoad] = useState<Load>({ kind: 'loading' })

  useEffect(() => {
    let live = true
    fetchAnalysis(ticker, false)
      .then((raw) => { if (live) setLoad({ kind: 'ready', analysis: normalizeAnalysis(raw) }) })
      .catch((error: Error) => { if (live) setLoad({ kind: 'error', detail: error.message }) })
    return () => { live = false }
  }, [ticker])

  if (load.kind === 'loading') {
    return <StateBlock state="waking" title={`Analysing ${ticker}`} detail="providers, scoring and evidence" />
  }
  if (load.kind === 'error') {
    return <StateBlock state="unavailable" title={`${ticker} could not be analysed`} detail={load.detail} />
  }

  const a = load.analysis
  const q = a.quant
  const completeness = q?.dataCompleteness ?? null
  const sources = a.provenance?.summary.sources.length ?? null
  const fresh = a.provenance
    ? a.provenance.inputs.every((input) => !input.stale && input.health === 'ok')
    : null
  const conflicts = a.seriesIntegrity?.conflict_count
    ?? (a.consensusPrice ? Number(a.consensusPrice.conflict) : null)

  return (
    <>
      <Panel title={a.companyName || ticker} subtitle={a.sector ?? undefined}>
        <Strip metrics={[
          { label: 'Price', value: a.price === null ? null : `$${a.price.toFixed(2)}` },
          { label: '5-session return', value: a.return5d === null ? null : a.return5d * 100, kind: 'percent' },
          { label: '21-session return', value: a.return21d === null ? null : a.return21d * 100, kind: 'percent' },
          { label: 'Volatility', value: a.volatility === null ? null : a.volatility * 100, kind: 'percent' },
        ]} />
      </Panel>

      <Panel title="Signal and risk" subtitle={q?.modelVersion ?? 'production scoring engine'}>
        <p className="bg__verdict">
          <span className="xp__signal" data-tone={signalTone(a.verdict)}>{a.verdict}</span>
        </p>
        <Strip metrics={[
          { label: 'Overall score', value: q?.rawScore ?? null, kind: 'count' },
          { label: 'Confidence', value: a.engineConfidence ?? q?.confidence ?? null, kind: 'count' },
          { label: 'Risk', value: a.riskLevel ?? null },
          { label: 'Risk score', value: q?.riskScore ?? null, kind: 'count' },
          { label: 'Data complete', value: completeness === null ? null : `${Math.round(completeness * 100)}%` },
        ]} />
        <DecisionQualityDetail quality={a.decisionQuality} />
        {a.rationale ? <Prose>{a.rationale}</Prose> : null}
      </Panel>

      <Panel title="Factor scorecard" subtitle="the components used by the same engine">
        <Strip metrics={[
          { label: 'Momentum', value: q?.momentumScore ?? null, kind: 'count' },
          { label: 'Fundamental', value: q?.fundamentalScore ?? null, kind: 'count' },
          { label: 'Quality', value: q?.qualityScore ?? null, kind: 'count' },
          { label: 'News', value: q?.newsScore ?? null, kind: 'count' },
          { label: 'Reversal', value: q?.reversalScore ?? null, kind: 'count' },
        ]} />
      </Panel>

      <Panel title="Strongest contributions">
        <FactorList factors={q?.factors ?? []} direction="positive" />
      </Panel>
      <Panel title="Main cautions">
        <FactorList factors={q?.factors ?? []} direction="negative" />
      </Panel>

      {(() => {
        const boundary = signalBoundary(q?.factors, q?.rawScore ?? null)
        const notStronger = whyNotStronger(boundary)
        if (!notStronger && !boundary?.next) return null
        return (
          <Panel title="Why isn't this signal stronger?">
            {notStronger ? <Prose>{notStronger}</Prose> : null}
            {boundary?.next ? (
              <Prose size="fine">
                The raw score is {boundary.score.toFixed(3)}; it would need to move{' '}
                {boundary.next.distance.toFixed(2)} points to reach the {boundary.next.verdict}{' '}
                threshold.
              </Prose>
            ) : null}
          </Panel>
        )
      })()}

      <Panel title="Valuation and analyst context">
        <Strip metrics={[
          { label: 'P / E', value: a.peRatio, kind: 'multiple' },
          { label: 'Forward P / E', value: a.forwardPe, kind: 'multiple' },
          { label: 'EPS', value: a.eps, kind: 'currency' },
          { label: 'Analyst target', value: a.analystTarget, kind: 'currency' },
          { label: 'Beta', value: a.beta, kind: 'multiple' },
        ]} />
      </Panel>

      <EvidenceHealth
        ticker={ticker}
        completeness={completeness}
        sources={sources}
        fresh={fresh}
        conflicts={conflicts}
        mode="intermediate"
      />

      <ResearchHistory ticker={ticker} mode="intermediate" />

      <AgentObservatory initialSymbol={ticker} />
      <AskOmniSignal ticker={ticker} />
      <WhatIfLab ticker={ticker} />
      <StockActions symbol={ticker} mode="intermediate" />
    </>
  )
}
