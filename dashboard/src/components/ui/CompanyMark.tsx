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
 * The logo is fetched from a third party and will sometimes 404 (delisted
 * names, anything the provider has not catalogued) or simply be slow. So the
 * monogram is always rendered and the image sits on top of it: nothing pops
 * in, nothing reflows, and a missing logo degrades to a mark that still
 * looks deliberate rather than to a broken-image glyph.
 *
 * The monogram's tint is derived from the ticker, so the same company always
 * gets the same colour and the eye can learn it. Hues are pinned to the
 * existing token palette rather than generated freely — a random hue would
 * be the one thing on screen not drawn from the design system.
 *
 * ## Why two providers
 *
 * `onError` advances through `logoSources` instead of giving up. Neither
 * provider covers the whole universe, and a symbol missing from the first is
 * often present in the second, so one 404 is not evidence that a company has
 * no logo. The monogram is only *revealed* once every provider has answered.
 *
 * ## Why the plate is only painted once a logo resolves
 *
 * Provider marks are mostly dark-on-transparent and need a light plate to
 * stay legible on the terminal's dark surface — but painting that plate
 * before the image loads produces a white square, which is what a broken
 * mark looks like. `data-state` gates it: the plate arrives with the pixels.
 *
 * A plain <img> rather than next/image on purpose: this needs no optimizer,
 * no `remotePatterns` entry, and no layout negotiation — it is a fixed-size
 * square that must fail silently.
 */

import { useState } from 'react'

import { logoSources } from '@/lib/identity'

/** Stable index into the token tints, from the ticker itself. */
function tint(ticker: string): number {
  let hash = 0
  for (let i = 0; i < ticker.length; i += 1) hash = (hash * 31 + ticker.charCodeAt(i)) | 0
  return Math.abs(hash) % 6
}

export default function CompanyMark({
  ticker,
  name,
  size = 22,
}: {
  ticker: string
  /** Company name, when the caller has one. Becomes the hover title, so a
   *  mark in a dense row can be identified without leaving the row. */
  name?: string | null
  /** Square edge in px. 22 suits table rows; 40+ suits a page header. */
  size?: number
}) {
  const symbol = ticker.toUpperCase()
  const sources = logoSources(symbol)
  /* Which provider is being tried. Past the end means every provider has
     answered and the monogram is the final word. */
  const [attempt, setAttempt] = useState(0)
  const [loaded, setLoaded] = useState(false)

  const src = sources[attempt]
  const state = loaded ? 'ready' : src ? 'loading' : 'none'

  return (
    <span
      className={`cmark cmark--t${tint(symbol)}`}
      data-state={state}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.4) }}
      title={name ? `${symbol} · ${name}` : undefined}
      aria-hidden
    >
      <span className="cmark__mono">{symbol.slice(0, 2)}</span>
      {/* Intentionally not next/image: a fixed-size third-party mark that
          must be allowed to fail silently. Routing it through the optimizer
          would need a remotePatterns entry per provider and would turn a 404
          into a build-time concern. */}
      {src && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          /* Keyed by src so a provider change remounts the element rather
             than asking the browser to re-fire load events on a node whose
             attribute changed mid-flight. */
          key={src}
          className="cmark__img"
          src={src}
          alt=""
          loading="lazy"
          decoding="async"
          onLoad={() => setLoaded(true)}
          onError={() => setAttempt((index) => index + 1)}
        />
      )}
    </span>
  )
}
