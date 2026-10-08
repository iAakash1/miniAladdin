/* Newest first. A story with no date has no place in that order, so it goes
   last instead of being given the time it was fetched. */

const at = (iso: string) => (iso ? Date.parse(iso) : Number.NEGATIVE_INFINITY)

export function byNewest(a: { publishedAt: string }, b: { publishedAt: string }): number {
  const x = at(a.publishedAt)
  const y = at(b.publishedAt)
  // An unparseable date sorts with the undated: both are "not known to be new".
  const left = Number.isNaN(x) ? Number.NEGATIVE_INFINITY : x
  const right = Number.isNaN(y) ? Number.NEGATIVE_INFINITY : y
  return left === right ? 0 : right > left ? 1 : -1
}
