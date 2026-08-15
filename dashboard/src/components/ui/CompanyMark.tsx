'use client'

/**
 * CompanyMark — a company's logo, with a monogram that is never a fallback
 * in the apologetic sense.
 *
 * Rows of tickers are scanned, not read. A mark gives each row an anchor the
 * eye can find without parsing four monospace characters, which is the whole
 * reason watchlists and archives in real terminals carry one.
 *
 * ## Why the monogram is drawn first
 *
 * The logo is fetched from a third party and will sometimes 404 (ETFs,
 * delisted names, anything the provider has not catalogued) or simply be
 * slow. So the monogram is always rendered and the image sits on top of it:
 * nothing pops in, nothing reflows, and a missing logo degrades to a mark
 * that still looks deliberate rather than to a broken-image glyph.
 *
 * The monogram's tint is derived from the ticker, so the same company always
 * gets the same colour and the eye can learn it. Hues are pinned to the
 * existing token palette rather than generated freely — a random hue would
 * be the one thing on screen not drawn from the design system.
 *
 * A plain <img> rather than next/image on purpose: this needs no optimizer,
 * no `remotePatterns` entry, and no layout negotiation — it is a fixed-size
 * square that must fail silently.
 */

import { useState } from 'react'

/** Stable index into the token tints, from the ticker itself. */
function tint(ticker: string): number {
  let hash = 0
  for (let i = 0; i < ticker.length; i += 1) hash = (hash * 31 + ticker.charCodeAt(i)) | 0
  return Math.abs(hash) % 6
}

export default function CompanyMark({
  ticker,
  size = 22,
}: {
  ticker: string
  /** Square edge in px. 22 suits table rows; 40+ suits a page header. */
  size?: number
}) {
  const [failed, setFailed] = useState(false)
  const symbol = ticker.toUpperCase()

  return (
    <span
      className={`cmark cmark--t${tint(symbol)}`}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.4) }}
      aria-hidden
    >
      <span className="cmark__mono">{symbol.slice(0, 2)}</span>
      {/* Intentionally not next/image: a fixed-size third-party mark that
          must be allowed to fail silently. Routing it through the optimizer
          would need a remotePatterns entry per provider and would turn a 404
          into a build-time concern. */}
      {!failed && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          className="cmark__img"
          src={`https://financialmodelingprep.com/image-stock/${encodeURIComponent(symbol)}.png`}
          alt=""
          loading="lazy"
          decoding="async"
          onError={() => setFailed(true)}
        />
      )}
    </span>
  )
}
