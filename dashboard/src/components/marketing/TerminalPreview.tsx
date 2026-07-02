/* A crafted, static rendering of the terminal — real NVDA output captured
   from the engine in July 2026 (22 daily closes, verdict, factors).
   Pure HTML/SVG: no chart library ships with the landing page. */

const SPARK_PATH =
  'M0,4 L24.8,21.2 L49.5,12.3 L74.3,41.2 L99,33.7 L123.8,34.6 L148.6,51.2 ' +
  'L173.3,41.7 L198.1,41 L222.9,25.5 L247.6,36.3 L272.4,42.2 L297.1,29.3 ' +
  'L321.9,33.6 L346.7,52 L371.4,54.2 L396.2,61.2 L421,68 L445.7,62.8 ' +
  'L470.5,51.9 L495.2,57.2 L520,66.9'

const STATS = [
  { label: 'RSI-14', value: '39.1' },
  { label: 'Sharpe', value: '1.07' },
  { label: 'Volatility', value: '39.9%' },
  { label: 'Street target', value: '+56.2%' },
]

export default function TerminalPreview() {
  return (
    <figure style={{ margin: 0 }}>
      <div
        className="theme-dark"
        style={{
          background: 'var(--bg)',
          border: '1px solid rgba(28, 27, 24, 0.9)',
          borderRadius: 12,
          overflow: 'hidden',
          boxShadow: '0 32px 80px rgba(28, 27, 24, 0.28), 0 4px 16px rgba(28, 27, 24, 0.12)',
          color: 'var(--text)',
        }}
      >
        {/* Window chrome */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '11px 16px',
            borderBottom: '1px solid var(--line)',
          }}
        >
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              style={{ width: 9, height: 9, borderRadius: '50%', background: 'var(--surface-2)' }}
              aria-hidden="true"
            />
          ))}
          <span className="mono" style={{ marginLeft: 10, fontSize: '0.6875rem', color: 'var(--faint)' }}>
            omnisignal — terminal
          </span>
        </div>

        <div style={{ padding: 'clamp(18px, 3vw, 28px)' }}>
          {/* Company band */}
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'baseline',
              gap: '6px 14px',
              marginBottom: 4,
            }}
          >
            <span className="mono" style={{ fontSize: '1rem', fontWeight: 600 }}>
              NVDA
            </span>
            <span style={{ fontSize: '0.875rem', color: 'var(--muted)' }}>NVIDIA Corporation</span>
            <span style={{ fontSize: '0.8125rem', color: 'var(--faint)' }}>Technology · $4.79T</span>
            <span className="badge badge--neg" style={{ marginLeft: 'auto' }}>
              Sell
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 6 }}>
            <span className="num" style={{ fontSize: '1.75rem', fontWeight: 600 }}>
              $193.06
            </span>
            <span className="num" style={{ fontSize: '0.875rem', color: 'var(--neg)' }}>
              −13.3% · 1M
            </span>
          </div>

          <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', marginBottom: 18 }}>
            Raw signal <strong style={{ color: 'var(--text)', fontWeight: 560 }}>Hold</strong> — dampened to{' '}
            <strong style={{ color: 'var(--neg)', fontWeight: 560 }}>Sell</strong> under an elevated macro
            regime <span className="num">(SRM 1.20)</span>
          </p>

          {/* Real 1-month sparkline */}
          <svg
            viewBox="0 0 520 72"
            preserveAspectRatio="none"
            role="img"
            aria-label="NVDA one-month price line, declining from about 223 to 193 dollars"
            style={{ width: '100%', height: 88, display: 'block', marginBottom: 18 }}
          >
            <path d={`${SPARK_PATH} L520,72 L0,72 Z`} fill="var(--neg)" opacity="0.08" />
            <path d={SPARK_PATH} fill="none" stroke="var(--neg)" strokeWidth="1.75" vectorEffect="non-scaling-stroke" />
          </svg>

          {/* Factor readouts */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))',
              gap: 1,
              background: 'var(--line)',
              border: '1px solid var(--line)',
              borderRadius: 'var(--r-md)',
              overflow: 'hidden',
            }}
          >
            {STATS.map((s) => (
              <div key={s.label} style={{ background: 'var(--surface)', padding: '12px 14px' }}>
                <div className="label" style={{ marginBottom: 5 }}>
                  {s.label}
                </div>
                <div className="num" style={{ fontSize: '0.9375rem', fontWeight: 500 }}>
                  {s.value}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <figcaption
        style={{
          textAlign: 'center',
          fontSize: '0.8125rem',
          color: 'var(--faint)',
          marginTop: 16,
        }}
      >
        Actual engine output for NVDA, July 2026 — not an illustration.
      </figcaption>
    </figure>
  )
}
