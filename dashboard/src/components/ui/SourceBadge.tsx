'use client'

/**
 * SourceBadge — who said this.
 *
 * Attribution was already printed on every headline and macro card, as a raw
 * vendor string in the same grey as the timestamp beside it. That makes
 * provenance something you *read*; a mark makes it something you *recognise*,
 * which is the difference between checking a source and scanning for one.
 *
 * The favicon comes from the source's own domain (see lib/identity), so this
 * carries no bundled publisher logos and cannot attribute a claim to a
 * publisher that did not make it: with no resolvable domain, the badge
 * renders the name alone rather than a stand-in icon.
 */

import { useState } from 'react'

import { faviconFor, sourceDomain, sourceLabel } from '@/lib/identity'

export default function SourceBadge({
  name,
  url,
  /** Hide the text and keep only the mark, for rows that are already tight. */
  compact = false,
}: {
  name?: string | null
  url?: string | null
  compact?: boolean
}) {
  const [failed, setFailed] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const domain = sourceDomain(name, url)
  const label = sourceLabel(name, url)
  if (!domain && !label) return null

  return (
    <span className="sbadge" title={domain || label}>
      {/* Same posture as CompanyMark: the letter is painted first and the
          icon sits on top, so a blocked or slow favicon degrades to an
          initial rather than to a blank plate. */}
      <span className="sbadge__mark" data-state={loaded ? 'ready' : 'waiting'} aria-hidden>
        {label.charAt(0).toUpperCase()}
        {/* Intentionally not next/image: a 14px third-party favicon that must
            be allowed to fail silently, from an open set of publisher
            domains that cannot be enumerated in remotePatterns. */}
        {domain && !failed && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            className="sbadge__img"
            src={faviconFor(domain)}
            alt=""
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            onLoad={() => setLoaded(true)}
            onError={() => setFailed(true)}
          />
        )}
      </span>
      {!compact && <span className="sbadge__name">{label}</span>}
    </span>
  )
}
