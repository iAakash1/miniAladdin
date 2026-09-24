'use client'

import { useState } from 'react'

import EntityMark from './EntityMark'
import { sourceDomain, sourceLabel } from '@/lib/identity'

/**
 * A publisher's own image for an article, at a fixed aspect ratio so nothing
 * shifts as it loads. Without a usable image — none supplied, not https, or it
 * fails — the tile shows the publisher's mark instead. Decorative: the
 * headline beside it carries the meaning.
 */
export default function Thumb({ src, source, url, width = 112, ratio = '16 / 10' }: {
  src?: string | null
  source?: string | null
  url?: string | null
  width?: number | string
  ratio?: string
}) {
  const usable = Boolean(src && /^https:\/\//i.test(src))
  const [state, setState] = useState<'loading' | 'ready' | 'failed'>(usable ? 'loading' : 'failed')
  const domain = sourceDomain(source, url)
  const label = sourceLabel(source, url)

  return (
    <span className="thumb" data-state={state} style={{ width, aspectRatio: ratio }} aria-hidden>
      <span className="thumb__fallback">
        <EntityMark domain={domain} label={label} size={20} />
      </span>
      {usable && state !== 'failed' ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          className="thumb__img"
          src={src as string}
          alt=""
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          onLoad={() => setState('ready')}
          onError={() => setState('failed')}
        />
      ) : null}
    </span>
  )
}
