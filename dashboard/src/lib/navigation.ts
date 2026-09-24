/**
 * The three navigation sets the shell can render.
 *
 * The full terminal reads the destination registry. Simple and Intermediate
 * are the same product at lower detail, so they get a shorter rail inside the
 * same shell rather than a shell of their own.
 */

import type { IconName } from '@/components/shell/Icon'
import { DESTINATIONS, groupOf } from '@/lib/destinations'

export type NavigationSet = 'terminal' | 'beginner' | 'intermediate'

export interface NavItem {
  href: string
  label: string
  icon: IconName
  /** Chord letter, shown in the rail as a hint. */
  key?: string
}

export interface NavGroup {
  group: string
  items: NavItem[]
}

export interface NavigationDefinition {
  label: string
  home: string
  groups: NavGroup[]
  /** The section name shown in the top bar for a route. */
  sectionFor: (pathname: string) => string | null
}

const terminal: NavigationDefinition = {
  label: 'Research terminal',
  home: '/terminal/command',
  groups: DESTINATIONS.map((g) => ({
    group: g.group,
    items: g.items.map((d) => ({ href: d.href, label: d.label, icon: d.icon, key: d.key })),
  })),
  sectionFor: (pathname) => {
    if (pathname.startsWith('/company/') || pathname.startsWith('/evidence/')) return 'Research'
    return groupOf(pathname)
  },
}

const beginner: NavigationDefinition = {
  label: 'Simple',
  home: '/beginner',
  groups: [
    {
      group: 'Simple',
      items: [
        { href: '/beginner', label: 'Home', icon: 'home' },
        { href: '/explore', label: 'Explore', icon: 'screen' },
        { href: '/beginner/watchlist', label: 'Watchlist', icon: 'list' },
        { href: '/beginner/portfolio', label: 'Portfolio', icon: 'paper' },
        { href: '/learn', label: 'Learn', icon: 'book' },
      ],
    },
  ],
  sectionFor: () => 'Simple',
}

const intermediate: NavigationDefinition = {
  label: 'Intermediate',
  home: '/intermediate',
  groups: [
    {
      group: 'Intermediate',
      items: [
        { href: '/intermediate', label: 'Home', icon: 'home' },
        { href: '/explore', label: 'Explore', icon: 'screen' },
        { href: '/intermediate/watchlist', label: 'Watchlist', icon: 'list' },
        { href: '/intermediate/portfolio', label: 'Portfolio', icon: 'paper' },
        { href: '/intermediate/compare', label: 'Compare', icon: 'factor' },
        { href: '/learn', label: 'Learn', icon: 'book' },
      ],
    },
  ],
  sectionFor: () => 'Intermediate',
}

export const NAVIGATION: Record<NavigationSet, NavigationDefinition> = {
  terminal,
  beginner,
  intermediate,
}
