import Link from 'next/link'
import type { ReactNode } from 'react'

import CompanyMark from '@/components/ui/CompanyMark'

const MARK: Record<'sm' | 'md' | 'lg', number> = { sm: 20, md: 28, lg: 44 }

/**
 * A listed company as the product shows it everywhere: logo (falling back to
 * a ticker monogram), ticker and name, optionally with a line of context.
 *
 *   sm  dense table rows
 *   md  lists, search results, watchlists
 *   lg  headers
 */
export default function CompanyIdentity({
  symbol, name, detail, size = 'md', href, trailing,
}: {
  symbol: string
  name?: string | null
  /** Secondary context: sector, exchange, a match reason. */
  detail?: ReactNode
  size?: 'sm' | 'md' | 'lg'
  href?: string
  trailing?: ReactNode
}) {
  const body = (
    <>
      <CompanyMark ticker={symbol} name={name} size={MARK[size]} />
      <span className="cid__text">
        <span className="cid__line">
          <span className="cid__sym">{symbol}</span>
          {size === 'sm' && name ? <span className="cid__name">{name}</span> : null}
          {trailing}
        </span>
        {size !== 'sm' && (name || detail) ? (
          <span className="cid__sub">
            {name ? <span className="cid__name">{name}</span> : null}
            {detail ? <span className="cid__detail">{detail}</span> : null}
          </span>
        ) : null}
      </span>
    </>
  )
  return href ? (
    <Link href={href} className="cid" data-size={size}>{body}</Link>
  ) : (
    <span className="cid" data-size={size}>{body}</span>
  )
}
