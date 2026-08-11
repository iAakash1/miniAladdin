/**
 * WorkBoot — the loading state for work that is *fast but not instant*.
 *
 * The product has exactly two honest loading languages, and this is the
 * short one:
 *
 *   ResearchLoader  work measured in tens of seconds. Names the real
 *                   pipeline stages, ticks only what the backend confirms.
 *   WorkBoot        work measured in ~1-4 seconds. Names the operation and
 *                   nothing else, because there is nothing else that could
 *                   be said truthfully in that window.
 *
 * The distinction matters. Validation's walk-forward measures ~1s warm; a
 * five-stage pipeline display for a one-second job would flash through five
 * states nobody can read, and would imply progress the code never observed.
 * That is the same lie ResearchLoader was built to avoid, just faster. So
 * this component makes no progress claim at all — three bars that say
 * "working", the operation's name, and what it is fetching.
 *
 * It is also deliberately *not* a stack of grey skeleton blocks. A skeleton
 * is a promise about layout, and it only pays off when the real layout
 * arrives in the same shape; for a result whose height depends entirely on
 * how much history a ticker has, the promise is usually wrong, and a wrong
 * skeleton reads as a broken page. Naming the operation is honest at any
 * result size.
 *
 * Motion is three bars on a 1.5s cycle and nothing else, disabled under
 * `prefers-reduced-motion` (the bars hold at rest opacity, so the component
 * still reads as "in progress" without moving).
 */
export default function WorkBoot({
  label,
  hint,
  compact = false,
}: {
  /** The operation, present participle: "Loading market data". */
  label: string
  /** What it is actually fetching or computing. One short clause. */
  hint?: string
  /** Sit inside a section that already has a header, rather than owning the
   *  viewport. Halves the reserved height so the page does not jump. */
  compact?: boolean
}) {
  return (
    <div className={`boot${compact ? ' boot--compact' : ''}`} role="status" aria-live="polite">
      <span className="boot__mark" aria-hidden>
        <span className="boot__bar" />
        <span className="boot__bar" />
        <span className="boot__bar" />
      </span>
      <span className="boot__label">{label}</span>
      {hint && <span className="boot__hint">{hint}</span>}
    </div>
  )
}
