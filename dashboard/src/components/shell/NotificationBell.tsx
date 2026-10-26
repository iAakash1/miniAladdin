'use client'

/**
 * The top-bar bell: the server's unread count and the latest notifications.
 *
 * The count is the persisted one from `/api/notifications`, re-read on a timer
 * while the page is visible and after every mark-read, so it can never drift
 * from what the server holds. Opening a notification marks it read on the
 * server first and then navigates to the security it is about.
 */

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useId, useRef, useState } from 'react'

import { useDrawerFocus } from '@/components/system/useDrawerFocus'
import { markRead, refreshInbox, useInbox, useInboxPolling, type InboxItem, type InboxState } from '@/lib/alerts'
import { formatMoment } from '@/lib/quantity'

const SHOWN = 8

export default function NotificationBell() {
  const inbox = useInbox()
  useInboxPolling()
  const [open, setOpen] = useState(false)
  const panelId = useId()
  const wrap = useRef<HTMLDivElement>(null)
  const router = useRouter()

  // Focus moves into the panel, Escape closes it, and focus returns to the bell.
  const panel = useDrawerFocus<HTMLDivElement>(open, () => setOpen(false))

  useEffect(() => {
    if (!open) return
    void refreshInbox()
    const onClick = (e: MouseEvent) => { if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false) }
    window.addEventListener('mousedown', onClick)
    return () => window.removeEventListener('mousedown', onClick)
  }, [open])

  if (inbox.status === 'signed-out') return null

  const go = async (n: InboxItem) => {
    if (!n.read) await markRead(n.id)
    setOpen(false)
    if (n.link) router.push(n.link)
  }

  return (
    <BellView inbox={inbox} open={open} panelId={panelId} wrap={wrap} panel={panel} onToggle={() => setOpen(!open)} onOpen={(n) => void go(n)} onClose={() => setOpen(false)} />
  )
}

/** The bell as drawn for a given inbox. Exported so each state can be rendered in tests. */
export function BellView({
  inbox, open, panelId, wrap, panel, onToggle, onOpen, onClose,
}: {
  inbox: InboxState; open: boolean; panelId: string; wrap?: React.Ref<HTMLDivElement>; panel?: React.Ref<HTMLDivElement>
  onToggle: () => void; onOpen: (n: InboxItem) => void; onClose: () => void
}) {
  const label = inbox.unread ? `Notifications, ${inbox.unread} unread` : 'Notifications'
  return (
    <div className="bell" ref={wrap}>
      <button
        type="button" className="sys-btn sys-btn--icon bell__btn" aria-label={label}
        aria-expanded={open} aria-controls={panelId} onClick={onToggle}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
          <path d="M8 1.75a4 4 0 0 0-4 4v2.5L2.75 10.5v1h10.5v-1L12 8.25v-2.5a4 4 0 0 0-4-4Zm-1.75 11a1.75 1.75 0 0 0 3.5 0" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
        </svg>
        {inbox.unread ? <span className="bell__count" aria-hidden>{inbox.unread > 99 ? '99+' : inbox.unread}</span> : null}
      </button>
      {open ? (
        <div id={panelId} ref={panel} tabIndex={-1} className="bell__panel" role="dialog" aria-label="Notifications">
          <div className="bell__head">
            <span className="sys-label">Notifications</span>
            {inbox.unread ? <button type="button" className="sys-btn sys-btn--xs" onClick={() => void markRead()}>Mark all read</button> : null}
          </div>
          {inbox.status === 'loading' && !inbox.notifications.length ? (
            <p className="bell__state">Loading…</p>
          ) : inbox.status === 'error' && !inbox.notifications.length ? (
            <p className="bell__state">Notifications could not be read. Your alerts are unaffected.</p>
          ) : !inbox.notifications.length ? (
            <p className="bell__state">No notifications yet. Triggered alerts appear here.</p>
          ) : (
            <ol className="bell__list">
              {inbox.notifications.slice(0, SHOWN).map((n) => (
                <li key={n.id} data-read={n.read ? 'true' : undefined}>
                  <button type="button" className="bell__item" onClick={() => onOpen(n)}>
                    <span className="bell__title">{!n.read ? <><span className="inbox__dot" aria-hidden /><span className="visually-hidden">Unread: </span></> : null}{n.title}</span>
                    {n.body ? <span className="bell__body">{n.body}</span> : null}
                    <span className="sys-meta">{formatMoment(n.createdAt)}</span>
                  </button>
                </li>
              ))}
            </ol>
          )}
          {inbox.status === 'error' && inbox.notifications.length ? <p className="bell__state">Showing the last list read; the latest refresh failed.</p> : null}
          <Link className="bell__all" href="/terminal/alerts" onClick={onClose}>All alerts and notifications</Link>
        </div>
      ) : null}
    </div>
  )
}
