/* A date is the same day for everyone.

   A trading date arrives as "2026-10-07". `new Date("2026-10-07")` is midnight
   UTC, so formatting it in the reader's own zone printed the 6th for anyone west
   of Greenwich: a performance chart labelled every point a day early. The
   timeline had the opposite fault, grouping by the UTC date while labelling by
   the local one, so a dated filing and a same-day timestamp sat under two
   headings that read the same, east of UTC.

   Node reads TZ when it is assigned, so each case runs in the zone it is about. */

import assert from 'node:assert/strict'
import test from 'node:test'

import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import Timeline from '../src/components/visual/Timeline'
import { fmtDate } from '../src/lib/format'
import { formatDay, formatMoment } from '../src/lib/quantity'

const ZONES = ['Pacific/Honolulu', 'America/Los_Angeles', 'UTC', 'Europe/London', 'Asia/Kolkata', 'Pacific/Auckland']

function inZone<T>(zone: string, fn: () => T): T {
  const before = process.env.TZ
  process.env.TZ = zone
  try {
    return fn()
  } finally {
    if (before === undefined) delete process.env.TZ
    else process.env.TZ = before
  }
}

test('a date with no time is the same calendar day in every zone', () => {
  for (const zone of ZONES) {
    inZone(zone, () => {
      assert.equal(fmtDate('2026-10-07'), 'Oct 7', zone)
      assert.equal(fmtDate('2026-01-01'), 'Jan 1', zone)
      assert.equal(fmtDate('2026-12-31', { month: 'short', day: 'numeric', year: 'numeric' }), 'Dec 31, 2026', zone)
    })
  }
})

test('a timestamp is an instant and is shown on the reader\'s own day', () => {
  inZone('America/Los_Angeles', () => assert.equal(fmtDate('2026-10-07T03:00:00Z'), 'Oct 6'))
  inZone('Asia/Kolkata', () => assert.equal(fmtDate('2026-10-07T03:00:00Z'), 'Oct 7'))
})

test('a dated filing and a same-day timestamp share one heading', () => {
  const items = [
    { id: 'filing', kind: 'filing' as const, date: '2026-10-07', title: 'Form 4' },
    { id: 'story', kind: 'news' as const, date: '2026-10-07T08:00:00', title: 'A story' },
  ]
  for (const zone of ZONES) {
    inZone(zone, () => {
      const html = renderToStaticMarkup(createElement(Timeline, { items }))
      assert.equal((html.match(/class="tl-day"/g) ?? []).length, 1, `${zone}: one calendar day became two groups`)
      assert.equal((html.match(/Oct 7/g) ?? []).length, 1, `${zone}: the heading is repeated`)
    })
  }
})

test('items on different days stay on different headings, newest first', () => {
  const items = [
    { id: 'a', kind: 'news' as const, date: '2026-10-06', title: 'older' },
    { id: 'b', kind: 'news' as const, date: '2026-10-08', title: 'newer' },
  ]
  for (const zone of ZONES) {
    inZone(zone, () => {
      const html = renderToStaticMarkup(createElement(Timeline, { items }))
      assert.equal((html.match(/class="tl-day"/g) ?? []).length, 2, zone)
      assert.ok(html.indexOf('Oct 8') < html.indexOf('Oct 6'), `${zone}: not newest first`)
    })
  }
})

test('an instant is named in UTC, and text that is not a date is no value', () => {
  for (const zone of ZONES) {
    inZone(zone, () => {
      assert.equal(formatMoment('2026-10-07T14:30:00Z'), 'Oct 7, 14:30 UTC', zone)
      assert.equal(formatMoment('2026-10-07T00:05:00Z'), 'Oct 7, 00:05 UTC', zone)
    })
  }
  for (const bad of [null, undefined, '', 'yesterday-ish', 'Invalid Date']) assert.equal(formatMoment(bad), '—')
})

test('a calendar day is read from an ISO prefix, never by constructing a Date', () => {
  assert.equal(formatDay('2026-10-07T23:59:59.000Z'), '2026-10-07')
  for (const bad of [null, undefined, '', 'NaN', 'Oct 7']) assert.equal(formatDay(bad), '—')
})

test('a coverage window never contains a date that cannot be read', async () => {
  const { readFileSync } = await import('node:fs')
  const { join } = await import('node:path')
  const text = readFileSync(join(__dirname, '..', 'src', 'components', 'terminal', 'data', 'Coverage.tsx'), 'utf8')
  assert.match(text, /Number\.isFinite\(Date\.parse\(s\.min_date\)\)/)
  assert.match(text, /Number\.isFinite\(Date\.parse\(s\.max_date\)\)/)
})

test('a memo with an unreadable time shows no time instead of throwing', async () => {
  const { readFileSync } = await import('node:fs')
  const { join } = await import('node:path')
  const text = readFileSync(join(__dirname, '..', 'src', 'components', 'terminal', 'memos', 'Memos.tsx'), 'utf8')
  assert.doesNotMatch(text, /new Date\([^)]*updatedAt[^)]*\)\.toISOString\(\)/, 'toISOString() throws on an invalid time')
  assert.match(text, /Number\.isFinite\(ms\)/)
})
