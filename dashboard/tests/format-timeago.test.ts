/* `timeAgo` must never return a string that `fmtDate` would also return.
   The Vault table and the report header both render `{fmtDate(t)} · {timeAgo(t)}`,
   and the old >7d fallback used the same `toLocaleDateString` options as
   `fmtDate`, so those rows printed the date twice ("Jul 28 · Jul 28"). */
import { strict as assert } from 'node:assert'
import test from 'node:test'
import { fmtDate, timeAgo } from '../src/lib/format'

const DAY = 86_400_000
const ago = (ms: number) => new Date(Date.now() - ms).toISOString()

test('stays relative at every age, so it never collides with fmtDate', () => {
  // Walk out to five years a day at a time — this is the property that was
  // broken, and a handful of hand-picked ages would have missed the boundary.
  for (let days = 0; days <= 365 * 5; days += 1) {
    const iso = ago(days * DAY + 60_000)
    const relative = timeAgo(iso)
    assert.notEqual(
      relative,
      fmtDate(iso),
      `timeAgo duplicated fmtDate at ${days}d: "${relative}"`,
    )
    assert.match(relative, /ago$/, `expected elapsed-time phrasing at ${days}d, got "${relative}"`)
  }
})

test('uses the largest unit that keeps the count meaningful', () => {
  assert.equal(timeAgo(ago(3 * 60_000)), '3m ago')
  assert.equal(timeAgo(ago(5 * 3_600_000)), '5h ago')
  assert.equal(timeAgo(ago(3 * DAY)), '3d ago')
  assert.equal(timeAgo(ago(10 * DAY)), '1w ago')
  assert.equal(timeAgo(ago(60 * DAY)), '2mo ago')
  assert.equal(timeAgo(ago(400 * DAY)), '1y ago')
})

test('two runs on the same calendar day report the same age', () => {
  // The Vault shows `{fmtDate} · {timeAgo}`. Two rows stamped with the same
  // date must not disagree about how long ago that was.
  for (let days = 8; days <= 200; days += 1) {
    const base = days * DAY
    const morning = timeAgo(ago(base))
    const evening = timeAgo(ago(base - 23 * 3_600_000))
    if (fmtDate(ago(base)) === fmtDate(ago(base - 23 * 3_600_000))) {
      assert.equal(morning, evening, `same day (${days}d) disagreed: ${morning} vs ${evening}`)
    }
  }
})

test('is monotonic — an older timestamp never reads as more recent', () => {
  const rank = (iso: string) => {
    const [, n, unit] = /^(\d+)(m|h|d|w|mo|y) ago$/.exec(timeAgo(iso)) ?? []
    const scale: Record<string, number> = { m: 60e3, h: 3.6e6, d: DAY, w: 7 * DAY, mo: 30 * DAY, y: 365 * DAY }
    return Number(n) * scale[unit]
  }
  let previous = 0
  for (const days of [0.5, 1, 3, 8, 20, 45, 120, 300, 800]) {
    const current = rank(ago(days * DAY))
    assert.ok(current >= previous, `non-monotonic at ${days}d`)
    previous = current
  }
})

test('empty input and unparseable dates render as nothing, not "NaN ago"', () => {
  assert.equal(timeAgo(null), '')
  assert.equal(timeAgo(undefined), '')
  assert.equal(timeAgo(''), '')
  assert.equal(timeAgo('not-a-date'), '')
})
