'use client'

interface VerdictBadgeProps {
  verdict: string
  signalScore: number
  riskAdjusted?: string
  srm: number
}

const CONFIGS: Record<string, { color: string; bg: string; border: string; glow: string }> = {
  'Strong Buy':  { color: '#10b981', bg: 'rgba(16,185,129,0.09)',  border: 'rgba(16,185,129,0.28)', glow: 'rgba(16,185,129,0.14)' },
  'Buy':         { color: '#34d399', bg: 'rgba(52,211,153,0.07)',  border: 'rgba(52,211,153,0.22)', glow: 'rgba(52,211,153,0.10)' },
  'Hold':        { color: '#f59e0b', bg: 'rgba(245,158,11,0.08)',  border: 'rgba(245,158,11,0.24)', glow: 'rgba(245,158,11,0.10)' },
  'Sell':        { color: '#f87171', bg: 'rgba(248,113,113,0.08)', border: 'rgba(248,113,113,0.22)', glow: 'rgba(248,113,113,0.10)' },
  'Strong Sell': { color: '#ef4444', bg: 'rgba(239,68,68,0.10)',   border: 'rgba(239,68,68,0.28)', glow: 'rgba(239,68,68,0.14)' },
}

const MAX = 8

export default function VerdictBadge({ verdict, signalScore, riskAdjusted, srm }: VerdictBadgeProps) {
  const cfg = CONFIGS[verdict] ?? CONFIGS['Hold']
  const fill = ((signalScore + MAX) / (MAX * 2)) * 100
  const srmRisk = srm > 1.3 ? 'Elevated' : srm > 1.1 ? 'Moderate' : 'Normal'
  const srmColor = srm > 1.3 ? '#f59e0b' : srm > 1.1 ? '#fbbf24' : '#38bdf8'

  return (
    <div
      style={{
        background: cfg.bg,
        border: `1px solid ${cfg.border}`,
        boxShadow: `0 0 48px ${cfg.glow}`,
        borderRadius: 8,
        padding: '24px 26px 22px',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
      }}
    >
      {/* Label */}
      <div className="label">OmniSignal Verdict</div>

      {/* Verdict word */}
      <div style={{ lineHeight: 1 }}>
        <div
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 'clamp(2rem, 5vw, 3.2rem)',
            fontWeight: 800,
            color: cfg.color,
            letterSpacing: '-0.02em',
          }}
        >
          {(verdict || "Hold").toUpperCase()}
        </div>
        {riskAdjusted && riskAdjusted !== verdict && (
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.68rem',
              color: cfg.color,
              opacity: 0.65,
              marginTop: 4,
              letterSpacing: '0.04em',
            }}
          >
            Risk-adjusted → {riskAdjusted}
          </div>
        )}
      </div>

      {/* Signal score gauge */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
          <span className="label">Signal Score</span>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.8rem',
              fontWeight: 700,
              color: cfg.color,
            }}
          >
            {signalScore > 0 ? '+' : ''}{signalScore}
          </span>
        </div>
        <div className="gauge-track">
          <div
            className="gauge-fill"
            style={{
              width: `${fill}%`,
              background: `linear-gradient(90deg, transparent 0%, ${cfg.color} 100%)`,
            }}
          />
        </div>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            marginTop: 5,
          }}
        >
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.55rem', color: 'var(--muted)' }}>
            −8 Strong Sell
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.55rem', color: 'var(--muted)' }}>
            +8 Strong Buy
          </span>
        </div>
      </div>

      {/* Divider */}
      <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }} />

      {/* SRM chip */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="label">Systemic Risk Multiplier</span>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.88rem',
            fontWeight: 700,
            color: srmColor,
            background: `rgba(${srm > 1.3 ? '245,158,11' : '56,189,248'},0.08)`,
            border: `1px solid rgba(${srm > 1.3 ? '245,158,11' : '56,189,248'},0.22)`,
            borderRadius: 4,
            padding: '2px 8px',
          }}
        >
          {(srm ?? 0).toFixed(3)} · {srmRisk}
        </span>
      </div>
    </div>
  )
}
