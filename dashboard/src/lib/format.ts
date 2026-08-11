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
  // Stays relative all the way out. The previous fallback returned
  // `toLocaleDateString` with the same options as `fmtDate`, so the very
  // common pairing `{fmtDate(t)} · {timeAgo(t)}` — used in the Vault table
  // and the report header — rendered the date twice ("Jul 28 · Jul 28")
  // for anything older than a week. Every call site phrases this as elapsed
  // time ("saved …", "opened …", "Updated …"), so a bare date was never the
  // right answer there either.
  // Rounded, not truncated, past a week. Truncating splits a single calendar
  // day across two buckets — two Vault rows both stamped "Jul 28" came out as
  // "1w ago" and "2w ago" purely from the hour they were run, which reads as
  // a bug even though the arithmetic is right. At week-and-coarser resolution
  // the nearest unit is the honest one.
  if (d < 32) return `${Math.round(d / 7)}w ago`
  if (d < 330) return `${Math.round(d / 30)}mo ago`
  return `${Math.round(d / 365)}y ago`
}

export function fmtDate(iso: string, opts?: Intl.DateTimeFormatOptions): string {
  return new Date(iso).toLocaleDateString('en-US', opts ?? { month: 'short', day: 'numeric' })
}
