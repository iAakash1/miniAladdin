'use client'

/**
 * A keyboard shortcut written for the keyboard in front of the reader.
 *
 * The palette answers to Meta+K and Control+K, but six places printed "⌘K",
 * the Mac symbol, to everyone — a Windows or Linux reader was told to press a
 * key their keyboard does not have. The server cannot know the platform, so it
 * renders the Mac form and a client that is not a Mac switches after mount.
 */

import { useSyncExternalStore, type ReactNode } from 'react'

const subscribe = () => () => undefined

function isApple(): boolean {
  const nav = navigator as Navigator & { userAgentData?: { platform?: string } }
  return /mac|iphone|ipad|ipod/i.test(nav.userAgentData?.platform ?? nav.platform ?? nav.userAgent ?? '')
}

export type Modifier = '⌘' | 'Ctrl'

/** The platform's command key: ⌘ on Apple hardware, Ctrl everywhere else. */
export function useModifier(): Modifier {
  return useSyncExternalStore<Modifier>(subscribe, () => (isApple() ? '⌘' : 'Ctrl'), () => '⌘')
}

/** "⌘K" on a Mac, "Ctrl K" elsewhere. Pure, so it can be tested without a browser. */
export function chord(modifier: Modifier, key: string): string {
  return modifier === '⌘' ? `⌘${key}` : `Ctrl ${key}`
}

export function Shortcut({ k }: { k: string }): ReactNode {
  return chord(useModifier(), k)
}
