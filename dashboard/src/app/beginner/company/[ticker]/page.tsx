'use client'

import { use } from 'react'

import Workbench from '@/components/system/Workbench'
import BeginnerAnalysis from '@/components/beginner/BeginnerAnalysis'
import ModeSwitch from '@/components/beginner/ModeSwitch'
import { Panel, Prose } from '@/components/system'

export default function BeginnerCompanyPage(
  { params }: { params: Promise<{ ticker: string }> },
) {
  const { ticker } = use(params)
  const symbol = decodeURIComponent(ticker).toUpperCase()

  return (
    <Workbench
      title={symbol}
      subtitle="plain-language analysis"
      rail={[{ label: 'Beginner', state: 'live', detail: 'same engine' }]}
      context={
        <>
          <Panel title="Same conclusion, less density">
            <Prose>
              This page reads the same research endpoint the full terminal
              uses. The signal, the confidence and the risk are identical —
              advanced mode shows the factor attribution and provenance behind
              them.
            </Prose>
            <ModeSwitch to="advanced" />
          </Panel>
          <Panel title="What a signal is">
            <Prose>
              A model output about a security under a stated method, not advice
              about your money and not a forecast of a price.
            </Prose>
          </Panel>
        </>
      }
    >
      <BeginnerAnalysis ticker={symbol} />
    </Workbench>
  )
}
