'use client'

/**
 * Create an alert for one security, or change an existing alert's condition.
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
  FILING_FORMS, KIND_LABEL, createAlert, draftProblems, updateAlert,
  type AlertDraft, type AlertKind, type PriceAlert,
} from '@/lib/alerts'

export default function AlertEditor({
  ticker: fixedTicker, onCreated, lastPrice, editing,
}: { ticker?: string; onCreated?: (a: PriceAlert) => void; lastPrice?: number | null; editing?: PriceAlert }) {
  const [ticker, setTicker] = useState(editing?.ticker ?? fixedTicker ?? '')
  const [kind, setKind] = useState<AlertKind>(editing?.kind ?? 'cross_above')
  const [threshold, setThreshold] = useState(
    editing?.threshold != null ? String(editing.threshold) : lastPrice ? String(Math.round(lastPrice * 1.05 * 100) / 100) : '',
  )
  const [high, setHigh] = useState(editing?.threshold_high != null ? String(editing.threshold_high) : '')
  const [direction, setDirection] = useState<'up' | 'down' | 'either'>(editing?.direction ?? 'either')
  const [period, setPeriod] = useState(String(editing?.period_days ?? 21))
  const [forms, setForms] = useState<string[]>(editing ? editing.form_types : ['10-K', '10-Q', '8-K'])
  const [repeat, setRepeat] = useState(editing?.repeat ?? false)
  const [note, setNote] = useState(editing?.note ?? '')
  const [saving, setSaving] = useState(false)
  // Problems are shown once the reader has typed or tried to save, not on an empty form.
  const [touched, setTouched] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null)
  const tickerFixed = Boolean(fixedTicker || editing)

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
      const saved = editing ? await updateAlert(editing, draft) : await createAlert(draft)
      setResult({
        ok: true,
        text: editing
          ? `Updated: ${saved.condition}. It starts again from the next evaluation.`
          : `Saved: ${saved.condition}. Checked on the server's schedule, not in this browser.`,
      })
      onCreated?.(saved)
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
    <form
      className="alert-editor" onChange={() => setTouched(true)}
      onSubmit={(e) => { e.preventDefault(); setTouched(true); if (!problems.length) void save() }}
    >
      <div className="ticket__fields">
        {tickerFixed ? null : (
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

      {touched && problems.length ? <ul className="ticket__local" aria-live="polite">{problems.map((p) => <li key={p}>{p}</li>)}</ul> : null}
      {result ? (
        <p className="alert-editor__result" role="status">
          <Status state={result.ok ? 'live' : 'error'} label={result.ok ? 'SAVED' : 'NOT SAVED'} /> {result.text}
        </p>
      ) : null}
      <div className="ticket__acts">
        <button type="submit" className="sys-btn sys-btn--primary" disabled={saving || (touched && problems.length > 0)}>
          {saving ? 'saving…' : editing ? 'Save changes' : 'Create alert'}
        </button>
      </div>
    </form>
  )
}
