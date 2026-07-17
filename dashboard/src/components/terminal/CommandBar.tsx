'use client'

import { useId, useState } from 'react'

const QUICK_TICKERS = ['NVDA', 'AAPL', 'TSLA', 'MSFT', 'META', 'AMZN', 'GOOGL', 'SPY']

interface CommandBarProps {
  loading: boolean
  fast: boolean
  onFastChange: (fast: boolean) => void
  onAnalyze: (ticker: string) => void
}

export default function CommandBar({ loading, fast, onFastChange, onAnalyze }: CommandBarProps) {
  const [value, setValue] = useState('')
  const inputId = useId()

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (value.trim()) onAnalyze(value.trim())
  }

  return (
    <div>
      <form
        onSubmit={submit}
        role="search"
        aria-label="Analyze a ticker"
        style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}
      >
        <div style={{ position: 'relative', flex: '1 1 220px', maxWidth: 320 }}>
          <label htmlFor={inputId} className="visually-hidden">
            Ticker symbol
          </label>
          <input
            id={inputId}
            className="input mono"
            type="text"
            inputMode="text"
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            maxLength={8}
            placeholder="Ticker — e.g. NVDA"
            value={value}
            onChange={(e) => setValue(e.target.value.toUpperCase().replace(/[^A-Z.^-]/g, ''))}
            style={{ fontSize: '0.9375rem', fontWeight: 500, letterSpacing: '0.06em' }}
          />
        </div>
        <button
          type="submit"
          className="btn btn--primary"
          disabled={loading || !value.trim()}
          style={{ minWidth: 110 }}
        >
          {loading ? 'Analyzing…' : 'Analyze'}
        </button>
      </form>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 14,
          marginTop: 14,
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }} aria-label="Quick tickers">
          {QUICK_TICKERS.map((t) => (
            <button
              key={t}
              type="button"
              className="btn btn--ghost btn--sm mono"
              disabled={loading}
              onClick={() => {
                setValue(t)
                onAnalyze(t)
              }}
              style={{
                height: 28,
                padding: '0 10px',
                fontSize: '0.75rem',
                fontWeight: 500,
                border: '1px solid var(--line)',
              }}
            >
              {t}
            </button>
          ))}
        </div>

        <label
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            marginLeft: 'auto',
            fontSize: '0.8125rem',
            color: 'var(--muted)',
            cursor: 'pointer',
            userSelect: 'none',
          }}
        >
          <input
            type="checkbox"
            checked={fast}
            onChange={(e) => onFastChange(e.target.checked)}
            style={{ accentColor: 'var(--accent)', width: 14, height: 14 }}
          />
          Quick scan — skips news sentiment, ~3s
        </label>
      </div>
    </div>
  )
}
