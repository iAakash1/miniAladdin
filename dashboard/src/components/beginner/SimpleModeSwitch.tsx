'use client'

/**
 * Routes from the Advanced terminal to the two lower-density experiences.
 *
 * Persisted before navigating, so the choice survives the next visit rather
 * than lasting until the tab closes. A failed write does not navigate: landing
 * in a mode the server did not record silently reverts on reload, which reads
 * as the product ignoring you.
 */

import ModeSwitch from '@/components/beginner/ModeSwitch'

export default function SimpleModeSwitch() {
  return (
    <>
      <ModeSwitch to="beginner" compact />
      <ModeSwitch to="intermediate" compact />
    </>
  )
}
