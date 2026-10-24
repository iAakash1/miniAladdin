/**
 * Facts the legal pages and the footer share, held in one place so the pages
 * cannot disagree with each other or with the backend.
 *
 * `LEGAL_LAST_UPDATED` is the date the current wording was written. Change it
 * whenever the wording of either page changes, and only then.
 */

export const LEGAL_LAST_UPDATED = '2026-10-25'

export const REPOSITORY_URL = 'https://github.com/iAakash1/miniAladdin'

/** The only contact channel the project has published. Issues are public. */
export const CONTACT_URL = `${REPOSITORY_URL}/issues`

/**
 * The notice FRED's API terms require of a public application, verbatim.
 * `tests/legal-pages.test.ts` holds it equal to the backend catalog's copy.
 */
export const FRED_NOTICE =
  'This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.'

export const FRED_TERMS_URL = 'https://fred.stlouisfed.org/docs/api/terms_of_use.html'

export function legalDate(iso: string = LEGAL_LAST_UPDATED): string {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-US', {
    year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC',
  })
}
