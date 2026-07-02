/* Free-tier usage tracking. Client-side by design (portfolio product):
   the same localStorage keys as v1 so existing users keep their counts. */

export const FREE_DAILY_LIMIT = 5

const DATE_KEY = 'omni_date'
const COUNT_KEY = 'omni_count'

export function readTodayCount(): number {
  if (typeof window === 'undefined') return 0
  const today = new Date().toDateString()
  if (localStorage.getItem(DATE_KEY) !== today) {
    localStorage.setItem(DATE_KEY, today)
    localStorage.setItem(COUNT_KEY, '0')
    return 0
  }
  return parseInt(localStorage.getItem(COUNT_KEY) ?? '0', 10) || 0
}

export function bumpTodayCount(): number {
  const next = readTodayCount() + 1
  localStorage.setItem(COUNT_KEY, String(next))
  return next
}
