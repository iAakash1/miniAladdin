/**
 * Section tracking inside the workspace scroll container.
 *
 * The workspace (#workspace), not the window, is what scrolls in this shell.
 * Every measurement here is relative to that container: a section's top is
 * its distance below the container's visible top edge.
 */

/**
 * Which section the reader is in: the last one whose top has crossed the
 * reading line. Deliberately not "the most visible section" — a 900px
 * section would otherwise keep the highlight long after the reader moved on.
 */
export function currentSectionId(
  tops: Array<{ id: string; top: number }>, line: number,
): string | null {
  if (tops.length === 0) return null
  let best = tops[0].id
  for (const entry of tops) {
    if (entry.top <= line) best = entry.id
  }
  return best
}

/** Where to scroll a container so `target` sits `offset` px below its top. */
export function scrollTargetFor(
  containerScrollTop: number, containerTop: number, targetTop: number, offset: number,
): number {
  return Math.max(0, containerScrollTop + (targetTop - containerTop) - offset)
}

export function workspaceRoot(): HTMLElement | null {
  return typeof document === 'undefined' ? null : document.getElementById('workspace')
}

/**
 * Scroll the workspace to a section, honouring reduced motion. Returns the
 * scroll position it will settle at — clamped, because a short section near
 * the end cannot be brought up to the reading line.
 */
export function scrollToSection(id: string, offset: number): number | null {
  const root = workspaceRoot()
  const el = document.getElementById(id)
  if (!root || !el) return null
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const wanted = scrollTargetFor(root.scrollTop, root.getBoundingClientRect().top, el.getBoundingClientRect().top, offset)
  const top = Math.min(wanted, Math.max(0, root.scrollHeight - root.clientHeight))
  root.scrollTo({ top, behavior: reduce ? 'auto' : 'smooth' })
  return top
}

/**
 * A section the reader chose, held as current until the scroll that took them
 * there has settled — so a short section is not immediately handed to its
 * neighbour, and a smooth scroll does not flicker through everything between.
 */
export function pinnedSection(
  pin: { id: string; target: number; until: number } | null, scrollTop: number, now: number,
): string | null {
  if (!pin) return null
  return now < pin.until || Math.abs(scrollTop - pin.target) < 6 ? pin.id : null
}
