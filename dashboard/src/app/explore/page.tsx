'use client'

import Workbench from '@/components/system/Workbench'
import ExploreBoard from '@/components/explore/ExploreBoard'
import { Panel, Prose } from '@/components/system'
import { useCapabilities } from '@/lib/capabilities'

export default function ExplorePage() {
  // Presentation only: the mode decides which company page a row links to and
  // how many rows are shown. Every ranking, and every verdict in it, is
  // identical in both modes because both read the same snapshot.
  const { caps } = useCapabilities()
  const mode = caps?.experience_mode === 'beginner' ? 'beginner' : 'advanced'

  return (
    <Workbench
      title="Explore"
      subtitle="ranked across the universe"
      rail={[{ label: 'Rankings', state: 'live', detail: 'cached snapshot' }]}
      context={
        <>
          <Panel title="What this answers">
            <Prose>
              Of the securities this system can currently score, which rank
              highest on one stated dimension — and what the model actually
              thinks of each of them.
            </Prose>
          </Panel>
          <Panel title="A rank is not a verdict">
            <Prose>
              Position here orders securities against each other. The model
              signal on each row is the separate question of what the engine
              concluded about that security on its own, and it is the same
              signal the research terminal returns.
            </Prose>
          </Panel>
          <Panel title="Trending is not buying">
            <Prose>
              The trending dimension measures movement and attention. A
              security falling hard on heavy coverage leads that list and may
              carry a Sell signal while it does. Both are shown together
              because both are true.
            </Prose>
          </Panel>
          <Panel title="Unknown is not good">
            <Prose>
              A security whose price is stale, whose evidence is too thin to
              score, or whose risk could not be measured is excluded rather
              than ranked. Otherwise the names we know least about sort to the
              top, because absent evidence cannot disagree with itself.
            </Prose>
          </Panel>
          <Panel title="Scope">
            <Prose>
              US-listed common equities. The macro gate underneath these scores
              is built from FRED, the Federal Funds rate, US CPI and the US
              yield curve, which are not global facts.
            </Prose>
          </Panel>
        </>
      }
    >
      <ExploreBoard mode={mode} />
    </Workbench>
  )
}
