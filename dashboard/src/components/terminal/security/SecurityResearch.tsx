/**
 * Where this security connects to the research layer.
 *
 * Last on the page, deliberately. An analyst opening AAPL wants the price, the
 * chart and the business before they want the quantitative programme, and the
 * previous arrangement put this third — above the company itself.
 *
 * It is a set of links rather than an embedded panel because the research
 * payload is an order of magnitude slower than everything above it, and
 * because the honest summary is short: no model is deployed, so nothing here
 * scores this security.
 */

import Link from 'next/link'

import { Panel, Prose } from '@/components/system'

export default function SecurityResearch({ symbol }: { symbol: string }) {
  return (
    <Panel title="Research" subtitle="how this name connects to the research layer" state="recorded">
      <Prose>
        No production model is deployed, so nothing in the research programme
        scores this security. What the archive does hold is the factor work, the
        signal evidence and the experiment record that produced that verdict.
      </Prose>
      <div className="sys-run" style={{ marginTop: 'var(--d-3)' }}>
        <Link className="sys-btn" href={`/company/${encodeURIComponent(symbol)}`}>
          full research report
        </Link>
        <Link className="sys-btn" href="/terminal/factorlab">factors</Link>
        <Link className="sys-btn" href="/terminal/evidence">evidence</Link>
        <Link className="sys-btn" href="/terminal/risk">risk</Link>
      </div>
      <Prose size="fine">
        The full report runs the whole pipeline for this name and takes around a
        minute. Everything above this panel came from the market providers in
        under a second.
      </Prose>
    </Panel>
  )
}
