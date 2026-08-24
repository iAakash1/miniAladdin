'use client'

/**
 * Editorial context imagery for a company.
 *
 * Loaded on its own request, *after* the research payload has rendered, and
 * never on the critical path of a price. A slow stock-photo API can only
 * delay a photograph.
 *
 * ## The distinction this component exists to preserve
 *
 * A company's logo is a factual claim about who it is. This is not that.
 * The image below is chosen from a query built out of the company's own
 * *industry* — "semiconductors", "financial services industry" — and is
 * labelled as editorial context wherever it appears. Presenting a stock
 * library photograph as a company's own image is a small lie repeated on
 * every page view, so the caption says what it is and the alt text describes
 * the photograph rather than the company.
 *
 * Renders nothing at all when no image resolves. There is deliberately no
 * generic fallback: a placeholder gradient would be decoration pretending to
 * be information.
 */

import { useEffect, useState } from 'react'

interface MediaAsset {
  provider: string
  image_url: string
  thumbnail_url: string
  source_url: string
  alt_text: string
  photographer: string
  photographer_url: string
  width: number | null
  height: number | null
}

interface MediaPayload {
  context: {
    asset: MediaAsset
    query: string
    providers: string[]
    cached: boolean
    kind: string
    disclaimer: string
  } | null
}

export default function CompanyMedia({
  ticker, sector, industry, name,
}: {
  ticker: string
  sector?: string | null
  industry?: string | null
  name?: string | null
}) {
  const [media, setMedia] = useState<MediaPayload | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let alive = true
    const controller = new AbortController()
    const query = new URLSearchParams()
    if (sector) query.set('sector', sector)
    if (industry) query.set('industry', industry)
    if (name) query.set('name', name)

    fetch(`/api/company/${encodeURIComponent(ticker)}/media?${query}`, {
      signal: controller.signal,
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data: MediaPayload) => { if (alive) setMedia(data) })
      .catch((error: unknown) => {
        // Imagery is enrichment. A failure here must be invisible, not an
        // error state competing with the financial data on the page.
        if ((error as Error).name !== 'AbortError') setFailed(true)
      })
    return () => { alive = false; controller.abort() }
  }, [ticker, sector, industry, name])

  const context = media?.context
  if (failed || !context?.asset?.image_url) return null

  const { asset } = context

  return (
    <figure className="cmedia">
      {/* Fixed aspect ratio reserved before the image loads, so arrival
          cannot shift the sections beneath it. */}
      <div className="cmedia__frame">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={asset.image_url}
          alt={asset.alt_text || `Editorial imagery for the ${context.query} industry`}
          width={asset.width ?? undefined}
          height={asset.height ?? undefined}
          loading="lazy"
          decoding="async"
        />
      </div>
      <figcaption className="cmedia__cap">
        <span className="cmedia__kind">Editorial context · {context.query}</span>
        {/* Both libraries require credit with a link back, and the flag
            travels on the asset so a renderer cannot omit it by forgetting
            which provider supplied it. */}
        {asset.photographer && (
          <span className="cmedia__credit">
            Photo by{' '}
            <a href={asset.photographer_url} target="_blank" rel="noopener noreferrer">
              {asset.photographer}
            </a>{' '}
            on{' '}
            <a href={asset.source_url} target="_blank" rel="noopener noreferrer">
              {asset.provider === 'pexels' ? 'Pexels' : 'Unsplash'}
            </a>
          </span>
        )}
      </figcaption>
    </figure>
  )
}
