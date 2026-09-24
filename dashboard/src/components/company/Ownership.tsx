import type { OwnershipBlock } from '@/lib/types'

function pct(fraction: number | null, digits = 1): string | null {
  return fraction === null || !Number.isFinite(fraction) ? null : `${(fraction * 100).toFixed(digits)}%`
}

function shares(v: number | null): string | null {
  if (v === null || !Number.isFinite(v)) return null
  return v.toLocaleString('en-US', { notation: 'compact', maximumFractionDigits: 2 })
}

function Share({ label, fraction, digits = 1, tone }: {
  label: string
  fraction: number | null
  digits?: number
  tone: 'accent' | 'warn' | 'neg'
}) {
  const text = pct(fraction, digits)
  return (
    <div className="own2-row">
      <span className="own2-row__k">{label}</span>
      <span className="own2-row__bar" aria-hidden>
        {text ? <span data-tone={tone} style={{ width: `${Math.min(100, Math.max(0, (fraction as number) * 100))}%` }} /> : null}
      </span>
      <span className="own2-row__v sys-num">{text ?? <span className="sys-null">—</span>}</span>
    </div>
  )
}

/**
 * Who holds the shares and how many are sold short. Context for a position,
 * never a scoring input. Short interest carries its settlement date because
 * exchanges publish it twice a month — it lags the price by up to two weeks.
 */
export default function Ownership({ ownership: o }: { ownership: OwnershipBlock }) {
  const facts: Array<[string, string | null]> = [
    ['Shares outstanding', shares(o.shares_outstanding)],
    ['Free float', shares(o.float_shares)],
    ['Shares short', shares(o.shares_short)],
    ['Days to cover', o.short_ratio !== null && Number.isFinite(o.short_ratio) ? o.short_ratio.toFixed(2) : null],
  ]
  return (
    <section className="sys-panel">
      <header className="sys-panel-head">
        <div className="sys-panel-head__title">
          <h2 className="sys-panel-title">Ownership and short interest</h2>
          <span className="sys-panel-sub">{o.source} · context, not a scoring input</span>
        </div>
      </header>
      <div className="sys-panel-body own2">
        <div className="own2-bars">
          <Share label="Institutions" fraction={o.held_percent_institutions} tone="accent" />
          <Share label="Insiders" fraction={o.held_percent_insiders} digits={2} tone="warn" />
          <Share label="Short, % of float" fraction={o.short_percent_of_float} digits={2} tone="neg" />
        </div>
        <dl className="cw-kv cw-kv--tight">
          {facts.map(([k, v]) => (
            <div key={k}><dt>{k}</dt><dd className="sys-num">{v ?? <span className="sys-null">—</span>}</dd></div>
          ))}
        </dl>
      </div>
      {o.short_interest_date ? (
        <footer className="sys-panel-foot">
          <span>Short interest settled {o.short_interest_date}; published twice monthly, so it lags the price.</span>
        </footer>
      ) : null}
    </section>
  )
}
