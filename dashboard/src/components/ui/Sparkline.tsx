/**
 * A small inline trend line. Plain SVG, cheap enough for dozens per page.
 *
 * Below two finite observations it draws nothing: one point is not a trend,
 * and a flat line would imply one. Missing observations break the line rather
 * than being bridged, so a gap in the data stays visible as a gap.
 */
export default function Sparkline({
  points, width = 72, height = 22, tone = 'auto', area = true, label,
}: {
  points: Array<number | null>
  width?: number
  height?: number
  /** `auto` colours by first-to-last direction; `neutral` never does. Series
   *  where up is not good (inflation, spreads) should stay neutral. */
  tone?: 'auto' | 'neutral'
  area?: boolean
  /** Accessible summary; omit when the row states the numbers already. */
  label?: string
}) {
  const finite = points.filter((p): p is number => p !== null && Number.isFinite(p))
  if (finite.length < 2) return null
  let min = finite[0]
  let max = finite[0]
  for (const p of finite) { if (p < min) min = p; if (p > max) max = p }
  const span = max - min || 1
  const pad = 2
  const x = (i: number) => (i / Math.max(1, points.length - 1)) * width
  const y = (v: number) => height - pad - ((v - min) / span) * (height - pad * 2)

  const runs: Array<Array<[number, number]>> = []
  let run: Array<[number, number]> = []
  points.forEach((v, i) => {
    if (v === null || !Number.isFinite(v)) {
      if (run.length) runs.push(run)
      run = []
      return
    }
    run.push([x(i), y(v)])
  })
  if (run.length) runs.push(run)
  const path = (r: Array<[number, number]>) =>
    r.map(([px, py], i) => `${i ? 'L' : 'M'}${px.toFixed(1)},${py.toFixed(1)}`).join(' ')

  const up = finite[finite.length - 1] >= finite[0]
  const cls = tone === 'neutral' ? 'spark' : `spark ${up ? 'spark--up' : 'spark--down'}`
  const lastIndex = points.length - 1 - [...points].reverse().findIndex((p) => p !== null && Number.isFinite(p))
  const last = points[lastIndex] as number

  return (
    <svg
      className={cls}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {area && runs.length === 1 && runs[0].length > 1 ? (
        <path
          className="spark__area"
          d={`${path(runs[0])} L${runs[0][runs[0].length - 1][0].toFixed(1)},${height} L${runs[0][0][0].toFixed(1)},${height} Z`}
        />
      ) : null}
      {runs.filter((r) => r.length > 1).map((r) => <path key={`${r[0][0]}`} className="spark__line" d={path(r)} />)}
      <circle className="spark__end" cx={x(lastIndex)} cy={y(last)} r={1.8} />
    </svg>
  )
}
