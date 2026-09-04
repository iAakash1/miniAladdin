import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import ModelCompare from '@/components/terminal/compare/ModelCompare'
import SecurityCompare from '@/components/terminal/compare/SecurityCompare'
import { Panel, Prose } from '@/components/system'

export const metadata: Metadata = {
  title: 'Compare — miniAladdin',
  description: 'Two securities side by side, or two models from the research archive.',
}

/* Two comparisons live at this route and they are not the same product.

   Comparing two companies is the thing a reader arrives wanting. Comparing
   two models is research: it belongs to the archive, it is about the
   programme rather than about any security, and no model here is deployed.

   The page used to render both at once under one set of context panels
   written entirely about models — so a reader who came to put Costco next to
   Walmart got a rail explaining turnover multiples and n/c cells, neither of
   which the security comparison uses, and a hundred-and-three-row model
   leaderboard underneath the answer they asked for. */

function SecurityContext() {
  return (
    <>
      <Panel title="What this answers">
        <Prose>How two companies differ, measure by measure, on figures that mean the same thing on both sides.</Prose>
      </Panel>
      <Panel title="Where the figures come from">
        <Prose size="tight">
          Vendor fundamentals, read fresh for each company and shared with
          their security pages. No model scores either side: nothing in the
          research programme is deployed, and a comparison is not a view.
        </Prose>
      </Panel>
      <Panel title="Reading a difference">
        <Prose size="tight">
          A difference in a percentage is percentage points; a difference
          between two multiples is a ratio. Colour appears only where the
          measure declares which direction is better — a lower price-to-earnings
          is the cheaper one, a lower current ratio is the weaker one.
        </Prose>
      </Panel>
    </>
  )
}

function ModelContext() {
  return (
    <>
      <Panel title="What this answers">
        <Prose>How two or more models differ, field by field, against a baseline.</Prose>
      </Panel>
      <Panel title="Why most deltas are grey">
        <Prose size="tight">
          A difference is coloured only where the metric declares a direction.
          Turnover of 18× is not worse than 6× without knowing the strategy,
          and colouring it red would be an opinion dressed as a measurement.
        </Prose>
      </Panel>
      <Panel title="Not comparable">
        <Prose size="tight">
          Where one side did not record a field, the cell says n/c. An absent
          value is not a match and not a zero: a model with no deflated Sharpe
          has not tied one that recorded a failing value.
        </Prose>
      </Panel>
    </>
  )
}

export default async function ComparePage({
  searchParams,
}: {
  searchParams: Promise<{ a?: string; b?: string }>
}) {
  const params = await searchParams
  const a = (params.a ?? '').toUpperCase()
  const b = (params.b ?? '').toUpperCase()
  const securities = Boolean(a && b)

  return (
    <Workbench
      title="Compare"
      subtitle={securities ? `${a} against ${b}` : 'model against model'}
      context={securities ? <SecurityContext /> : <ModelContext />}
    >
      {securities ? (
        <>
          <SecurityCompare a={a} b={b} />
          <Panel title="Comparing models instead">
            <Prose size="tight">
              The research archive holds a model comparison over the same
              fields for all registered models.{' '}
              <a href="/terminal/compare">Open it</a> — it is about the
              research programme, not about {a} or {b}.
            </Prose>
          </Panel>
        </>
      ) : (
        <ModelCompare />
      )}
    </Workbench>
  )
}
