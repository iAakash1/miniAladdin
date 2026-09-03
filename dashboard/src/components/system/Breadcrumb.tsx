/**
 * The research path, not the URL hierarchy.
 *
 * A URL breadcrumb says "Factors / Momentum", which the reader already knows —
 * they are looking at it. What they cannot see is how they arrived: which model
 * sent them to this feature, which experiment sent them to that model.
 *
 * So this shows the last few objects actually opened, oldest first, ending at
 * where they are. It makes a research path visible and reversible, which is the
 * thing a terminal loses fastest when every click is a fresh page.
 *
 * It renders nothing on a first visit. A breadcrumb of one item is a label.
 */
'use client'

import Link from 'next/link'

import { useRecentObjects } from '@/lib/research/history'
import { KINDS, href as objectHref } from '@/lib/research/objects'

export default function Breadcrumb({ limit = 4 }: { limit?: number }) {
  const recent = useRecentObjects()
  // Recents are newest-first; a path reads oldest-first.
  const path = recent.slice(0, limit).reverse()

  if (path.length < 2) return null

  return (
    <nav className="sys-crumbs" aria-label="Research path">
      {path.map((o, i) => (
        <span key={`${o.kind}:${o.id}`} className="sys-crumb-wrap">
          {i > 0 ? <span className="sys-crumb-sep" aria-hidden>→</span> : null}
          <Link
            href={objectHref(o)}
            className="sys-crumb"
            aria-current={i === path.length - 1 ? 'page' : undefined}
            title={`${KINDS[o.kind].plural}${o.detail ? ` · ${o.detail}` : ''}`}
          >
            <span className="sys-crumb-glyph" aria-hidden>{KINDS[o.kind].glyph}</span>
            {o.label}
          </Link>
        </span>
      ))}
    </nav>
  )
}
