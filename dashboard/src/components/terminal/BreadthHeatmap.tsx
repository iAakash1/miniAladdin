'use client'

import Tooltip from '@/components/ui/Tooltip'
import { type Breadth, heatIntensity, type SectorRow } from '@/lib/dashboardInsights'

function SectorTile({ sector, isLeader, isLaggard }: { sector: SectorRow; isLeader: boolean; isLaggard: boolean }) {
  const value = sector.strength_21d
  const positive = (value ?? 0) >= 0
  const intensity = heatIntensity(value)
  const background = value === null
    ? 'var(--surface-2)'
    : `color-mix(in srgb, ${positive ? 'var(--pos)' : 'var(--neg)'} ${intensity}%, var(--surface))`
  const changeText = value !== null ? `${value > 0 ? '+' : ''}${value}%` : '—'
  const momentumText = sector.momentum_63d !== null
    ? `${sector.momentum_63d > 0 ? '+' : ''}${sector.momentum_63d}%` : '—'

  return (
    <div
      className="sector-tile"
      style={{ background }}
      tabIndex={0}
      role="group"
      aria-label={`${sector.name}: ${changeText} over 21 days, verdict ${sector.verdict}`}
      title={`${sector.name} (${sector.symbol}) · 21d ${changeText} · 63d ${momentumText} · vol ${sector.volatility}% · ${sector.verdict}`}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{ fontSize: '0.6875rem', fontWeight: 600 }}>{sector.symbol}</span>
        {(isLeader || isLaggard) && (
          <span className="label" style={{ fontSize: '0.625rem' }}>{isLeader ? 'Leader' : 'Laggard'}</span>
        )}
      </div>
      <span className="num" style={{ fontSize: '0.875rem', fontWeight: 650, color: positive ? 'var(--pos)' : 'var(--neg)' }}>
        {changeText}
      </span>
      <span style={{ fontSize: '0.625rem', color: 'var(--muted)' }}>{sector.name}</span>
    </div>
  )
}

/**
 * Market breadth as an actual visual — an 11-tile sector heatmap (color =
 * 21-day strength) instead of the old plain data table, plus index quotes
 * and the leadership/laggard read. Replaces the previous BreadthSection +
 * SectorsSection pair: the two communicated almost the same thing, so
 * they're merged into one section per the redesign brief.
 */
export default function BreadthHeatmap({ breadth, sectors }: { breadth: Breadth; sectors: SectorRow[] }) {
  return (
    <section aria-labelledby="breadth-h" className="card dash-breadth">
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10, marginBottom: 14 }}>
        <span id="breadth-h" className="h-panel" style={{ fontSize: '0.9375rem', display: 'inline-flex', alignItems: 'center', gap: 2 }}>
          Market breadth
          <Tooltip label="Why breadth matters">{breadth.explain}</Tooltip>
        </span>
        {breadth.breadth_score !== null && (
          <span className="num" style={{ fontSize: '0.8125rem', color: 'var(--muted)' }}>
            <strong style={{ fontSize: '1.125rem', color: 'var(--text)' }}>{breadth.breadth_score}</strong>
            <span style={{ fontSize: '0.6875rem' }}> /100 above 50-day</span>
          </span>
        )}
      </div>

      {breadth.indexes.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'clamp(14px, 3vw, 32px)', marginBottom: 18 }}>
          {breadth.indexes.map((index) => (
            <div key={index.symbol}>
              <div className="label" style={{ fontSize: '0.625rem', marginBottom: 3 }}>{index.symbol}</div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                <span className="num" style={{ fontSize: '0.9375rem', fontWeight: 600 }}>{index.price}</span>
                {index.change_1d !== null && (
                  <span className="num" style={{ fontSize: '0.6875rem', color: index.change_1d >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                    {index.change_1d >= 0 ? '+' : ''}{index.change_1d}%
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {sectors.length > 0 && (
        <div className="sector-heatmap" role="list" aria-label="Sector performance, 21-day strength">
          {sectors.map((sector) => (
            <SectorTile
              key={sector.symbol}
              sector={sector}
              isLeader={breadth.leadership === sector.name}
              isLaggard={breadth.laggard === sector.name}
            />
          ))}
        </div>
      )}

      {breadth.leadership && (
        <p style={{ fontSize: '0.6875rem', color: 'var(--faint)', marginTop: 14 }}>
          Leading: {breadth.leadership} · Lagging: {breadth.laggard}
        </p>
      )}
    </section>
  )
}
