'use client'

import { useParams } from 'next/navigation'

import CompanyWorkspace from '@/components/company/CompanyWorkspace'
import Workbench from '@/components/system/Workbench'
import { openPalette } from '@/components/system/Palette'

const TICKER_RE = /^[A-Z0-9.^-]{1,10}$/

/**
 * /company/{ticker} — the research workspace for one company. The URL is the
 * research request: opening it runs the full deterministic pipeline, so it is
 * safe to bookmark and share. `?tab=` selects a section.
 */
export default function CompanyPage() {
  const params = useParams<{ ticker: string }>()
  const ticker = decodeURIComponent(params.ticker ?? '').toUpperCase()
  const valid = TICKER_RE.test(ticker)

  return (
    <Workbench title={valid ? ticker : 'Company research'} header={false} flush>
      {valid ? (
        <CompanyWorkspace key={ticker} ticker={ticker} />
      ) : (
        <div className="cw-invalid">
          <p className="sys-label">Company research</p>
          <h1>“{ticker}” is not a ticker symbol</h1>
          <p>Symbols are one to ten letters or digits, such as AAPL, MSFT or BRK.B.</p>
          <button type="button" className="sys-btn sys-btn--primary" onClick={() => openPalette(ticker)}>Search for a company</button>
        </div>
      )}
    </Workbench>
  )
}
