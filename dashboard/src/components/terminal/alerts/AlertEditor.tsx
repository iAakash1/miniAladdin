'use client'

/**
 * Create an alert for one security.
 *
 * Only conditions the evaluator can test from data it actually has: price
 * crossings, a range exit, a move over a day or a number of trading sessions,
 * and a new SEC filing. The server checks the symbol against real data when
 * the alert is created and takes the current price as the baseline, so a
 * crossing alert waits for an actual crossing.
 */

import { useState } from 'react'

import { Status } from '@/components/system'
import {
  FILING_FORMS, KIND_LABEL, createAlert, draftProblems,
  type AlertDraft, type AlertKind, type PriceAlert,
} from '@/lib/alerts'

export default function AlertEditor({
  ticker: fixedTicker, onCreated, lastPrice,
}: { ticker?: string; onCreated?: (a: PriceAlert) => void; lastPrice?: number | null }) {
  const [ticker, setTicker] = useState(fixedTicker ?? '')
  const [kind, setKind] = useState<AlertKind>('cross_above')
  const [threshold, setThreshold] = useState(lastPrice ? String(Math.round(lastPrice * 1.05 * 100) / 100) : '')
  const [high, setHigh] = useState('')
  const [direction, setDirection] = useState<'up' | 'down' | 'either'>('either')
  const [period, setPeriod] = useState('21')
  const [forms, setForms] = useState<string[]>(['10-K', '10-Q', '8-K'])
  const [repeat, setRepeat] = useState(false)
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null)

  const draft: AlertDraft = {
    ticker: ticker.trim().toUpperCase(), kind, repeat, note: note.trim() || null,
    threshold: kind === 'new_filing' ? null : threshold === '' ? null : Number(threshold),
    threshold_high: kind === 'range_exit' && high !== '' ? Number(high) : null,
    direction: kind === 'day_move' || kind === 'period_move' ? direction : null,
    period_days: kind === 'period_move' ? Number(period) : null,
    form_types: kind === 'new_filing' ? forms : [],
  }
  const problems = draftProblems(draft)

  const save = async () => {
    setSaving(true); setResult(null)
    try {
      const created = await createAlert(draft)
      setResult({ ok: true, text: `Saved: ${created.condition}. Checked on the server's schedule, not in this browser.` })
      onCreated?.(created)
    } catch (e) {
      setResult({ ok: false, text: e instanceof Error ? e.message : 'The alert was not saved.' })
    } finally {
      setSaving(false)
    }
  }

  const priceField = (label: string, value: string, set: (v: string) => void, id: string) => (
    <label className="ticket__field" htmlFor={id}>
      <span className="k">{label}</span>
      <input id={id} className="sys-input" type="number" min="0" step="any" inputMode="decimal" value={value} onChange={(e) => set(e.target.value)} />
    </label>
  )

  return (
    <form className="alert-editor" onSubmit={(e) => { e.preventDefault(); if (!problems.length) void save() }}>
      <div className="ticket__fields">
        {fixedTicker ? null : (
          <label className="ticket__field">
            <span className="k">Ticker</span>
            <input className="sys-input" value={ticker} onChange={(e) => setTicker(e.target.value)} autoComplete="off" placeholder="AAPL" />
          </label>
        )}
        <label className="ticket__field">
          <span className="k">Condition</span>
          <select className="sys-input" value={kind} onChange={(e) => setKind(e.target.value as AlertKind)}>
            {(Object.keys(KIND_LABEL) as AlertKind[]).map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
          </select>
        </label>

        {kind === 'cross_above' || kind === 'cross_below' ? priceField('Price', threshold, setThreshold, 'alert-price') : null}
        {kind === 'range_exit' ? (
          <>
            {priceField('Low', threshold, setThreshold, 'alert-low')}
            {priceField('High', high, setHigh, 'alert-high')}
          </>
        ) : null}
        {kind === 'day_move' || kind === 'period_move' ? (
          <>
            <label className="ticket__field">
              <span className="k">Move (%)</span>
              <input className="sys-input" type="number" min="0" max="100" step="any" value={threshold} onChange={(e) => setThreshold(e.target.value)} />
            </label>
            <label className="ticket__field">
              <span className="k">Direction</span>
              <select className="sys-input" value={direction} onChange={(e) => setDirection(e.target.value as 'up' | 'down' | 'either')}>
                <option value="either">Either way</option>
                <option value="up">Up</option>
                <option value="down">Down</option>
              </select>
            </label>
          </>
        ) : null}
        {kind === 'period_move' ? (
          <label className="ticket__field">
            <span className="k">Trading days</span>
            <input className="sys-input" type="number" min="2" max="260" step="1" value={period} onChange={(e) => setPeriod(e.target.value)} />
          </label>
        ) : null}
        {kind === 'new_filing' ? (
          <fieldset className="ticket__field ticket__field--wide alert-forms">
            <legend className="k">Form types (none = any)</legend>
            {FILING_FORMS.map((f) => (
              <label key={f} className="alert-forms__opt">
                <input type="checkbox" checked={forms.includes(f)} onChange={(e) => setForms(e.target.checked ? [...forms, f] : forms.filter((x) => x !== f))} />
                {f}
              </label>
            ))}
          </fieldset>
        ) : null}

        <label className="ticket__field ticket__field--wide alert-repeat">
          <input type="checkbox" checked={repeat} onChange={(e) => setRepeat(e.target.checked)} />
          <span>Repeat — notify again each time the condition is met anew, instead of once</span>
        </label>
        <label className="ticket__field ticket__field--wide">
          <span className="k">Note <span className="opt">optional</span></span>
          <input className="sys-input" value={note} maxLength={280} onChange={(e) => setNote(e.target.value)} />
        </label>
      </div>

      {problems.length ? <ul className="ticket__local" aria-live="polite">{problems.map((p) => <li key={p}>{p}</li>)}</ul> : null}
      {result ? (
        <p className="alert-editor__result" role="status">
          <Status state={result.ok ? 'live' : 'error'} label={result.ok ? 'SAVED' : 'NOT SAVED'} /> {result.text}
        </p>
      ) : null}
      <div className="ticket__acts">
        <button type="submit" className="sys-btn sys-btn--primary" disabled={saving || problems.length > 0}>{saving ? 'saving…' : 'Create alert'}</button>
      </div>
    </form>
  )
}
