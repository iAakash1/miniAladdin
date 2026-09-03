/* Formatting utilities — single source of truth for number/date rendering. */

/** Everything that is not a finite number renders as "no value".
 *
 *  `Number.isNaN` alone missed two cases that reach these functions from real
 *  data: a Sharpe ratio over zero realised volatility, and a return measured
 *  from a zero base, both of which are `Infinity`. They rendered literally —
 *  "+Infinity%" and "$∞" — which in a research terminal reads as a broken
 *  page rather than as an undefined statistic. */
function isMissing(v: number | null | undefined): boolean {
  return v == null || !Number.isFinite(v)
}

/** Strips the sign from a value that rounds to zero.
 *
 *  `(-0.000001).toFixed(2)` is "-0.00", and `-0` formats as "-$0.00". Both
 *  claim a direction the number does not have; a reader scanning a column of
 *  returns sees a loss that is not there. */
function unsignZero(text: string): string {
  return /^-0(\.0*)?$/.test(text) ? text.slice(1) : text
}

export function fmtPrice(v: number | null | undefined): string {
  if (isMissing(v)) return '—'
  // Round to the displayed precision *before* formatting. Checking for -0
  // alone is not enough: -0.0001 is not -0, but `toLocaleString` still
  // renders it "-$0.00" once rounded to two places.
  const rounded = Math.round((v as number) * 100) / 100
  return (rounded === 0 ? 0 : rounded).toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

export function fmtNum(v: number | null | undefined, digits = 2): string {
  if (isMissing(v)) return '—'
  return unsignZero((v as number).toFixed(digits))
}

/** 0.0431 -> "+4.31%" */
export function fmtPct(v: number | null | undefined, digits = 2, signed = true): string {
  if (isMissing(v)) return '—'
  const pct = (v as number) * 100
  const body = unsignZero(pct.toFixed(digits))
  // The '+' is decided after rounding, so a value that rounds to zero gets
  // neither sign rather than a '+' on a number that did not move.
  const sign = signed && parseFloat(body) > 0 ? '+' : ''
  return `${sign}${body}%`
}

/** 4.47 -> "4.47%" (already in percent units). `signed` adds a leading '+'
 *  for a real gain, decided after rounding like `fmtPct`. */
export function fmtPctRaw(
  v: number | null | undefined, digits = 2, signed = false,
): string {
  if (isMissing(v)) return '—'
  const body = unsignZero((v as number).toFixed(digits))
  return `${signed && parseFloat(body) > 0 ? '+' : ''}${body}%`
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
  /* Past a day, count calendar days rather than elapsed 24-hour blocks.
     Rounding alone does not hold the invariant it was chosen for: two stamps
     on one date can be 23 hours apart, which moves a floored day count by one,
     which can cross a rounding boundary. Eleven days and ten-and-a-bit days
     both fall on the same date and came out "2w ago" and "1w ago" — visible
     only when the page was opened near midnight, which is exactly the kind of
     bug that survives review.
     Counting from local midnight makes two timestamps on one date produce the
     same number by construction, at every coarser unit. */
  const midnight = (ms: number) => { const x = new Date(ms); x.setHours(0, 0, 0, 0); return x.getTime() }
  const d = Math.max(1, Math.round((midnight(Date.now()) - midnight(t)) / 86_400_000))
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
