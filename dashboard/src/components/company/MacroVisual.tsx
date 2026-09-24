import type { Analysis, MacroRate } from '@/lib/types'

/** A value on a fixed scale, with the scale's ends labelled. */
function Gauge({ label, value, display, min, max, lo, hi, note }: {
  label: string
  value: number | null
  display: string
  min: number
  max: number
  lo: string
  hi: string
  note?: string
}) {
  const at = value === null ? null : Math.max(0, Math.min(1, (value - min) / (max - min)))
  return (
    <div className="mv-gauge">
      <div className="mv-gauge__head">
        <span className="mv-gauge__label">{label}</span>
        <span className="mv-gauge__value sys-num">{value === null ? <span className="sys-null">—</span> : display}</span>
      </div>
      <div className="mv-gauge__track" role="img" aria-label={value === null ? `${label} not available` : `${label} ${display}`}>
        {at !== null ? <span className="mv-gauge__fill" style={{ width: `${at * 100}%` }} /> : null}
        {at !== null ? <span className="mv-gauge__mark" style={{ left: `${at * 100}%` }} /> : null}
      </div>
      <div className="mv-gauge__ends"><span>{lo}</span><span>{hi}</span></div>
      {note ? <p className="mv-gauge__note">{note}</p> : null}
    </div>
  )
}

function Rates({ rates }: { rates: MacroRate[] }) {
  const pctRates = rates.filter((r) => r.unit === '%')
  if (!pctRates.length) return null
  const span = Math.max(0.5, ...pctRates.map((r) => Math.abs(r.value)))
  const hasNeg = pctRates.some((r) => r.value < 0)
  return (
    <ul className="mv-rates">
      {pctRates.map((r) => {
        const w = (Math.abs(r.value) / span) * (hasNeg ? 50 : 100)
        const style = hasNeg
          ? (r.value >= 0 ? { left: '50%', width: `${w}%` } : { left: `${50 - w}%`, width: `${w}%` })
          : { left: 0, width: `${w}%` }
        return (
          <li key={r.series_id} title={r.why}>
            <span className="mv-rates__label">{r.label}</span>
            <span className="mv-rates__bar" data-diverging={hasNeg ? '' : undefined} aria-hidden>
              <span data-tone={r.value < 0 ? 'neg' : 'info'} style={style} />
            </span>
            <span className="mv-rates__value sys-num">{r.value.toFixed(2)}%</span>
            <span className="mv-rates__meta">
              {r.change !== null && r.change !== 0 ? <span className={r.change > 0 ? 'sys-pos' : 'sys-neg'}>{r.change > 0 ? '+' : ''}{r.change.toFixed(2)} </span> : null}
              {r.source} · {r.as_of}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

/**
 * What the macro environment does to this signal, drawn: the gate on the
 * momentum sleeve, the stress probability behind it, and the rates a
 * valuation sits on — each with its own observation date.
 */
export default function MacroVisual({ a }: { a: Analysis }) {
  const m = a.macro
  const q = a.quant
  const ctx = a.macroContext
  // Without the context block, the three series the regime read carries.
  const dates = m.observationDates ?? {}
  const basic = (id: string, label: string, value: number | null, date: string | undefined): MacroRate | null =>
    value === null ? null : {
      series_id: id, label, unit: '%', why: label, value, as_of: date ?? 'date not reported',
      prior: null, change: null, source: (m.source ?? 'fred').toUpperCase(),
    }
  const fallbackRates = [
    basic('fed', 'Policy rate', m.fedRate, dates.fed_funds_rate),
    basic('cpi', 'CPI, year over year', m.cpi, dates.inflation_rate),
    basic('spread', 'Curve slope (10y−2y)', m.yieldSpread, dates.yield_spread),
  ].filter((r): r is MacroRate => r !== null)
  const rates = ctx?.rates.length ? ctx.rates : fallbackRates
  const chips: Array<[string, string, 'pos' | 'warn' | 'neg' | 'muted']> = [
    ['Regime', m.status === 'UNAVAILABLE' ? 'unavailable' : m.status.toLowerCase(), m.status === 'UNAVAILABLE' ? 'muted' : m.status === 'STABLE' || m.status === 'NORMAL' ? 'pos' : 'warn'],
    ['Curve', m.inverted === null ? 'unknown' : m.inverted ? 'inverted' : 'not inverted', m.inverted ? 'warn' : m.inverted === null ? 'muted' : 'pos'],
    ['Recession warning', m.recessionWarning === null ? 'unknown' : m.recessionWarning ? 'raised' : 'none', m.recessionWarning ? 'neg' : m.recessionWarning === null ? 'muted' : 'pos'],
  ]

  return (
    <div className="cw-grid cw-grid--2">
      <section className="sys-panel">
        <header className="sys-panel-head">
          <div className="sys-panel-head__title">
            <h2 className="sys-panel-title">Regime and gate</h2>
            <span className="sys-panel-sub">{m.source ? `${m.source.toUpperCase()}${m.stale ? ' · stale' : ''}` : 'what the macro environment does to this signal'}</span>
          </div>
        </header>
        <div className="sys-panel-body mv">
          <div className="mv-chips">
            {chips.map(([k, v, tone]) => (
              <span key={k} className="mv-chip"><span className="dot" data-tone={tone} aria-hidden /><span className="mv-chip__k">{k}</span>{v}</span>
            ))}
          </div>
          <Gauge
            label="Momentum gate"
            value={q ? q.macroGate : null}
            display={q ? `×${q.macroGate.toFixed(2)}` : '—'}
            min={0}
            max={1}
            lo="×0 suppressed"
            hi="×1 unsuppressed"
            note="Scales the momentum sleeve only — value, quality and news are never macro-suppressed."
          />
          <Gauge
            label="Stress probability"
            value={q?.stressProbability ?? null}
            display={q?.stressProbability !== null && q?.stressProbability !== undefined ? `${(q.stressProbability * 100).toFixed(1)}%` : '—'}
            min={0}
            max={1}
            lo="0%"
            hi="100%"
          />
          <p className="cw-note">
            Risk multiplier <span className="sys-num">{m.srm === null ? '—' : m.srm.toFixed(2)}</span>.
            {a.verdict !== a.riskAdjusted
              ? ` For this run the gate moved the signal from ${a.verdict} to ${a.riskAdjusted}.`
              : ' For this run the gate did not change the signal.'}
          </p>
        </div>
      </section>
      <section className="sys-panel">
        <header className="sys-panel-head">
          <div className="sys-panel-head__title">
            <h2 className="sys-panel-title">Rates</h2>
            <span className="sys-panel-sub">each series carries its own observation date</span>
          </div>
        </header>
        <div className="sys-panel-body">
          {rates.length ? <Rates rates={rates} /> : <p className="cw-muted">No rate series were returned with this run.</p>}
          {ctx?.stress.length ? (
            <>
              <h3 className="cw-sub">What gates the verdict</h3>
              <ul className="mv-stress">
                {ctx.stress.map((s) => (
                  <li key={s.key}>
                    <span className="mv-stress__label">{s.label}</span>
                    <span className="sys-num">{s.value.toFixed(3)}</span>
                    <span className="mv-stress__note">{s.note} · {s.source}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {ctx?.note ? <p className="cw-note">{ctx.note}</p> : null}
        </div>
      </section>
    </div>
  )
}
