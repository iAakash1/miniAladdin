'use client'

/**
 * Ask OmniSignal — questions about this analysis, answered from its evidence.
 *
 * Deliberately not a free-text chat box. The suggested questions are the ones
 * answerable from a single run, which is the test for whether a question
 * belongs here at all; a box that invites anything invites questions this
 * product cannot ground, and an ungrounded answer is the thing the whole
 * architecture exists to avoid. Free text is still accepted, because a reader
 * will type something, and it is answered under the same constraints.
 *
 * The signal, risk and confidence shown beside an answer come from the
 * scorecard, attached after generation. If the model says something else, the
 * numbers are still the engine's.
 */

import { useEffect, useState } from 'react'

import { EmptyLine, Panel, Prose, StateBlock } from '@/components/system'

interface Answer {
  answer: string
  source: string
  redirected: boolean
  evidence_ids: string[]
  model_signal: string | null
  confidence: number | null
  risk_score: number | null
}

export default function AskOmniSignal({ ticker }: { ticker: string }) {
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<Answer | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let live = true
    void (async () => {
      try {
        const res = await fetch('/api/ask/suggestions')
        if (!res.ok) return
        const body = (await res.json()) as { suggestions: string[] }
        if (live) setSuggestions(body.suggestions ?? [])
      } catch {
        /* Suggestions are a convenience; their absence is not worth reporting. */
      }
    })()
    return () => { live = false }
  }, [])

  async function send(text: string) {
    const clean = text.trim()
    if (!clean) return
    setBusy(true)
    setError(null)
    setAnswer(null)
    setQuestion(clean)
    try {
      const res = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker, question: clean }),
      })
      if (!res.ok) {
        setError(`OmniSignal could not answer that (${res.status}).`)
      } else {
        setAnswer((await res.json()) as Answer)
      }
    } catch {
      setError('OmniSignal could not be reached.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel title="Ask OmniSignal" subtitle="answered from this analysis only">
      <Prose>
        These answers come from the evidence gathered for {ticker} — not from
        the web, and not from anything this run did not measure. OmniSignal
        explains its analysis; it does not give personal financial advice.
      </Prose>

      {suggestions.length ? (
        <div className="ask__chips">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              className="ask__chip"
              disabled={busy}
              onClick={() => void send(s)}
            >
              {s}
            </button>
          ))}
        </div>
      ) : null}

      <form
        className="bg__search"
        onSubmit={(e) => { e.preventDefault(); void send(question) }}
      >
        <label htmlFor={`ask-${ticker}`} className="visually-hidden">
          Ask a question about {ticker}
        </label>
        <input
          id={`ask-${ticker}`}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about this analysis…"
          maxLength={400}
        />
        <button type="submit" disabled={busy}>{busy ? 'Thinking…' : 'Ask'}</button>
      </form>

      {busy ? <StateBlock state="waking" title="Reading the evidence" detail="one analysis run" /> : null}
      {error ? <StateBlock state="unavailable" title="No answer" detail={error} /> : null}

      {answer ? (
        <div className="ask__answer">
          <Prose>{answer.answer}</Prose>
          <p className="ask__meta">
            {answer.redirected ? 'Redirected — this product produces research, not advice. ' : ''}
            {answer.source === 'model' ? 'Written by a model from the evidence below. '
              : 'Composed from the model’s own figures, with no language model involved. '}
            {answer.evidence_ids.length
              ? `Evidence: ${answer.evidence_ids.join(', ')}.`
              : ''}
          </p>
          <p className="ask__meta">
            Signal {answer.model_signal ?? '—'} · Risk {answer.risk_score ?? '—'} ·
            {' '}Confidence {answer.confidence ?? '—'}/100 — the engine&apos;s, not the
            answer&apos;s.
          </p>
        </div>
      ) : null}

      {!busy && !answer && !error ? (
        <EmptyLine label="Ask">Pick a question above, or type your own.</EmptyLine>
      ) : null}
    </Panel>
  )
}
