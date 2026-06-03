'use client'

interface MacroPanelProps {
  macro: {
    srm: number
    yield_spread: number
    cpi: number
    fed_funds_rate: number
    macro_env?: string
  }
}

interface RowProps {
  label: string
  value: number
  unit: string
  warn?: boolean
  inverse?: boolean   // lower = worse
}

function MetricRow({ label, value, unit, warn, inverse }: RowProps) {
  const bad    = warn ?? false
  const color  = bad ? 'var(--amber)' : 'var(--text)'

  return (
    <div className="metric-row">
      <span className="label">{label}</span>
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '0.84rem',
          fontWeight: 500,
          color,
        }}
      >
        {value >= 0 && !inverse && unit === '%' ? '' : ''}
        {(isNaN(value) ? "—" : value.toFixed(2))}
        {unit}
      </span>
    </div>
  )
}

export default function MacroPanel({ macro }: MacroPanelProps) {
  const srmBad    = macro.srm > 1.2
  const yieldBad  = (macro.yield_spread ?? 0) < 0
  const cpiBad    = (macro.cpi ?? 0) > 4
  const ffBad     = (macro.fed_funds_rate ?? 0) > 5

  const envLabel =
    macro.srm < 0.9 ? 'LOW RISK'
    : macro.srm < 1.2 ? 'MODERATE RISK'
    : 'ELEVATED RISK'

  const envColor =
    macro.srm < 0.9 ? 'var(--green)'
    : macro.srm < 1.2 ? 'var(--accent)'
    : 'var(--amber)'

  return (
    <div
      className="card"
      style={{ padding: '20px 22px', height: '100%' }}
    >
      <div className="section-heading">
        <span>Macro Environment</span>
      </div>

      {/* SRM hero number */}
      <div
        style={{
          background: 'var(--accent-dim)',
          border: '1px solid var(--border-hi)',
          borderRadius: 6,
          padding: '14px 16px',
          marginBottom: 16,
        }}
      >
        <div className="label" style={{ marginBottom: 6 }}>
          Systemic Risk Multiplier
        </div>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '2rem',
            fontWeight: 700,
            color: srmBad ? 'var(--amber)' : 'var(--accent)',
            letterSpacing: '-0.02em',
            lineHeight: 1,
          }}
        >
          {(macro.srm ?? 0).toFixed(3)}
        </div>
        <div
          style={{
            marginTop: 8,
            display: 'inline-flex',
            alignItems: 'center',
            gap: 5,
          }}
        >
          <span
            style={{
              display: 'inline-block',
              width: 5,
              height: 5,
              borderRadius: '50%',
              background: envColor,
              flexShrink: 0,
            }}
          />
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.62rem',
              letterSpacing: '0.1em',
              color: envColor,
            }}
          >
            {envLabel}
          </span>
          <span className="label" style={{ marginLeft: 4 }}>
            · {'>'} 1.3 dampens bullish signals
          </span>
        </div>
      </div>

      <MetricRow
        label="Yield Spread (10Y–2Y)"
        value={macro.yield_spread ?? 0}
        unit="%"
        warn={yieldBad}
      />
      <MetricRow
        label="CPI Inflation (YoY)"
        value={macro.cpi ?? 0}
        unit="%"
        warn={cpiBad}
      />
      <MetricRow
        label="Fed Funds Rate"
        value={macro.fed_funds_rate ?? 0}
        unit="%"
        warn={ffBad}
      />
    </div>
  )
}
