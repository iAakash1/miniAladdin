'use client'

/**
 * Alerts and the inbox.
 *
 * Every alert shows what the server's evaluator last concluded and when, in
 * its own words: "triggered", "not crossed", "baseline set", or "skipped:
 * quote is stale". A skip is not an evaluation, and the "last checked" time
 * only moves when the condition was actually tested against usable data.
 */

import Link from 'next/link'
import { useState } from 'react'

import AlertEditor from './AlertEditor'
import Drawer from '@/components/shell/Drawer'
import ActionMenu from '@/components/system/ActionMenu'
import { Panel, StateBlock, Status } from '@/components/system'
import {
  deleteAlert, describeResult, markRead, setAlertStatus, useAlerts, useAlertsStatus, useInbox,
  type PriceAlert,
} from '@/lib/alerts'
import { formatMoment } from '@/lib/quantity'

const FRESH: Record<string, string> = { live: 'live', delayed: 'delayed', end_of_day: 'last close', stale: 'stale' }

export default function AlertsWorkspace() {
  const alerts = useAlerts()
  const status = useAlertsStatus()
  const inbox = useInbox()
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<PriceAlert | null>(null)

  const act = (fn: () => Promise<void>) => { setError(null); fn().catch((e: Error) => setError(e.message)) }

  if (status === 'signed-out' || inbox.status === 'signed-out') {
    return (
      <StateBlock
        state="blocked" title="Sign in to use alerts"
        detail="Alerts and their notifications are stored with your account. Your session was not accepted, so nothing here can be read or changed until you sign in again."
      />
    )
  }

  const counts = {
    active: alerts.filter((a) => a.status === 'active').length,
    triggered: alerts.filter((a) => a.status === 'triggered').length,
    paused: alerts.filter((a) => a.status === 'paused').length,
  }

  return (
    <div className="alerts">
      {alerts.length || inbox.notifications.length ? (
        <dl className="alerts-sum" aria-label="Alert summary">
          <div><dt>Active</dt><dd>{counts.active}</dd></div>
          <div><dt>Triggered</dt><dd>{counts.triggered}</dd></div>
          <div><dt>Paused</dt><dd>{counts.paused}</dd></div>
          <div><dt>Unread notifications</dt><dd>{inbox.unread}</dd></div>
        </dl>
      ) : null}

      <div className="alerts-grid">
        <div className="alerts-main">
          <Panel title="Your alerts" subtitle={`${alerts.length} defined · evaluated on the server's schedule`} flush>
            {error ? <p className="trk-error" role="alert">{error}</p> : null}
            {status === 'loading' && !alerts.length ? <StateBlock state="waking" title="Loading alerts" />
              : status === 'error' ? <StateBlock state="unavailable" title="Alerts are unavailable right now" detail="The persistence service did not answer." />
                : !alerts.length ? (
                  <div className="alerts-empty">
                    <p className="alerts-empty__title">No alerts yet</p>
                    <p>Create one with the form alongside, or from any company page or watchlist row. The server checks each alert on a schedule against quotes it can date, and records what it concluded.</p>
                  </div>
                ) : (
                  <div className="sys-scroll-x">
                    <table className="sys-table sys-table--compact alerts-table">
                      <thead>
                        <tr>
                          <th scope="col">Condition</th>
                          <th scope="col">State</th>
                          <th scope="col">Last result</th>
                          <th scope="col">Last checked</th>
                          <th scope="col">Last observation</th>
                          <th scope="col"><span className="visually-hidden">Actions</span></th>
                        </tr>
                      </thead>
                      <tbody>
                        {alerts.map((a) => <AlertRow key={a.id} a={a} act={act} onEdit={() => setEditing(a)} />)}
                      </tbody>
                    </table>
                  </div>
                )}
          </Panel>

          <Panel title="Notifications" subtitle={`${inbox.unread} unread`} actions={inbox.unread ? <button type="button" className="sys-btn sys-btn--xs" onClick={() => void markRead()}>Mark all read</button> : undefined}>
            {(inbox.status === 'idle' || inbox.status === 'loading') && !inbox.notifications.length ? (
              <StateBlock state="waking" title="Loading notifications" />
            ) : inbox.status === 'error' && !inbox.notifications.length ? (
              <StateBlock state="unavailable" title="Notifications could not be read" detail="Your alerts are unaffected; this is only the inbox." />
            ) : !inbox.notifications.length ? (
              <p className="alerts-empty">No alert has triggered yet. Notifications appear here when the server&apos;s evaluator records a trigger.</p>
            ) : (
              <ol className="inbox">
                {inbox.notifications.map((n) => (
                  <li key={n.id} data-read={n.read ? 'true' : undefined}>
                    <div className="inbox__head">
                      {!n.read ? <><span className="inbox__dot" aria-hidden /><span className="visually-hidden">Unread: </span></> : null}
                      <strong>{n.title}</strong>
                      <span className="sys-meta">{formatMoment(n.createdAt)}</span>
                    </div>
                    {n.body ? <p className="inbox__body">{n.body}</p> : null}
                    {n.event ? (
                      <p className="sys-meta">
                        {n.event.freshness ? `${FRESH[n.event.freshness] ?? n.event.freshness} data` : 'data'}
                        {n.event.source ? ` from ${n.event.source}` : ''}
                        {n.event.source_timestamp ? ` at ${formatMoment(n.event.source_timestamp)}` : ''}
                      </p>
                    ) : null}
                    <div className="inbox__acts">
                      {n.link ? <Link className="sys-btn sys-btn--xs" href={n.link}>Open</Link> : null}
                      {!n.read ? <button type="button" className="sys-btn sys-btn--xs" onClick={() => void markRead(n.id)}>Mark read</button> : null}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </Panel>
        </div>

        <aside className="alerts-side" aria-label="Create an alert">
          <Panel title="New alert" subtitle="checked by the server, not in this browser">
            <AlertEditor />
          </Panel>
        </aside>
      </div>

      <Drawer open={editing !== null} onClose={() => setEditing(null)} title={editing ? `Edit alert · ${editing.ticker}` : 'Edit alert'} meta="A changed condition starts again from the next evaluation">
        {editing ? <AlertEditor key={editing.id} editing={editing} /> : null}
      </Drawer>
    </div>
  )
}

export function AlertRow({ a, act, onEdit }: { a: PriceAlert; act: (fn: () => Promise<void>) => void; onEdit?: () => void }) {
  const [confirm, setConfirm] = useState(false)
  const skipped = (a.last_result ?? '').startsWith('skipped')
  return (
    <tr>
      <th scope="row">
        <span className="alerts-cond">
          <Link className="trk-sym__link" href={`/company/${encodeURIComponent(a.ticker)}`}>{a.ticker}</Link>
          <span>{a.condition.startsWith(`${a.ticker} `) ? a.condition.slice(a.ticker.length + 1) : a.condition}</span>
          {a.repeat ? <span className="sys-meta">repeats</span> : null}
        </span>
        {a.note ? <span className="trk-note">{a.note}</span> : null}
      </th>
      <td className="alerts-state"><Status state={a.status === 'active' ? 'live' : a.status === 'triggered' ? 'recorded' : 'blocked'} label={a.status.toUpperCase()} /></td>
      <td className={`alerts-result${skipped ? ' alerts-skip' : ''}`}>{describeResult(a)}</td>
      <td className="sys-meta alerts-checked" data-label="Checked:">{a.last_evaluated_at ? formatMoment(a.last_evaluated_at) : 'not yet evaluated'}</td>
      <td className="sys-meta alerts-obs" data-label="Observed:">
        {a.last_observed_value != null && a.kind !== 'new_filing' ? `${a.last_observed_value}${a.kind.endsWith('move') ? '%' : ''}` : ''}
        {a.last_source ? ` · ${a.last_source}` : ''}
      </td>
      <td className="trk-acts">
        {onEdit ? <button type="button" className="sys-btn sys-btn--xs" onClick={onEdit}>Edit</button> : null}
        {a.status === 'active' ? <button type="button" className="sys-btn sys-btn--xs" onClick={() => act(() => setAlertStatus(a.id, 'paused'))}>Pause</button> : null}
        {a.status !== 'active' ? <button type="button" className="sys-btn sys-btn--xs" onClick={() => act(() => setAlertStatus(a.id, 'active'))}>{a.status === 'triggered' ? 'Re-arm' : 'Resume'}</button> : null}
        {confirm ? (
          <>
            <button type="button" className="sys-btn sys-btn--xs sys-btn--danger" onClick={() => act(() => deleteAlert(a.id))}>Delete alert</button>
            <button type="button" className="sys-btn sys-btn--xs" onClick={() => setConfirm(false)}>Keep</button>
          </>
        ) : (
          <ActionMenu
            label={`More actions for the ${a.ticker} alert`}
            items={[
              { kind: 'link', label: `Open ${a.ticker}`, href: `/company/${encodeURIComponent(a.ticker)}` },
              { kind: 'separator' },
              { label: 'Delete alert…', onSelect: () => setConfirm(true), tone: 'danger' },
            ]}
          />
        )}
      </td>
    </tr>
  )
}
