import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import PaperWorkspace from '@/components/terminal/paper/PaperWorkspace'
import { Panel, Prose } from '@/components/system'

export const metadata: Metadata = {
  title: 'Paper — miniAladdin',
  description: 'A simulated account at Alpaca’s paper endpoint. No real money, no live execution.',
}

export default function PaperPage() {
  return (
    <Workbench
      title="Paper"
      subtitle="simulated account · alpaca paper"
      context={
        <>
          <Panel title="What this is">
            <Prose>
              A simulated brokerage account. Orders reach Alpaca&apos;s paper
              endpoint and settle nothing.
            </Prose>
          </Panel>
          <Panel title="Live trading is not available">
            <Prose size="tight">
              This build can only reach the paper endpoint. Pointing it at the
              live one is refused rather than ignored, so an environment
              configured for real execution fails to start instead of quietly
              trading paper — or worse, quietly trading.
            </Prose>
          </Panel>
          <Panel title="Where these figures come from">
            <Prose size="tight">
              Every number here was reported by the broker. Nothing is computed
              locally — no fill, no average price, no profit derived from a
              quote this product holds. An unfilled order has no fill price
              rather than a guessed one.
            </Prose>
          </Panel>
        </>
      }
    >
      <PaperWorkspace />
    </Workbench>
  )
}
