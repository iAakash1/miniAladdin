'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

import SecurityCompare from '@/components/terminal/compare/SecurityCompare'
import { Panel, Prose } from '@/components/system'

export default function ExperienceCompare({
  a: initialA,
  b: initialB,
  mode,
}: {
  a: string
  b: string
  mode: 'beginner' | 'intermediate'
}) {
  const router = useRouter()
  const [a, setA] = useState(initialA)
  const [b, setB] = useState(initialB)

  function compare(event: React.FormEvent) {
    event.preventDefault()
    const left = a.trim().toUpperCase()
    const right = b.trim().toUpperCase()
    if (left && right && left !== right) {
      router.push(`/${mode}/compare?a=${encodeURIComponent(left)}&b=${encodeURIComponent(right)}`)
    }
  }

  return (
    <>
      <Panel title="Choose two companies">
        <Prose>The comparison uses the same vendor ratios and filed facts as each company page.</Prose>
        <form onSubmit={compare} className="bg__search">
          <label htmlFor="compare-a" className="visually-hidden">First ticker</label>
          <input id="compare-a" value={a} onChange={(event) => setA(event.target.value)} placeholder="AAPL" />
          <label htmlFor="compare-b" className="visually-hidden">Second ticker</label>
          <input id="compare-b" value={b} onChange={(event) => setB(event.target.value)} placeholder="MSFT" />
          <button type="submit">Compare</button>
        </form>
      </Panel>
      {initialA && initialB ? <SecurityCompare a={initialA} b={initialB} /> : null}
    </>
  )
}
