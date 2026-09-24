'use client'

import Link from 'next/link'
import { useSyncExternalStore } from 'react'

import Icon from '@/components/shell/Icon'
import ModeSwitch from '@/components/beginner/ModeSwitch'
import { destinationAt } from '@/lib/destinations'
import type { NavigationDefinition } from '@/lib/navigation'
import { emptySnapshot, recentSnapshot, subscribeSymbols } from '@/lib/symbols'

function isActive(pathname: string, href: string, terminal: boolean): boolean {
  if (terminal) return destinationAt(pathname)?.href === href
  return pathname === href || (href !== '/beginner' && href !== '/intermediate' && pathname.startsWith(`${href}/`))
}

export default function Rail({
  set, pathname, open, onNavigate,
}: {
  set: NavigationDefinition
  pathname: string
  open: boolean
  onNavigate: () => void
}) {
  const recent = useSyncExternalStore(subscribeSymbols, recentSnapshot, emptySnapshot)
  const terminal = set.home === '/terminal/command'
  const currentSymbol = pathname.startsWith('/company/')
    ? decodeURIComponent(pathname.split('/')[2] ?? '').toUpperCase()
    : null

  return (
    <nav className="shell-rail" data-open={open ? '' : undefined} aria-label="Primary">
      <div className="rail-scroll">
        {set.groups.map((group) => (
          <div className="rail-group" key={group.group}>
            <p className="rail-group__label">{group.group}</p>
            <ul className="rail-list">
              {group.items.map((item) => {
                const active = isActive(pathname, item.href, terminal)
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className="rail-link"
                      aria-current={active ? 'page' : undefined}
                      onClick={onNavigate}
                    >
                      <Icon name={item.icon} className="rail-link__icon" />
                      <span className="rail-link__label">{item.label}</span>
                      {item.key ? <kbd className="rail-link__key" aria-hidden>G {item.key.toUpperCase()}</kbd> : null}
                    </Link>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}

        {terminal ? (
          <div className="rail-group">
            <p className="rail-group__label">Recent companies</p>
            {recent.length ? (
              <ul className="rail-list">
                {recent.slice(0, 6).map((sym) => (
                  <li key={sym}>
                    <Link
                      href={`/company/${encodeURIComponent(sym)}`}
                      className="rail-link rail-link--symbol"
                      aria-current={currentSymbol === sym ? 'page' : undefined}
                      onClick={onNavigate}
                    >
                      <span className="rail-sym">{sym}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="rail-empty">Companies you open appear here.</p>
            )}
          </div>
        ) : (
          <div className="rail-group">
            <p className="rail-group__label">Detail level</p>
            <div className="rail-modes">
              {set.home !== '/beginner' ? <ModeSwitch to="beginner" compact /> : null}
              {set.home !== '/intermediate' ? <ModeSwitch to="intermediate" compact /> : null}
              <ModeSwitch to="advanced" compact />
            </div>
          </div>
        )}
      </div>

      <div className="rail-foot">
        <span><kbd>⌘K</kbd> search</span>
        <span><kbd>?</kbd> shortcuts</span>
      </div>
    </nav>
  )
}
