'use client'

import { UserButton } from '@clerk/nextjs'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'

import Icon from '@/components/shell/Icon'
import { openPalette } from '@/components/system/Palette'
import { LogoMark } from '@/components/ui/Logo'
import ThemeToggle from '@/components/ui/ThemeToggle'
import { experienceHome, setExperienceMode, type ExperienceMode } from '@/lib/capabilities'
import { NAVIGATION, type NavigationSet } from '@/lib/navigation'

const MODE_FOR: Record<NavigationSet, ExperienceMode> = {
  terminal: 'advanced',
  intermediate: 'intermediate',
  beginner: 'beginner',
}

/** Detail level is an account preference; it is saved before navigating. */
function DetailLevel({ navigation }: { navigation: NavigationSet }) {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)

  return (
    <label className="shell-detail" title={failed ? 'The preference could not be saved' : 'How much of the analysis is shown'}>
      <span className="visually-hidden">Detail level</span>
      <select
        className="shell-detail__select"
        value={MODE_FOR[navigation]}
        disabled={busy}
        onChange={async (e) => {
          const mode = e.target.value as ExperienceMode
          setBusy(true)
          setFailed(false)
          const ok = await setExperienceMode(mode)
          setBusy(false)
          if (ok) router.push(experienceHome(mode))
          else setFailed(true)
        }}
      >
        <option value="advanced">Full terminal</option>
        <option value="intermediate">Intermediate</option>
        <option value="beginner">Simple</option>
      </select>
    </label>
  )
}

export default function TopBar({
  navigation, section, location, onMenu, navOpen,
}: {
  navigation: NavigationSet
  section: string | null
  location: string
  onMenu: () => void
  navOpen: boolean
}) {
  const set = NAVIGATION[navigation]

  return (
    <header className="shell-top">
      <button
        type="button"
        className="shell-top__menu sys-btn sys-btn--icon"
        onClick={onMenu}
        aria-expanded={navOpen}
        aria-label={navOpen ? 'Close navigation' : 'Open navigation'}
      >
        <Icon name={navOpen ? 'close' : 'menu'} />
      </button>

      <Link href={set.home} className="shell-brand" aria-label="OmniSignal home">
        <LogoMark size={18} />
        <span className="shell-brand__name">OmniSignal</span>
      </Link>

      <nav className="shell-loc" aria-label="Location">
        {section ? <span className="shell-loc__section">{section}</span> : null}
        {section ? <Icon name="chevronRight" size={12} className="shell-loc__sep" /> : null}
        <span className="shell-loc__page" aria-current="page">{location}</span>
      </nav>

      <button type="button" className="shell-search" onClick={() => openPalette()} aria-label="Search companies, tickers and commands">
        <Icon name="search" size={14} />
        <span className="shell-search__text">Search companies, tickers, themes, commands</span>
        <kbd className="shell-search__kbd">⌘K</kbd>
      </button>

      <div className="shell-top__end">
        <DetailLevel navigation={navigation} />
        <ThemeToggle />
        <div className="shell-account">
          <UserButton appearance={{ elements: { avatarBox: { width: 24, height: 24 } } }} />
        </div>
      </div>
    </header>
  )
}
