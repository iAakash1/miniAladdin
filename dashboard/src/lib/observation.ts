/**
 * Distinguishing what is true now from what was true last time anyone looked.
 *
 * The status rail shipped a version that kept announcing HOLDOUT SEALED and
 * REGISTRY 103 ENTRIES while the backend was unreachable. Both had been true
 * an hour earlier. Neither was known at the moment they were displayed, and
 * the rail is the reassuring strip that is always in view, which makes it the
 * last thing a reader would think to doubt.
 *
 * The fix was to show nothing. That is correct and it is wasteful: a reader
 * who has just lost the backend usually still wants to know what it last said,
 * provided the screen is honest that this is what it is doing.
 *
 * So there are two acceptable renderings and one forbidden one:
 *
 *   REGISTRY  103 entries                          — only while observed
 *   REGISTRY  unavailable · last seen 103, 16:31   — after an outage
 *   REGISTRY  103 entries                          — during an outage: FORBIDDEN
 *
 * The distinction is the whole point of this module. A remembered value must
 * arrive labelled with when it was seen, and must never occupy the position a
 * current value would.
 */

export type ObservationState =
  /** Read successfully on the current request. */
  | 'observed'
  /** The current request failed; this is what the last successful one said. */
  | 'last-observed'
  /** The current request failed and nothing was ever successfully read. */
  | 'unavailable'
  /** Read successfully, and the source reports it holds no value. */
  | 'not-recorded'

export interface Observed<T> {
  state: ObservationState
  /** The value, current or remembered. Null when nothing was ever read. */
  value: T | null
  /** When `value` was actually read. Null when there is no value. */
  at: string | null
  /** Why the current read failed, when it did. */
  detail?: string
}

export function observed<T>(value: T, at: string = new Date().toISOString()): Observed<T> {
  return { state: 'observed', value, at }
}

export function notRecorded<T>(at: string = new Date().toISOString()): Observed<T> {
  return { state: 'not-recorded', value: null, at }
}

/**
 * Fold a failed read into whatever was known before it.
 *
 * With a previous success this degrades to `last-observed`, keeping the old
 * value and — critically — the timestamp it was read at, not the time of the
 * failure. With no previous success it is simply unavailable, and no value is
 * invented to fill the space.
 */
export function failed<T>(previous: Observed<T> | null, detail: string): Observed<T> {
  if (previous && previous.value !== null && previous.at !== null) {
    return { state: 'last-observed', value: previous.value, at: previous.at, detail }
  }
  return { state: 'unavailable', value: null, at: null, detail }
}

/** Whether the value describes the present. */
export function isCurrent<T>(o: Observed<T>): boolean {
  return o.state === 'observed'
}

/**
 * How a remembered observation should be introduced.
 *
 * Always the words "last seen", never a bare value. The phrase is what stops a
 * stale figure being read as a live one, so it is generated here rather than
 * left to each call site to remember.
 */
export function staleNote<T>(o: Observed<T>, render: (v: T) => string): string | null {
  if (o.state !== 'last-observed' || o.value === null || o.at === null) return null
  return `last seen ${render(o.value)} · ${o.at.slice(0, 19).replace('T', ' ')}`
}

/**
 * How long ago, in whole minutes, or null when there is nothing to age.
 * Used to decide whether a remembered value is worth showing at all.
 */
export function ageMinutes<T>(o: Observed<T>, now: number = Date.now()): number | null {
  if (o.at === null) return null
  const t = Date.parse(o.at)
  if (!Number.isFinite(t)) return null
  return Math.max(0, Math.round((now - t) / 60_000))
}
