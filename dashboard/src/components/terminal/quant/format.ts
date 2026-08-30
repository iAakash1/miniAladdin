import type { StatusTone } from '@/components/ui/DataMarks'

/**
 * Formatters for the quant terminal.
 *
 * Every one returns an em dash for null and **never** zero. A zero that means
 * "not measured" is the most expensive lie a research UI can tell: it is
 * indistinguishable from a measured zero, and a blank correction column looks
 * exactly like a correction that was applied and passed.
 */

export const f = (v: number | null | undefined, d = 4) =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : v.toFixed(d)

export const sign = (v: number | null | undefined, d = 4) =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : (v >= 0 ? '+' : '') + v.toFixed(d)

export const pct = (v: number | null | undefined) =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : `${(v * 100).toFixed(0)}%`

export const num = (v: number | null | undefined, d = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : v.toFixed(d)

export const int = (v: number | null | undefined) =>
  v === null || v === undefined ? '—' : v.toLocaleString()

/** Verdict labels come from the backend; this only chooses a colour for them. */
export const VERDICT_TONE: Record<string, StatusTone> = {
  ROBUST: 'pos',
  PROMISING: 'accent',
  EXPERIMENTAL: 'muted',
  OVERFIT: 'warn',
  UNTRADEABLE: 'warn',
  REJECTED: 'neg',
}

/**
 * Validation dates a regime needs before its metrics may be quoted.
 * Mirrors `REGIME_MIN_DATES` in `scripts/quant/register_experiment.py`; the
 * backend marks thin regimes INSUFFICIENT and this only styles them.
 */
export const REGIME_MIN_DATES = 200
