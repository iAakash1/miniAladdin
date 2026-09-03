/**
 * Windowing rules for time-series plots.
 *
 * A window is a pair of indices into a series. Indices are not dates, so a
 * window is only meaningful against the exact series it was drawn on. The
 * failure this module exists to prevent is quiet: a reader selects March, the
 * underlying series reloads with a different length, and the chart keeps
 * showing indices 40..60 — now some other two months — under the axis labels
 * of a range the reader never chose.
 *
 * The rule is therefore to discard rather than reinterpret. A chart that snaps
 * back to its full range is obviously back at full range; a chart showing the
 * wrong window looks exactly like a chart showing the right one.
 */

export interface Window {
  /** First visible index, inclusive. */
  from: number
  /** Last visible index, inclusive. */
  to: number
}

/** A selection under this many observations is a click that wandered. */
export const MIN_SPAN = 2

/**
 * Validate a stored window against the series it will be drawn on.
 * Returns null — meaning full range — whenever the window cannot be trusted.
 */
export function resolve(view: Window | null, total: number): Window | null {
  if (!view) return null
  if (total <= 0) return null
  // Out of bounds: the series changed under the window.
  if (view.to >= total || view.from < 0) return null
  if (view.to < view.from) return null
  // A window narrower than the minimum selection cannot have been drawn by a
  // deliberate gesture, so it is not honoured as one.
  if (view.to - view.from < MIN_SPAN) return null
  // A window covering everything is not a window.
  if (view.from === 0 && view.to === total - 1) return null
  return view
}

/**
 * Convert a drag, expressed in indices of the *currently visible* window, into
 * an absolute window over the full series. Returns null when the gesture was
 * too small to be a range selection.
 */
export function commit(drag: Window, offset: number, total: number): Window | null {
  const a = Math.min(drag.from, drag.to)
  const b = Math.max(drag.from, drag.to)
  if (b - a < MIN_SPAN) return null
  return resolve({ from: offset + a, to: offset + b }, total)
}

/** The visible bounds for a resolved window, defaulting to the whole series. */
export function bounds(view: Window | null, total: number): Window {
  const w = resolve(view, total)
  return w ?? { from: 0, to: Math.max(0, total - 1) }
}
