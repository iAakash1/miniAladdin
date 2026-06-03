'use client'

interface TechnicalPanelProps {
  rsi: number
  sharpe: number
  sortino: number
  volatility: number
  momentum: number
  drawdown: number
  sentiment: number
  sentimentLabel: string
  headlineCount?: number

  /* Optional enriched fields */
  peRatio?: number
  forwardPe?: number
  eps?: number
  analystTarget?: number
  analystUpside?: number
  beta?: number
  week52Low?: number
  week52High?: number
  currentPrice?: number
}

function Row({
  label,
  value,
  color,
}: {
  label: string
  value: string
  color?: string
}) {
  return (
    <div className="metric-row">
      <span className="label">{label}</span>
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '0.82rem',
          fontWeight: 500,
          color: color ?? 'var(--text)',
        }}
      >
        {value}
      </span>
    </div>
  )
}

function colorRsi(v: number)   { return v > 70 ? 'var(--red)' : v < 30 ? 'var(--green)' : 'var(--text)' }
function colorRatio(v: number) { return v > 1 ? 'var(--green)' : v < 0 ? 'var(--red)' : 'var(--amber)' }
function colorMom(v: number)   { return v > 0 ? 'var(--green)' : 'var(--red)' }
function colorVol(v: number)   { return v > 0.45 ? 'var(--red)' : v > 0.25 ? 'var(--amber)' : 'var(--green)' }
function colorSent(v: number)  { return v > 0.1 ? 'var(--green)' : v < -0.1 ? 'var(--red)' : 'var(--amber)' }

export default function TechnicalPanel({
  rsi, sharpe, sortino, volatility, momentum, drawdown,
  sentiment, sentimentLabel, headlineCount,
  peRatio, forwardPe, eps, analystTarget, analystUpside,
  beta, week52Low, week52High, currentPrice,
}: TechnicalPanelProps) {

  const hasFundamentals = peRatio != null || analystTarget != null || beta != null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* ── Technical card ── */}
      <div className="card" style={{ padding: '20px 22px' }}>
        <div className="section-heading"><span>Technical Analysis</span></div>

        <Row label="RSI (14)"                  value={rsi.toFixed(1)}                      color={colorRsi(rsi)} />
        <Row label="Sharpe Ratio"              value={sharpe.toFixed(3)}                   color={colorRatio(sharpe)} />
        <Row label="Sortino Ratio"             value={sortino.toFixed(3)}                  color={colorRatio(sortino)} />
        <Row label="21D Momentum"              value={`${(momentum * 100).toFixed(2)}%`}   color={colorMom(momentum)} />
        <Row label="Annualized Volatility"     value={`${(volatility * 100).toFixed(1)}%`} color={colorVol(volatility)} />
        <Row label="Max Drawdown"              value={`${(drawdown * 100).toFixed(2)}%`}   color="var(--red)" />
      </div>

      {/* ── Sentiment card ── */}
      <div className="card" style={{ padding: '20px 22px' }}>
        <div className="section-heading">
          <span>
            News Sentiment
            {headlineCount != null && (
              <span
                style={{
                  marginLeft: 8,
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.6rem',
                  fontWeight: 400,
                  color: 'var(--muted)',
                  textTransform: 'none',
                  letterSpacing: '0.04em',
                }}
              >
                {headlineCount} headlines
              </span>
            )}
          </span>
        </div>

        {/* Score + label */}
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, marginBottom: 14 }}>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '1.9rem',
              fontWeight: 700,
              color: colorSent(sentiment),
              lineHeight: 1,
              letterSpacing: '-0.02em',
            }}
          >
            {sentiment > 0 ? '+' : ''}
            {sentiment.toFixed(3)}
          </span>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.7rem',
              color: colorSent(sentiment),
              background: sentiment > 0.1
                ? 'var(--green-dim)'
                : sentiment < -0.1
                ? 'var(--red-dim)'
                : 'var(--amber-dim)',
              border: `1px solid ${sentiment > 0.1 ? 'var(--green-border)' : sentiment < -0.1 ? 'var(--red-border)' : 'var(--amber-border)'}`,
              borderRadius: 4,
              padding: '2px 8px',
              marginBottom: 3,
              letterSpacing: '0.06em',
            }}
          >
            {sentimentLabel.toUpperCase()}
          </span>
        </div>

        {/* Sentiment bar (center = 0) */}
        <div
          style={{
            position: 'relative',
            height: 5,
            background: 'rgba(255,255,255,0.06)',
            borderRadius: 3,
          }}
        >
          {/* Center mark */}
          <div
            style={{
              position: 'absolute',
              left: '50%',
              top: 0,
              bottom: 0,
              width: 1,
              background: 'rgba(255,255,255,0.18)',
            }}
          />
          {/* Fill */}
          <div
            style={{
              position: 'absolute',
              top: 0, bottom: 0,
              left: sentiment >= 0 ? '50%' : `${50 + sentiment * 50}%`,
              width: `${Math.abs(sentiment) * 50}%`,
              background: colorSent(sentiment),
              borderRadius: 3,
              transition: 'width 0.65s ease',
            }}
          />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 5 }}>
          <span className="label" style={{ fontSize: '0.55rem' }}>−1 Bearish</span>
          <span className="label" style={{ fontSize: '0.55rem' }}>+1 Bullish</span>
        </div>
      </div>

      {/* ── Fundamentals card (optional) ── */}
      {hasFundamentals && (
        <div className="card" style={{ padding: '20px 22px' }}>
          <div className="section-heading"><span>Fundamentals</span></div>
          {peRatio  != null && <Row label="P/E Ratio"           value={peRatio.toFixed(2)}  />}
          {forwardPe != null && <Row label="Forward P/E"        value={forwardPe.toFixed(2)} />}
          {eps       != null && <Row label="EPS"                value={`$${eps.toFixed(2)}`} />}
          {beta      != null && <Row label="Beta"               value={beta.toFixed(2)} color={beta > 1.5 ? 'var(--amber)' : 'var(--text)'} />}
          {analystTarget != null && (
            <Row
              label="Analyst Target"
              value={`$${analystTarget.toFixed(2)}${analystUpside != null ? ` (${analystUpside > 0 ? '+' : ''}${analystUpside.toFixed(1)}%)` : ''}`}
              color={analystUpside && analystUpside > 0 ? 'var(--green)' : 'var(--red)'}
            />
          )}
          {week52Low != null && week52High != null && currentPrice != null && (
            <>
              <div className="metric-row">
                <span className="label">52-Week Range</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem', color: 'var(--muted)' }}>
                  ${week52Low.toFixed(0)} — ${week52High.toFixed(0)}
                </span>
              </div>
              {/* Range bar */}
              <div style={{ padding: '4px 0 2px' }}>
                <div style={{ position: 'relative', height: 3, background: 'rgba(255,255,255,0.07)', borderRadius: 2 }}>
                  <div
                    style={{
                      position: 'absolute',
                      top: 0, bottom: 0,
                      left: 0,
                      width: `${Math.min(100, ((currentPrice - week52Low) / (week52High - week52Low)) * 100)}%`,
                      background: 'var(--accent)',
                      borderRadius: 2,
                    }}
                  />
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
