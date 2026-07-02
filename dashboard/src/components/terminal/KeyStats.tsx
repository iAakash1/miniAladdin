'use client'

import { fmtNum, fmtPct } from '@/lib/format'
import type { Analysis } from '@/lib/types'

type Tone = 'pos' | 'neg' | 'warn' | 'neutral'

const TONE_COLOR: Record<Tone, string> = {
  pos: 'var(--pos)',
  neg: 'var(--neg)',
  warn: 'var(--warn)',
  neutral: 'var(--text)',
}

function Row({ label, value, tone = 'neutral', note }: { label: string; value: string; tone?: Tone; note?: string }) {
  return (
    <div className="metric-row">
      <dt>
        {label}
        {note && <span style={{ display: 'block', fontSize: '0.6875rem', color: 'var(--faint)', marginTop: 1 }}>{note}</span>}
      </dt>
      <dd style={{ color: TONE_COLOR[tone] }}>{value}</dd>
    </div>
  )
}

export default function KeyStats({ analysis: a }: { analysis: Analysis }) {
  return (
    <section aria-label="Risk and momentum metrics" className="panel" style={{ padding: '20px 22px' }}>
      <h3 className="h-panel" style={{ marginBottom: 10 }}>
        Risk &amp; momentum
      </h3>
      <dl style={{ margin: 0 }}>
        <Row
          label="RSI-14"
          value={fmtNum(a.rsi, 1)}
          tone={a.rsi > 70 ? 'neg' : a.rsi < 30 ? 'pos' : 'neutral'}
          note={a.rsi > 70 ? 'overbought' : a.rsi < 30 ? 'oversold' : undefined}
        />
        <Row label="21-day return" value={fmtPct(a.return21d)} tone={a.return21d >= 0 ? 'pos' : 'neg'} />
        <Row label="5-day return" value={fmtPct(a.return5d)} tone={a.return5d >= 0 ? 'pos' : 'neg'} />
        <Row
          label="Sharpe ratio"
          value={fmtNum(a.sharpe, 2)}
          tone={a.sharpe > 1 ? 'pos' : a.sharpe < 0 ? 'neg' : 'warn'}
        />
        <Row
          label="Sortino ratio"
          value={fmtNum(a.sortino, 2)}
          tone={a.sortino > 1 ? 'pos' : a.sortino < 0 ? 'neg' : 'neutral'}
        />
        <Row
          label="Volatility, annualized"
          value={fmtPct(a.volatility, 1, false)}
          tone={a.volatility > 0.45 ? 'neg' : a.volatility > 0.25 ? 'warn' : 'pos'}
        />
        <Row label="Max drawdown" value={fmtPct(a.maxDrawdown)} tone="neg" />
        {a.macdCrossover && (
          <Row
            label="MACD crossover"
            value={a.macdCrossover}
            tone={/bull/i.test(a.macdCrossover) ? 'pos' : /bear/i.test(a.macdCrossover) ? 'neg' : 'neutral'}
          />
        )}
      </dl>
    </section>
  )
}
