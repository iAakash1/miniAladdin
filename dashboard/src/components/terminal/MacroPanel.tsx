'use client'

import { fmtNum, fmtPctRaw } from '@/lib/format'
import type { Macro } from '@/lib/types'

export default function MacroPanel({ macro }: { macro: Macro }) {
  const elevated = macro.srm > 1.2

  return (
    <section aria-label="Macro conditions" className="panel" style={{ padding: '20px 22px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <h3 className="h-panel">Macro regime</h3>
        <span className={`badge ${elevated || macro.recessionWarning ? 'badge--warn' : 'badge--pos'}`}>
          {macro.recessionWarning ? 'Recession warning' : macro.status.toLowerCase()}
        </span>
      </div>

      <dl style={{ margin: 0 }}>
        <div className="metric-row">
          <dt>
            Systemic risk multiplier
            <span style={{ display: 'block', fontSize: '0.6875rem', color: 'var(--faint)', marginTop: 1 }}>
              dampens bullish verdicts above ~1.2
            </span>
          </dt>
          <dd style={{ color: elevated ? 'var(--warn)' : undefined, fontWeight: 600 }}>
            {fmtNum(macro.srm, 2)}
          </dd>
        </div>
        <div className="metric-row">
          <dt>10Y–2Y Treasury spread</dt>
          <dd style={{ color: macro.inverted ? 'var(--neg)' : undefined }}>
            {fmtNum(macro.yieldSpread, 2)}%{macro.inverted ? ' · inverted' : ''}
          </dd>
        </div>
        <div className="metric-row">
          <dt>CPI inflation</dt>
          <dd style={{ color: macro.cpi > 4 ? 'var(--warn)' : undefined }}>{fmtPctRaw(macro.cpi)}</dd>
        </div>
        <div className="metric-row">
          <dt>Fed funds rate</dt>
          <dd>{fmtPctRaw(macro.fedRate)}</dd>
        </div>
      </dl>

      <p style={{ fontSize: '0.75rem', color: 'var(--faint)', marginTop: 12 }}>
        Series from FRED, St. Louis Fed.
      </p>
    </section>
  )
}
