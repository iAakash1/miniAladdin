import Sparkline from '@/components/ui/Sparkline'

/**
 * Three months of closes for one row, drawn from the quote that row already
 * holds. The batch quote is computed from this same series and now returns
 * it, so a list of sparklines costs nothing beyond the one quote request.
 * Each row used to ask `/api/chart` for its own copy — nine requests queued
 * behind the quote batch on a backend that serves one at a time.
 *
 * `values` undefined means the quote has not landed; an empty or one-point
 * series means it landed without enough history to draw a line.
 */
export default function SymbolSpark({ values, width = 72, height = 22 }: {
  values: readonly number[] | null | undefined
  width?: number
  height?: number
}) {
  const points = values?.filter((v) => Number.isFinite(v)) ?? null
  const state = points === null ? 'loading' : points.length > 1 ? 'ready' : 'empty'
  return (
    <span className="sspark" style={{ width, height }} data-state={state}>
      {points && points.length > 1 ? <Sparkline points={points} width={width} height={height} /> : null}
    </span>
  )
}
