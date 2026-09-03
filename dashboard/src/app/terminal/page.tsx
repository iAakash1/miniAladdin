import { redirect } from 'next/navigation'

/**
 * The root terminal route.
 *
 * It used to render a market dashboard, which made it a second market
 * workspace with its own shell, navigation and keyboard context. Everything it
 * showed now lives on the Market workspace — the sector map and the "what
 * changed" diff were migrated there rather than dropped.
 *
 * What a reader reasonably expects on arriving at /terminal is the way in, not
 * one particular analysis. Command is that: the workspace that says what state
 * the research is in and what is worth looking at. So this redirects there
 * rather than picking a subject on the reader's behalf.
 *
 * Kept as a redirect rather than deleted because /terminal is a URL people
 * have typed and bookmarked for as long as the product has existed.
 */
export default function TerminalRoot() {
  redirect('/terminal/command')
}
