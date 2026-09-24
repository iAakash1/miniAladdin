'use client'

import { useState } from 'react'

import { faviconFor } from '@/lib/identity'

/**
 * The mark of an organisation that is not a listed company — a data provider
 * or a publisher — from its own domain. The initial is painted first, so a
 * blocked or missing favicon degrades to a letter, never a broken image.
 */
export default function EntityMark({ domain, label, size = 18 }: {
  domain: string
  label: string
  size?: number
}) {
  const [state, setState] = useState<'loading' | 'ready' | 'failed'>('loading')
  return (
    <span
      className="emark"
      data-state={domain ? state : 'failed'}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.46) }}
      aria-hidden
    >
      <span className="emark__letter">{(label.trim()[0] ?? '?').toUpperCase()}</span>
      {domain && state !== 'failed' ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          className="emark__img"
          src={faviconFor(domain, 64)}
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
