'use client'

/**
 * Trace: where a result came from, and where trust in it stopped.
 *
 * Two chains that are usually shown apart, joined into one because a reader
 * asking "should I believe this" needs both halves and gets neither from
 * either alone.
 *
 * The first half is lineage — vendor observation, point-in-time returns,
 * features, universe, model, backtest, attribution — each stage tagged with
 * what kind of claim it is. OBSERVED is something a vendor recorded. DERIVED is
 * arithmetic on it. MODEL_PREDICTED is a guess. A reader who cannot see which
 * is which cannot tell a measurement from an output.
 *
 * The second half is the gates: the thresholds a model has to clear to be
 * promoted, and which of them it did not.
 *
 * **The failure is the point.** A trace that draws only the happy path is a
 * diagram of an argument with its rebuttal removed. Once a gate is unmet the
 * chain is marked as stopped there and everything after it is drawn as NOT
 * REACHED — not as passed, and not as absent. A model that fails the deflated
 * Sharpe gate has not "not been promoted yet"; it has been stopped, at a
 * nameable place, for a stated reason.
 *
 * **An unmet gate and an unmeasured one are drawn differently.** "not recorded"
 * is its own outcome. Absent evidence is not passing evidence — but it is also
 * not a failed measurement, and the work each implies is different: one needs a
 * better model, the other needs a measurement.
 */

import { useEffect, useState } from 'react'

import { Panel, Prose, StateBlock, Status } from '@/components/system'

interface Stage {
  stage: string
  kind: 'OBSERVED' | 'DERIVED' | 'MODEL_PREDICTED' | string
  detail: string
  evidence?: unknown
}

interface Provenance {
  status: string
  chain?: Stage[]
  content_hash?: string
  dataset_version?: string
  git_commit?: string
}

interface RegistryEntry {
  model_id: string
  label: string
  status?: string
  eligible_for?: string[]
  candidate_thresholds_not_met?: Record<string, number | string>
  thresholds_not_met?: Record<string, number | string>
}

interface Registry {
  entries?: RegistryEntry[]
  promotion_gates?: Record<string, string[]>
}

type State =
  | { status: 'reading' }
  | { status: 'ready'; provenance: Provenance; entry: RegistryEntry | null; gates: Record<string, string[]> }
  | { status: 'unavailable'; detail: string }

/** What kind of claim a lineage stage makes. */
const KIND_STATE: Record<string, 'recorded' | 'candidate' | 'experimental'> = {
  OBSERVED: 'recorded',
  DERIVED: 'candidate',
  MODEL_PREDICTED: 'experimental',
}

const KIND_NOTE: Record<string, string> = {
  OBSERVED: 'A vendor recorded this. It is not our arithmetic.',
  DERIVED: 'Computed from what came before it. No new information enters here.',
  MODEL_PREDICTED: 'A model output. This is a guess, however well made.',
}

export function Trace({ label = 'fwd_rank_21', model = 'gradient_boosting' }: {
  label?: string
  model?: string
}) {
  const [state, setState] = useState<State>({ status: 'reading' })

  useEffect(() => {
    let alive = true
    Promise.all([
      fetch(`/api/ml/provenance/${encodeURIComponent(label)}/${encodeURIComponent(model)}`)
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`provenance returned ${r.status}`)))),
      fetch('/api/ml/registry')
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`the registry returned ${r.status}`)))),
    ])
      .then(([provenance, registry]: [Provenance, Registry]) => {
        if (!alive) return
        const entry = (registry.entries ?? []).find(
          (e) => e.model_id === model && e.label === label,
        ) ?? null
        setState({ status: 'ready', provenance, entry, gates: registry.promotion_gates ?? {} })
      })
      .catch((e: Error) => { if (alive) setState({ status: 'unavailable', detail: e.message }) })
    return () => { alive = false }
  }, [label, model])

  if (state.status === 'reading') {
    return <Panel title="Trace" state="waking"><StateBlock state="waking" title="Reading the chain" /></Panel>
  }
  if (state.status === 'unavailable') {
    return (
      <Panel title="Trace" state="unavailable">
        <StateBlock
          state="unavailable"
          title="The chain could not be read"
          detail={`${state.detail}. No partial chain is drawn: a lineage missing a stage looks like a lineage that skipped one.`}
        />
      </Panel>
    )
  }

  const chain = state.provenance.chain ?? []
  const unmet = {
    ...(state.entry?.candidate_thresholds_not_met ?? {}),
    ...(state.entry?.thresholds_not_met ?? {}),
  }
  // Measured failures first. A number that missed is the concrete finding; a
  // gate that was never measured is a gap in the record, and burying the first
  // under six of the second is how the actionable line gets skipped.
  const unmetNames = Object.keys(unmet).sort((a, b) => {
    const am = typeof unmet[a] === 'number' ? 0 : 1
    const bm = typeof unmet[b] === 'number' ? 0 : 1
    return am - bm
  })
  const stopped = unmetNames.length > 0
  const unmeasured = unmetNames.filter((g) => typeof unmet[g] !== 'number')

  return (
    <>
      <Panel
        title="Trace"
        subtitle={`${label} · ${model}`}
        state={stopped ? 'blocked' : 'recorded'}
        badge={stopped ? `STOPPED AT ${unmetNames.length} GATE${unmetNames.length === 1 ? '' : 'S'}` : 'NO GATE UNMET'}
        badgeTone={stopped ? 'fail' : 'pass'}
        source={state.provenance.dataset_version}
        asOf={state.provenance.content_hash ? `hash ${state.provenance.content_hash.slice(0, 12)}` : undefined}
      >
        <Prose>
          Where this result came from, and where trust in it stopped. The chain
          runs from what a vendor recorded through to a promotion decision, and
          each link says which kind of claim it is making.
        </Prose>

        {chain.length === 0 ? (
          <StateBlock
            state="unavailable"
            title="No lineage is recorded for this model"
            detail="The provenance endpoint answered and named no stages. A model with no recorded lineage cannot be traced, which is a fact about the record rather than about this page."
          />
        ) : (
          <ol className="sys-trace">
            {chain.map((s) => (
              <li key={s.stage} className="sys-trace__step" data-kind={s.kind}>
                <div className="sys-trace__head">
                  <span className="sys-trace__name">{s.stage.replace(/_/g, ' ')}</span>
                  <Status state={KIND_STATE[s.kind] ?? 'unknown'} label={s.kind.replace(/_/g, ' ')} />
                </div>
                <p className="sys-trace__detail">{s.detail}</p>
                {KIND_NOTE[s.kind] ? (
                  <p className="sys-trace__kindnote">{KIND_NOTE[s.kind]}</p>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </Panel>

      <Panel
        title="Where trust stopped"
        state={stopped ? 'blocked' : 'recorded'}
      >
        {!state.entry ? (
          <StateBlock
            state="unavailable"
            title="This model is not in the registry"
            detail="Without a registry entry there are no recorded gate outcomes, so none are shown. It is not being described as passing."
          />
        ) : stopped ? (
          <>
            <ol className="sys-trace sys-trace--gates">
              {unmetNames.map((gate) => {
                const value = unmet[gate]
                const measured = typeof value === 'number'
                return (
                  <li key={gate} className="sys-trace__step" data-outcome={measured ? 'failed' : 'unmeasured'}>
                    <div className="sys-trace__head">
                      <span className="sys-trace__name sys-mono">{gate.replace(/_/g, ' ')}</span>
                      <Status
                        state={measured ? 'blocked' : 'unavailable'}
                        label={measured ? 'FAILED' : 'NOT RECORDED'}
                      />
                    </div>
                    {/* Only a measured failure carries a line of its own. The
                        unmeasured ones share one explanation below, because
                        seven copies of the same sentence is a paragraph a
                        reader stops seeing. */}
                    {measured ? (
                      <p className="sys-trace__detail">
                        Observed <span className="sys-mono">{value}</span>, which does not meet the threshold.
                      </p>
                    ) : null}
                  </li>
                )
              })}
              <li className="sys-trace__step" data-outcome="unreached">
                <div className="sys-trace__head">
                  <span className="sys-trace__name">promotion</span>
                  <Status state="blocked" label="NOT REACHED" />
                </div>
                <p className="sys-trace__detail">
                  The chain stopped above. This is not a decision still pending —
                  it is a decision that cannot be taken while a gate is unmet.
                </p>
              </li>
            </ol>
            {unmeasured.length ? (
              <Prose caution>
                {unmeasured.length === 1 ? 'One gate was' : `${unmeasured.length} gates were`}{' '}
                never measured. Absent evidence is not passing evidence, so
                {unmeasured.length === 1 ? ' it stays' : ' they stay'} unmet — but
                {unmeasured.length === 1 ? ' it needs' : ' they need'} a
                measurement rather than a better model, and treating an unmeasured
                gate as passed is how an unmeasured model reaches production.
              </Prose>
            ) : null}
            <Prose caution>
              A measured failure and an unrecorded one both leave a gate unmet,
              and they call for opposite work. The first needs a better model.
              The second needs somebody to run the measurement.
            </Prose>
          </>
        ) : (
          <StateBlock
            state="recorded"
            title="No gate is recorded as unmet"
            detail={`Eligible for: ${state.entry.eligible_for?.join(', ') || 'nothing recorded'}. Clearing the gates is not promotion; promotion is a separate, deliberate act.`}
          />
        )}
      </Panel>
    </>
  )
}
