'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import PriceChart     from '@/components/PriceChart'
import MacroPanel     from '@/components/MacroPanel'
import VerdictBadge   from '@/components/VerdictBadge'
import TechnicalPanel from '@/components/TechnicalPanel'
import type { ResearchResult, MacroData } from '@/types/api'

const QUICK = ['NVDA', 'AAPL', 'TSLA', 'MSFT', 'META', 'AMZN', 'GOOGL', 'SPY']

/* ── OmniSignal logo mark ── */
function Logo() {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden>
      <polygon
        points="11,1 21,6 21,16 11,21 1,16 1,6"
        stroke="#38bdf8"
        strokeWidth="1.2"
        fill="rgba(56,189,248,0.1)"
      />
      <circle cx="11" cy="11" r="3.2" fill="#38bdf8" fillOpacity="0.9" />
      <line x1="11" y1="5"  x2="11" y2="8.2"  stroke="#38bdf8" strokeWidth="1" />
      <line x1="11" y1="13.8" x2="11" y2="17" stroke="#38bdf8" strokeWidth="1" />
    </svg>
  )
}

/* ── Shimmer skeleton block ── */
function Skel({ h }: { h: number }) {
  return <div className="shimmer" style={{ height: h, borderRadius: 8 }} />
}

/* ── Small macro stat in header ── */
function HeaderStat({
  label,
  value,
  color,
}: {
  label: string
  value: string
  color?: string
}) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 5,
        padding: '0 10px',
        borderLeft: '1px solid rgba(255,255,255,0.06)',
      }}
    >
      <span className="label">{label}</span>
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '0.72rem',
          fontWeight: 600,
          color: color ?? 'var(--text)',
        }}
      >
        {value}
      </span>
    </div>
  )
}

export default function Home() {
  const [ticker,   setTicker  ] = useState('')
  const [loading,  setLoading ] = useState(false)
  const [result,   setResult  ] = useState<ResearchResult | null>(null)
  const [error,    setError   ] = useState<string | null>(null)
  const [macro,    setMacro   ] = useState<MacroData | null>(null)
  const [fastMode, setFastMode] = useState(false)
  const resultRef = useRef<HTMLDivElement>(null)
  const inputRef  = useRef<HTMLInputElement>(null)

  /* Load macro on mount */
  useEffect(() => {
    fetch('/api/macro')
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setMacro(d))
      .catch(() => null)
  }, [])

  const runAnalysis = useCallback(async (sym: string) => {
    const t = sym.trim().toUpperCase()
    if (!t) return
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const url = `/api/research/${t}${fastMode ? '?fast=true' : ''}`
      const res = await fetch(url)
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body?.detail || `Server error ${res.status}`)
      }
      const data: ResearchResult = await res.json()
      setResult(data)
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Analysis failed')
    } finally {
      setLoading(false)
    }
  }, [fastMode])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    runAnalysis(ticker)
  }

  const handleChip = (sym: string) => {
    setTicker(sym)
    runAnalysis(sym)
  }

  /* ── Helper: snap price highlight ── */
  const priceColor = (result: ResearchResult) => {
    const pct = result.price_history?.length
      ? (result.price_history.at(-1)!.close - result.price_history[0].close) / result.price_history[0].close
      : 0
    return pct >= 0 ? 'var(--green)' : 'var(--red)'
  }

  return (
    <div style={{ position: 'relative', zIndex: 1, minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>

      {/* ════════════════════════════ HEADER ════════════════════════════ */}
      <header
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 50,
          backdropFilter: 'blur(14px)',
          WebkitBackdropFilter: 'blur(14px)',
          background: 'rgba(6,13,27,0.82)',
          borderBottom: '1px solid rgba(56,189,248,0.08)',
          height: 50,
          display: 'flex',
          alignItems: 'center',
          padding: '0 20px',
          gap: 10,
          overflow: 'hidden',
        }}
      >
        {/* Brand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <Logo />
          <span
            style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 800,
              fontSize: '0.88rem',
              letterSpacing: '0.1em',
              color: 'var(--text)',
              textTransform: 'uppercase',
            }}
          >
            OmniSignal
          </span>
          <span
            style={{
              fontSize: '0.52rem',
              color: 'var(--accent)',
              border: '1px solid rgba(56,189,248,0.3)',
              borderRadius: 3,
              padding: '1px 5px',
              letterSpacing: '0.08em',
              fontFamily: 'var(--font-mono)',
            }}
          >
            v1.0
          </span>
        </div>

        {/* Live dot + macro stats */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 2, marginLeft: 'auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, paddingRight: 10 }}>
            <span className="status-dot blink" />
            <span className="label">Live</span>
          </div>
          {macro ? (
            <>
              <HeaderStat
                label="SRM"
                value={macro.srm.toFixed(3)}
                color={macro.srm > 1.2 ? 'var(--amber)' : 'var(--accent)'}
              />
              <HeaderStat
                label="Yield Spread"
                value={`${(macro.yield_spread ?? 0).toFixed(2)}%`}
                color={(macro.yield_spread ?? 0) < 0 ? 'var(--red)' : 'var(--text)'}
              />
              <HeaderStat
                label="CPI"
                value={`${(macro.cpi ?? 0).toFixed(2)}%`}
                color={(macro.cpi ?? 0) > 4 ? 'var(--amber)' : 'var(--text)'}
              />
              <HeaderStat
                label="Fed Rate"
                value={`${(macro.fed_funds_rate ?? 0).toFixed(2)}%`}
              />
            </>
          ) : (
            <span className="label" style={{ padding: '0 10px' }}>Fetching macro…</span>
          )}
        </div>
      </header>

      {/* ════════════════════════════ HERO ════════════════════════════ */}
      <section
        style={{
          padding: 'clamp(48px, 8vw, 80px) 24px clamp(36px, 6vw, 56px)',
          textAlign: 'center',
          maxWidth: 720,
          margin: '0 auto',
          width: '100%',
        }}
      >
        {/* Tag */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 7,
            padding: '4px 14px',
            border: '1px solid rgba(56,189,248,0.2)',
            borderRadius: 20,
            marginBottom: 22,
            background: 'rgba(56,189,248,0.04)',
          }}
        >
          <span style={{ width: 5, height: 5, borderRadius: '50%', background: 'var(--accent)', display: 'inline-block' }} />
          <span
            style={{
              fontSize: '0.6rem',
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
              color: 'var(--accent)',
              fontFamily: 'var(--font-mono)',
            }}
          >
            Agentic Multi-Factor Risk Engine
          </span>
        </div>

        {/* Word-mark */}
        <h1
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 'clamp(2.8rem, 7vw, 4.8rem)',
            fontWeight: 800,
            letterSpacing: '-0.035em',
            lineHeight: 1,
            marginBottom: 16,
          }}
        >
          <span style={{ color: 'var(--text)' }}>Omni</span>
          <span style={{ color: 'var(--accent)' }}>Signal</span>
        </h1>

        {/* Sub */}
        <p
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.78rem',
            color: 'var(--muted)',
            lineHeight: 1.8,
            marginBottom: 36,
          }}
        >
          FRED macro · Yahoo Finance technicals · RSS news sentiment
          <br />
          Unified into a single risk-adjusted equity verdict.
        </p>

        {/* Search form */}
        <form onSubmit={handleSubmit} style={{ display: 'flex', justifyContent: 'center', gap: 8, marginBottom: 16 }}>
          <input
            ref={inputRef}
            type="text"
            value={ticker}
            onChange={e => setTicker(e.target.value.toUpperCase().replace(/[^A-Z.^]/g, ''))}
            placeholder="TICKER"
            maxLength={8}
            className="ticker-input"
            style={{
              width: 200,
              background: 'rgba(10,22,40,0.95)',
              border: '1px solid var(--border-hi)',
              borderRadius: 6,
              padding: '11px 16px',
              fontSize: '1rem',
              fontFamily: 'var(--font-mono)',
              fontWeight: 700,
              letterSpacing: '0.12em',
              color: 'var(--text)',
              caretColor: 'var(--accent)',
              transition: 'border-color 0.18s, box-shadow 0.18s',
            }}
          />
          <button
            type="submit"
            disabled={loading || !ticker}
            style={{
              background: loading || !ticker ? 'rgba(56,189,248,0.15)' : 'var(--accent)',
              color:      loading || !ticker ? 'var(--accent)'         : '#060d1b',
              border: `1px solid ${loading || !ticker ? 'var(--border-hi)' : 'transparent'}`,
              borderRadius: 6,
              padding: '11px 18px',
              fontSize: '0.72rem',
              fontFamily: 'var(--font-mono)',
              fontWeight: 700,
              letterSpacing: '0.08em',
              cursor: loading || !ticker ? 'not-allowed' : 'pointer',
              transition: 'all 0.16s ease',
              whiteSpace: 'nowrap',
            }}
          >
            {loading ? 'ANALYZING…' : 'ANALYZE →'}
          </button>
        </form>

        {/* Fast-mode toggle */}
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 8, marginBottom: 20 }}>
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              cursor: 'pointer',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.62rem',
              color: 'var(--muted)',
              letterSpacing: '0.06em',
            }}
          >
            <input
              type="checkbox"
              checked={fastMode}
              onChange={e => setFastMode(e.target.checked)}
              style={{ accentColor: 'var(--accent)', width: 12, height: 12 }}
            />
            FAST MODE (skip sentiment · ~3s)
          </label>
        </div>

        {/* Quick-access chips */}
        <div style={{ display: 'flex', gap: 6, justifyContent: 'center', flexWrap: 'wrap' }}>
          {QUICK.map(sym => (
            <button key={sym} className="chip" onClick={() => handleChip(sym)}>
              {sym}
            </button>
          ))}
        </div>
      </section>

      {/* ════════════════════════════ CONTENT ════════════════════════════ */}
      <main
        ref={resultRef}
        style={{
          flex: 1,
          padding: '0 clamp(14px, 3vw, 32px) 60px',
          maxWidth: 1180,
          margin: '0 auto',
          width: '100%',
        }}
      >
        {/* ── Error ── */}
        {error && (
          <div
            className="fade-up"
            style={{
              background: 'rgba(239,68,68,0.07)',
              border: '1px solid rgba(239,68,68,0.22)',
              borderRadius: 8,
              padding: '13px 18px',
              marginBottom: 22,
              display: 'flex',
              alignItems: 'center',
              gap: 10,
            }}
          >
            <span style={{ color: 'var(--red)', fontSize: '0.85rem', flexShrink: 0 }}>✕</span>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '0.78rem',
                color: '#fca5a5',
              }}
            >
              {error}
            </span>
          </div>
        )}

        {/* ── Skeleton ── */}
        {loading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div className="grid-halves">
              <Skel h={160} />
              <Skel h={160} />
            </div>
            <Skel h={240} />
            <div className="grid-asymmetric">
              <Skel h={220} />
              <Skel h={220} />
            </div>
          </div>
        )}

        {/* ── Results ── */}
        {result && !loading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

            {/* Row 1: Verdict + Quick stats */}
            <div className="grid-halves fade-up-1">
              {/* Verdict */}
              <VerdictBadge
                verdict={result.verdict}
                signalScore={result.signal_score}
                riskAdjusted={result.risk_adjusted_signal}
                srm={result.srm ?? result.macro?.srm ?? 1}
              />

              {/* Quick stats card */}
              <div
                className="card"
                style={{ padding: '20px 22px', display: 'flex', flexDirection: 'column', gap: 0 }}
              >
                <div className="section-heading">
                  <span>{result.ticker} · Snapshot</span>
                </div>

                {/* Current price */}
                {result.current_price != null && (
                  <div style={{ marginBottom: 16 }}>
                    <div className="label" style={{ marginBottom: 4 }}>Current Price</div>
                    <div
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: '2rem',
                        fontWeight: 700,
                        letterSpacing: '-0.02em',
                        color: 'var(--text)',
                        lineHeight: 1,
                      }}
                    >
                      ${result.current_price.toFixed(2)}
                    </div>
                  </div>
                )}

                {/* 2×2 metrics grid */}
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: '10px 16px',
                    marginTop: 'auto',
                  }}
                >
                  {[
                    {
                      label: 'RSI (14)',
                      value: result.rsi?.toFixed(1) ?? '—',
                      color: result.rsi > 70 ? 'var(--red)' : result.rsi < 30 ? 'var(--green)' : 'var(--text)',
                    },
                    {
                      label: '21D Momentum',
                      value: `${((result.momentum ?? 0) * 100).toFixed(2)}%`,
                      color: (result.momentum ?? 0) > 0 ? 'var(--green)' : 'var(--red)',
                    },
                    {
                      label: 'Sharpe Ratio',
                      value: result.sharpe_ratio?.toFixed(3) ?? '—',
                      color: (result.sharpe_ratio ?? 0) > 1 ? 'var(--green)' : (result.sharpe_ratio ?? 0) < 0 ? 'var(--red)' : 'var(--amber)',
                    },
                    {
                      label: 'Volatility',
                      value: `${((result.volatility ?? 0) * 100).toFixed(1)}%`,
                      color: (result.volatility ?? 0) > 0.4 ? 'var(--red)' : (result.volatility ?? 0) > 0.25 ? 'var(--amber)' : 'var(--green)',
                    },
                  ].map(({ label, value, color }) => (
                    <div key={label}>
                      <div className="label" style={{ marginBottom: 3 }}>{label}</div>
                      <div
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: '0.95rem',
                          fontWeight: 600,
                          color,
                        }}
                      >
                        {value}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Row 2: Price chart */}
            {(result.price_history?.length ?? 0) > 0 && (
              <div className="fade-up-2">
                <PriceChart
                  data={result.price_history!}
                  ticker={result.ticker}
                />
              </div>
            )}

            {/* Row 3: Macro + Technical/Sentiment */}
            <div className="grid-asymmetric fade-up-3">
              <MacroPanel macro={result.macro} />
              <TechnicalPanel
                rsi={result.rsi}
                sharpe={result.sharpe_ratio}
                sortino={result.sortino_ratio}
                volatility={result.volatility}
                momentum={result.momentum}
                drawdown={result.max_drawdown}
                sentiment={result.sentiment_score}
                sentimentLabel={result.sentiment_label}
                headlineCount={result.sentiment_headline_count}
                peRatio={result.pe_ratio}
                forwardPe={result.forward_pe}
                eps={result.eps}
                analystTarget={result.analyst_target}
                analystUpside={result.analyst_upside}
                beta={result.beta}
                week52Low={result.week52_low}
                week52High={result.week52_high}
                currentPrice={result.current_price}
              />
            </div>

            {/* Timestamp */}
            {result.generated_at && (
              <div className="fade-up-4" style={{ textAlign: 'center', paddingTop: 8 }}>
                <span className="label" style={{ fontSize: '0.58rem' }}>
                  Generated {new Date(result.generated_at).toLocaleString()} · For research &amp; educational purposes only · Not financial advice
                </span>
              </div>
            )}
          </div>
        )}

        {/* ── Empty state ── */}
        {!result && !loading && !error && (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              padding: '40px 0 60px',
              gap: 28,
            }}
          >
            {/* Icon */}
            <div
              style={{
                width: 72,
                height: 72,
                border: '1px solid var(--border-hi)',
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'var(--accent-dim)',
              }}
            >
              <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                <polygon
                  points="16,2 30,9 30,23 16,30 2,23 2,9"
                  stroke="#38bdf8"
                  strokeWidth="1"
                  fill="rgba(56,189,248,0.08)"
                />
                <circle cx="16" cy="16" r="3.5" fill="none" stroke="#38bdf8" strokeWidth="1.2" />
                <line x1="16" y1="9"  x2="16" y2="12.5" stroke="#38bdf8" strokeWidth="1" />
                <line x1="16" y1="19.5" x2="16" y2="23" stroke="#38bdf8" strokeWidth="1" />
                <line x1="9"  y1="16" x2="12.5" y2="16" stroke="#38bdf8" strokeWidth="1" />
                <line x1="19.5" y1="16" x2="23" y2="16" stroke="#38bdf8" strokeWidth="1" />
              </svg>
            </div>

            <p
              className="label"
              style={{ fontSize: '0.68rem', textAlign: 'center' }}
            >
              Enter a ticker above to start the analysis pipeline
            </p>

            {/* Live macro display */}
            {macro && (
              <div
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: 0,
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                  overflow: 'hidden',
                  background: 'var(--bg-card)',
                }}
              >
                {[
                  {
                    label: 'Systemic Risk Multiplier',
                    value: macro.srm.toFixed(3),
                    color: macro.srm > 1.2 ? 'var(--amber)' : 'var(--accent)',
                  },
                  {
                    label: 'Yield Spread (10Y–2Y)',
                    value: `${(macro.yield_spread ?? 0).toFixed(2)}%`,
                    color: (macro.yield_spread ?? 0) < 0 ? 'var(--red)' : 'var(--text)',
                  },
                  {
                    label: 'CPI Inflation',
                    value: `${(macro.cpi ?? 0).toFixed(2)}%`,
                    color: (macro.cpi ?? 0) > 4 ? 'var(--amber)' : 'var(--text)',
                  },
                  {
                    label: 'Fed Funds Rate',
                    value: `${(macro.fed_funds_rate ?? 0).toFixed(2)}%`,
                    color: 'var(--text)',
                  },
                ].map(({ label, value, color }) => (
                  <div
                    key={label}
                    style={{
                      padding: '18px 24px',
                      borderRight: '1px solid var(--border)',
                      minWidth: 140,
                      flex: '1 1 120px',
                    }}
                  >
                    <div className="label" style={{ marginBottom: 6 }}>{label}</div>
                    <div
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: '1.3rem',
                        fontWeight: 700,
                        color,
                        letterSpacing: '-0.01em',
                      }}
                    >
                      {value}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>

      {/* ════════════════════════════ FOOTER ════════════════════════════ */}
      <footer
        style={{
          borderTop: '1px solid rgba(56,189,248,0.06)',
          padding: '14px 24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 8,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Logo />
          <span className="label">OmniSignal · Agentic Risk Engine</span>
        </div>
        <span className="label" style={{ fontSize: '0.58rem' }}>
          Research &amp; education only · Not financial advice ·{' '}
          <span style={{ color: 'var(--accent)' }}>iAakash1</span>
        </span>
      </footer>
    </div>
  )
}
