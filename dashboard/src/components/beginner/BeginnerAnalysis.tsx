'use client'

/**
 * One security, explained plainly.
 *
 * Reads `/api/research/{ticker}` — the same endpoint the advanced terminal
 * calls, normalised through the same client — and renders a subset of it. The
 * verdict, confidence, risk and factor contributions shown here are byte-for-
 * byte the ones an advanced reader sees; there is no second model, no
 * beginner-specific scoring, and no adjustment of any number on the way to
 * the screen.
 *
 * The language rules are in lib/beginner.ts and they are the part most easily
 * lost: a signal is the model's rather than the reader's, confidence
 * describes evidence rather than outcome, and risk describes exposure rather
 * than a probability of loss.
 */

import { useEffect, useState } from 'react'

import { EmptyLine, Panel, Prose, StateBlock, Strip } from '@/components/system'
import {
  DISCLAIMER, explainCompleteness, explainConfidence, explainRisk,
  reasons, signalSentence, whatCouldChange,
} from '@/lib/beginner'
import AskOmniSignal from '@/components/beginner/AskOmniSignal'
import WhatIfLab from '@/components/whatif/WhatIfLab'
import StockActions from '@/components/beginner/StockActions'
import { fetchAnalysis, normalizeAnalysis } from '@/lib/api'
import { signalTone } from '@/lib/explore'
import type { Analysis } from '@/lib/types'

const dash = '—'

type Load =
  | { kind: 'loading' }
  | { kind: 'error'; detail: string }
  | { kind: 'ready'; analysis: Analysis }

export default function BeginnerAnalysis({ ticker }: { ticker: string }) {
  const [load, setLoad] = useState<Load>({ kind: 'loading' })

  useEffect(() => {
    let live = true
    void (async () => {
      try {
        const raw = await fetchAnalysis(ticker, false)
        if (live) setLoad({ kind: 'ready', analysis: normalizeAnalysis(raw) })
      } catch (e) {
        if (live) setLoad({ kind: 'error', detail: (e as Error).message })
      }
    })()
    return () => { live = false }
  }, [ticker])

  if (load.kind === 'loading') {
    return <StateBlock state="waking" title={`Analysing ${ticker}`} detail="providers, factors, macro" />
  }
  if (load.kind === 'error') {
    return <StateBlock state="unavailable" title={`${ticker} could not be analysed`} detail={load.detail} />
  }

  const a = load.analysis
  const quant = a.quant
  const { positive, cautious } = reasons(quant?.factors, 3)
  const changes = whatCouldChange(quant?.factors, a.verdict)
  const completeness = quant?.dataCompleteness ?? null
  const confidence = a.engineConfidence ?? quant?.confidence ?? null
  const riskScore = quant?.riskScore ?? null

  return (
    <>
      <Panel title={a.companyName || ticker} subtitle={a.sector ?? undefined}>
        <Strip
          metrics={[
            { label: 'Ticker', value: a.ticker },
            { label: 'Price', value: a.price === null ? dash : `$${a.price.toFixed(2)}` },
            // return5d arrives as a fraction; scaled once, here, because no
            // formatter in this product multiplies. Null stays null — a
            // return we could not compute is not a return of zero.
            {
              label: '5-session return',
              value: a.return5d === null ? null : a.return5d * 100,
              kind: 'percent',
            },
            { label: 'Sector', value: a.sector ?? dash },
          ]}
        />
      </Panel>

      <Panel title="What OmniSignal currently thinks">
        <p className="bg__verdict">
          <span className="xp__signal" data-tone={signalTone(a.verdict)}>
            {a.verdict ?? dash}
          </span>
        </p>
        <Prose>{signalSentence(a.verdict)}</Prose>
        <Prose>{DISCLAIMER}</Prose>

        <Strip
          metrics={[
            { label: 'Analysis confidence', value: confidence, kind: 'count' },
            { label: 'Risk level', value: a.riskLevel ?? dash },
            { label: 'Risk score', value: riskScore, kind: 'count' },
            { label: 'Data coverage', value: completeness === null ? dash
              : `${Math.round(completeness * 100)}%` },
          ]}
        />
      </Panel>

      <Panel title="How confident, and how risky">
        <Prose>{explainConfidence(confidence)}</Prose>
        <Prose>{explainRisk(a.riskLevel, riskScore)}</Prose>
        <Prose>{explainCompleteness(completeness)}</Prose>
      </Panel>

      <Panel title="Why the model likes it">
        {positive.length === 0 ? (
          <EmptyLine label="No supporting factors">
            No factor is currently contributing positively to this score.
          </EmptyLine>
        ) : (
          <ul className="bg__reasons">
            {positive.map((r) => (
              <li key={r.key} className="bg__reason" data-tone="positive">
                <span className="bg__reason-label">{r.label}</span>
                <span className="bg__reason-detail">{r.detail}</span>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel title="What makes us cautious">
        {cautious.length === 0 ? (
          <EmptyLine label="No opposing factors">
            No factor is currently contributing negatively to this score.
          </EmptyLine>
        ) : (
          <ul className="bg__reasons">
            {cautious.map((r) => (
              <li key={r.key} className="bg__reason" data-tone="negative">
                <span className="bg__reason-label">{r.label}</span>
                <span className="bg__reason-detail">{r.detail}</span>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel title="What could change the signal">
        <Prose>
          Derived from the factors currently carrying the conclusion. Nothing
          here predicts an event — it names what would have to move.
        </Prose>
        <ul className="bg__reasons">
          {changes.map((line) => (
            <li key={line} className="bg__reason"><span className="bg__reason-detail">{line}</span></li>
          ))}
        </ul>
      </Panel>

      {a.ai?.executiveSummary ? (
        <Panel title="In plain words" subtitle="generated from the validated evidence">
          <Prose>{a.ai.executiveSummary}</Prose>
          <Prose>
            Written by a language model from the numbers above. It explains the
            conclusion; it does not make it — the signal, confidence and risk
            are the engine&apos;s and are attached after generation.
          </Prose>
        </Panel>
      ) : null}

      <AskOmniSignal ticker={ticker} />

      <WhatIfLab ticker={ticker} />

      <StockActions symbol={ticker} />

      <Panel title="Where this came from">
        <Prose>
          {a.macro?.status
            ? `Macro regime: ${a.macro.status}.`
            : 'Macro regime could not be read for this run.'}
          {' '}
          {explainCompleteness(completeness)}
        </Prose>
        {a.rationale ? <Prose>{a.rationale}</Prose> : null}
      </Panel>
    </>
  )
}
