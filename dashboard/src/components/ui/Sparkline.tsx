interface SparklineProps {
  points: number[]
  direction?: 'up' | 'down' | 'flat'
  width?: number
  height?: number
}

/**
 * Minimal inline trend line shared by dashboard cards and the hero. Plain
 * SVG (no chart library) so it's cheap enough to render dozens per page —
 * the dashboard shows one per macro card plus the hero's own. The draw-in
 * animation on hover (see .sparkline-line in globals.css) is disabled
 * globally under prefers-reduced-motion.
 */
export default function Sparkline({ points, direction = 'flat', width = 56, height = 18 }: SparklineProps) {
  if (points.length < 2) return null
  const min = Math.min(...points)
  const max = Math.max(...points)
  const span = max - min || 1
  const pad = 2
  const coords = points
    .map((value, index) => {
      const x = (index / (points.length - 1)) * width
      const y = height - pad - ((value - min) / span) * (height - pad * 2)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  const color = direction === 'up' ? 'var(--pos)' : direction === 'down' ? 'var(--neg)' : 'var(--faint)'

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      <polyline className="sparkline-line" points={coords} fill="none" stroke={color} strokeWidth="1.25" />
    </svg>
  )
}
