'use client'

import Link from 'next/link'
import { useEffect } from 'react'

import Logo from '@/components/ui/Logo'

import { StateBlock } from './index'

/**
 * What a reader sees when a view throws while rendering.
 *
 * Without a boundary the framework shows its own blank "Application error"
 * screen, which names neither the product nor the cause and offers no way
 * back. A malformed provider field reaching a formatter is enough to trigger
 * it, so the failure has to be contained and described rather than left to
 * the default.
 *
 * Says only what is known: the view failed to render, nothing was saved or
 * changed, and no figures are shown in its place. The `digest` is the
 * framework's own opaque reference to the server-side log entry — safe to
 * display, and what someone reporting the problem can quote.
 */
export default function RouteError({
  error,
  reset,
  scope = 'view',
}: {
  error: Error & { digest?: string }
  reset: () => void
  scope?: string
}) {
  useEffect(() => {
    // Reaches the browser console and any error monitor attached to it.
    console.error(error)
  }, [error])

  return (
    <main
      id="main"
      role="alert"
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 20,
        padding: 24,
        background: 'var(--bg, var(--paper))',
        color: 'var(--text, var(--ink))',
      }}
    >
      <Logo size={22} />
      <div style={{ width: '100%', maxWidth: 520 }}>
        <StateBlock
          state="unavailable"
          title={`This ${scope} could not be displayed`}
          detail="An error interrupted rendering. Nothing was saved or changed, and no figures are shown in its place. Trying again often clears a transient fault; if it persists, the data behind this view may be unavailable."
        >
          {error.digest ? (
            <div className="sys-meta">
              Reference <span className="sys-num">{error.digest}</span>
            </div>
          ) : null}
        </StateBlock>
      </div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', justifyContent: 'center' }}>
        <button type="button" className="sys-btn sys-btn--primary" onClick={() => reset()}>
          Try again
        </button>
        <Link href="/" className="sys-btn">
          Home
        </Link>
        <Link href="/terminal" className="sys-btn">
          Open terminal
        </Link>
      </div>
    </main>
  )
}
