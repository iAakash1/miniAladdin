/** Standard 8-K item numbers, as the SEC defines them. */
const ITEM_8K: Record<string, string> = {
  '1.01': 'material agreement', '1.02': 'agreement terminated', '2.01': 'acquisition or disposition',
  '2.02': 'results of operations', '2.03': 'new obligation', '2.05': 'exit costs', '2.06': 'impairment',
  '3.01': 'listing notice', '4.01': 'auditor change', '4.02': 'non-reliance on financials',
  '5.02': 'officer or director change', '5.03': 'charter or bylaw change', '5.07': 'shareholder vote',
  '7.01': 'Regulation FD disclosure', '8.01': 'other events', '9.01': 'financial statements and exhibits',
}

export function filingItems(items: string | null): string | null {
  if (!items) return null
  return items.split(/[,\s]+/).filter(Boolean)
    .map((code) => (ITEM_8K[code] ? `${code} ${ITEM_8K[code]}` : code)).join(' · ')
}
