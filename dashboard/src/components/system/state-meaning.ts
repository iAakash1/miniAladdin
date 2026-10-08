/**
 * What each research state means, in one place.
 *
 * Plain TypeScript with no React in it, because three different kinds of
 * consumer need the same words: the `Status` chip (a client component), the
 * hidden description every chip points at (a server component, which cannot
 * read values exported from a 'use client' module), and the key printed in the
 * handbook. One table means the three cannot drift apart - a chip that says
 * "stale" and a key that defines "stale" differently is a trust failure.
 */

export type ResearchState =
  | 'live' | 'recorded' | 'stale' | 'waking' | 'unavailable'
  | 'blocked' | 'experimental' | 'candidate' | 'production' | 'unknown'
  | 'retired' | 'paper' | 'error' | 'warning' | 'info'

export const STATE_TITLE: Record<ResearchState, string> = {
  live:         'Observed now, inside its freshness window',
  recorded:     'A fact read from a stored artifact — it cannot go stale',
  stale:        'Real, but past its freshness window',
  waking:       'Being retrieved; no value yet',
  unavailable:  'Refused or absent. No value is being shown in its place',
  blocked:      'A research constraint prevents this, not an error',
  experimental: 'Exists and is measured, but is not promotable',
  candidate:    'Cleared the development gates; holdout not yet spent',
  production:   'Armed and serving',
  unknown:      'State could not be determined',
  retired:      'Withdrawn from use. Kept in the record, never served',
  paper:        'Simulated. No real order, money or position is involved',
  error:        'The request failed. The cause is shown with it',
  warning:      'Usable, but something about it needs a second look',
  info:         'For the reader’s information; nothing needs doing',
}

export const STATE_LABEL: Record<ResearchState, string> = {
  live: 'live',
  recorded: 'recorded',
  stale: 'stale',
  waking: 'loading',
  unavailable: 'unavailable',
  blocked: 'blocked',
  experimental: 'experimental',
  candidate: 'candidate',
  production: 'production',
  unknown: 'unknown',
  retired: 'retired',
  paper: 'paper',
  error: 'error',
  warning: 'warning',
  info: 'info',
}

/** The order the key lists them in: trust first, then lifecycle, then notices. */
export const STATE_ORDER: readonly ResearchState[] = [
  'live', 'recorded', 'stale', 'waking', 'unavailable', 'unknown',
  'blocked', 'experimental', 'candidate', 'production', 'retired', 'paper',
  'error', 'warning', 'info',
]

/** The id of the shared, hidden description of one state. */
export const stateMeaningId = (state: ResearchState): string => `state-meaning-${state}`
