'use client'

import Link from 'next/link'

import { StateBlock } from '@/components/system'
import { age } from '@/components/company/derive'
import { useAlerts, useAlertsStatus, useInbox } from '@/lib/alerts'

/**
 * What is waiting on the reader: notifications they have not read and alerts
 * that have fired. Built only from the alert store and the inbox, so it can
 * say "nothing" only when both were read — a failed read is said as one.
 */
export default function Attention() {
  const alerts = useAlerts()
  const status = useAlertsStatus()
  const inbox = useInbox()

  const loading = status === 'idle' || status === 'loading' || inbox.status === 'idle' || inbox.status === 'loading'
  const signedOut = status === 'signed-out' || inbox.status === 'signed-out'
  const failed = status === 'error' && inbox.status === 'error'

  const fired = alerts.filter((a) => a.status === 'triggered')
  const active = alerts.filter((a) => a.status === 'active').length
  const paused = alerts.filter((a) => a.status === 'paused').length
  const unread = inbox.notifications.filter((n) => !n.read).slice(0, 4)

  const head = (
    <header className="sys-panel-head">
      <div className="sys-panel-head__title">
        <h2 className="sys-panel-title">Needs attention</h2>
        {status === 'ready' ? (
          <span className="sys-panel-sub">
            {active} active{paused ? ` · ${paused} paused` : ''}
          </span>
        ) : null}
      </div>
      <Link className="cw-more" href="/terminal/alerts">Alerts</Link>
    </header>
  )

  if (loading) {
    return <section className="sys-panel attn">{head}<StateBlock state="waking" title="Reading your alerts and inbox" /></section>
  }
  if (signedOut) {
    return (
      <section className="sys-panel attn">
        {head}
        <p className="attn__note">Sign in to see your alerts and notifications. They are stored with your account.</p>
      </section>
    )
  }
  if (failed) {
    return (
      <section className="sys-panel attn" data-state="unavailable">
        {head}
        <p className="attn__note">Alerts and the inbox could not be read right now, so this cannot say whether anything fired.</p>
      </section>
    )
  }

  const nothing = !fired.length && !unread.length

  return (
    <section className="sys-panel attn" aria-label="Needs attention">
      {head}
      {status === 'error' || inbox.status === 'error' ? (
        <p className="attn__warn">
          {status === 'error' ? 'Alerts could not be read; only the inbox is shown.' : 'The inbox could not be read; only alerts are shown.'}
        </p>
      ) : null}
      {nothing ? (
        <div className="attn__empty">
          {alerts.length ? (
            <p>Nothing has fired. {active ? `${active} ${active === 1 ? 'alert is' : 'alerts are'} watching.` : 'Every alert is paused.'}</p>
          ) : (
            <>
              <p>No alerts yet. An alert watches a price level, a move or a new SEC filing and notifies you here.</p>
              <Link href="/terminal/alerts" className="sys-btn sys-btn--xs">Create an alert</Link>
            </>
          )}
        </div>
      ) : (
        <ul className="attn__list">
          {unread.map((n) => (
            <li key={n.id} className="attn__row">
              <span className="attn__dot" aria-hidden />
              <span className="attn__main">
                {n.link ? <Link href={n.link} className="attn__title">{n.title}</Link> : <span className="attn__title">{n.title}</span>}
                {n.body ? <span className="attn__body">{n.body}</span> : null}
              </span>
              <span className="attn__when">{age(n.createdAt)}</span>
            </li>
          ))}
          {fired
            .filter((a) => !unread.some((n) => n.event?.ticker === a.ticker))
            .slice(0, 4)
            .map((a) => (
              <li key={a.id} className="attn__row">
                <span className="attn__dot attn__dot--read" aria-hidden />
                <span className="attn__main">
                  <Link href={`/company/${encodeURIComponent(a.ticker)}`} className="attn__title">
                    <span className="attn__sym">{a.ticker}</span> {a.condition}
                  </Link>
                  <span className="attn__body">Triggered — re-arm or remove it on the alerts page.</span>
                </span>
                <span className="attn__when">{a.last_triggered_at ? age(a.last_triggered_at) : ''}</span>
              </li>
            ))}
        </ul>
      )}
    </section>
  )
}
