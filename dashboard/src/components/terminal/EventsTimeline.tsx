import { eventsWithBuckets, type EventRow } from '@/lib/dashboardInsights'

/**
 * Upcoming macro events as a timeline instead of a flat list — grouped
 * under Today / Tomorrow / This week / Later, each row carrying an
 * importance badge and a countdown. Only ever shows event types the
 * backend actually returns (FOMC, CPI, PPI, Jobs Report from the public
 * BLS/FOMC calendars) — there is no free earnings-calendar source, so
 * "Earnings" from the mock-up is intentionally absent rather than
 * fabricated, matching this codebase's existing "omitted, not invented"
 * convention (see dashboard_service.py's ISM/PMI note).
 */
export default function EventsTimeline({ events }: { events: EventRow[] }) {
  if (events.length === 0) return null

  const rows = eventsWithBuckets(events)

  return (
    <section aria-labelledby="events-h" className="card dash-events">
      <span id="events-h" className="h-panel" style={{ fontSize: '0.9375rem', marginBottom: 14, display: 'block' }}>
        Upcoming events
      </span>
      <ol className="events-timeline">
        {rows.map(({ event, bucket, showBucket }) => {
          return (
            <li key={`${event.date}-${event.type}`} className="events-timeline__row">
              {showBucket && <span className="events-timeline__bucket label">{bucket}</span>}
              <div className="events-timeline__item">
                <span className={`badge ${event.importance === 'high' ? 'badge--warn' : 'badge--neutral'}`}>
                  {event.type}
                </span>
                <span style={{ fontSize: '0.8125rem', flex: 1, minWidth: 160 }}>{event.title}</span>
                {event.historical_move !== null && (
                  <span className="num" title={event.explain} style={{ fontSize: '0.6875rem', color: 'var(--muted)' }}>
                    ±{event.historical_move}% typical
                  </span>
                )}
                <span
                  className="num events-timeline__countdown"
                  data-soon={event.days_away <= 3 ? 'true' : undefined}
                >
                  {event.days_away === 0 ? 'today' : event.days_away === 1 ? 'tomorrow' : `${event.date} · in ${event.days_away}d`}
                </span>
              </div>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
