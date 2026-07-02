/* Formatting utilities — single source of truth for number/date rendering. */

export function fmtPrice(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

export function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(digits)
}

/** 0.0431 -> "+4.31%" */
export function fmtPct(v: number | null | undefined, digits = 2, signed = true): string {
  if (v == null || Number.isNaN(v)) return '—'
  const pct = v * 100
  const sign = signed && pct > 0 ? '+' : ''
  return `${sign}${pct.toFixed(digits)}%`
}

/** 4.47 -> "4.47%" (already in percent units) */
export function fmtPctRaw(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${v.toFixed(digits)}%`
}

export function parsePercentString(v: string | number | null | undefined): number {
  if (v == null) return 0
  if (typeof v === 'number') return v
  const n = parseFloat(v.replace('%', '').replace('N/A', ''))
  return Number.isNaN(n) ? 0 : n
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const diff = Date.now() - t
  const m = Math.floor(diff / 60_000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  if (d < 7) return `${d}d ago`
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export function fmtDate(iso: string, opts?: Intl.DateTimeFormatOptions): string {
  return new Date(iso).toLocaleDateString('en-US', opts ?? { month: 'short', day: 'numeric' })
}
