'use client'

/**
 * The official record around a company, beside its filings.
 *
 * Federal Register documents that name the registrant, and — only when EDGAR
 * classifies it as healthcare — FDA enforcement reports and the clinical
 * trials it leads. These are records to open and judge, not inputs: the
 * signal, confidence and risk above never read them, and the panel says so.
 *
 * Every section states how it ended. "No recalls on record" and "the recall
 * database did not answer" are different findings and never share a line.
 */

import { useEffect, useState } from 'react'

import { Panel, StateBlock } from '@/components/system'
import { readResource } from '@/lib/resource'

type SectionStatus = 'ok' | 'empty' | 'unavailable' | 'not_configured' | 'not_applicable'

interface FrDocument { id: string; title: string; type: string; published: string; agencies: string[]; url: string }
interface Recall { id: string; classification: string; status: string; reported: string; initiated: string | null; firm: string; product: string; reason: string }
interface Trial { id: string; title: string; phases: string[]; status: string; sponsor: string; started: string | null; updated: string | null; url: string }

interface Section { status: SectionStatus; provider?: string; reason?: string }
interface FederalSection extends Section { total?: number; routine_excluded?: number; documents?: FrDocument[] }
interface RecallSection extends Section { kind?: 'drug' | 'device'; firm?: string; total?: number; recalls?: Recall[] }
interface TrialSection extends Section { sponsor?: string; active_total?: number | null; phase3_active?: number | null; trials?: Trial[] }

interface RecordResponse {
  symbol: string
  status: 'ok' | 'unavailable'
  entity: { name: string; core_name: string; sic: string | null; sic_description: string | null; healthcare: boolean } | null
  sections: {
    federal_register?: FederalSection
    fda_drug_recalls?: RecallSection
    fda_device_recalls?: RecallSection
    clinical_trials?: TrialSection
  }
}

const PHASE: Record<string, string> = {
  EARLY_PHASE1: 'Early 1', PHASE1: 'Phase 1', PHASE2: 'Phase 2', PHASE3: 'Phase 3', PHASE4: 'Phase 4', NA: 'n/a',
}

function words(status: string): string {
  return status.toLowerCase().replace(/_/g, ' ')
}

function SourceMissing({ section, what }: { section: Section; what: string }) {
  if (section.status === 'not_configured') {
    return <p className="or-note">{what} is not configured on this deployment, so it was not asked. Nothing is shown in its place.</p>
  }
  return <p className="or-note">{what} did not answer this time. This is a missing reading, not an empty record.</p>
}

function Federal({ s, registrant }: { s: FederalSection; registrant: string }) {
  const docs = s.documents ?? []
  return (
    <div className="or-sec">
      <h3 className="or-sec__title">
        Federal Register
        <span>documents federal agencies published that name {registrant}</span>
      </h3>
      {s.status === 'ok' ? (
        <>
          <ol className="or-docs">
            {docs.map((d) => (
              <li key={d.id || d.url}>
                <a className="or-doc" href={d.url} target="_blank" rel="noopener noreferrer">
                  <time className="or-doc__date" dateTime={d.published}>{d.published}</time>
                  <span className="or-doc__body">
                    <span className="or-doc__meta">
                      <span className="or-chip">{d.type}</span>
                      {d.agencies.join(' · ')}
                    </span>
                    <span className="or-doc__title">{d.title}</span>
                  </span>
                </a>
              </li>
            ))}
          </ol>
          <p className="or-foot">
            {docs.length} most recent of {s.total ?? docs.length} matching documents
            {s.routine_excluded ? ` · ${s.routine_excluded} exchange rule filings that only cite the stock left out` : ''}
            {' · '}FederalRegister.gov
          </p>
        </>
      ) : s.status === 'empty' ? (
        <p className="or-note">No Federal Register document names {registrant}.</p>
      ) : (
        <SourceMissing section={s} what="The Federal Register" />
      )}
    </div>
  )
}

function Trials({ s, core }: { s: TrialSection; core: string }) {
  const active = s.active_total ?? null
  const late = s.phase3_active ?? null
  const share = active && late !== null ? Math.min(100, (late / active) * 100) : null
  return (
    <div className="or-sec">
      <h3 className="or-sec__title">
        Clinical trials
        <span>active studies {core} leads as sponsor · ClinicalTrials.gov</span>
      </h3>
      {s.status === 'ok' ? (
        <>
          <div className="or-figures">
            <div className="or-figure"><span className="or-figure__v sys-num">{active ?? '—'}</span><span className="or-figure__k">active studies</span></div>
            <div className="or-figure"><span className="or-figure__v sys-num">{late ?? '—'}</span><span className="or-figure__k">in Phase 3</span></div>
            {share !== null ? (
              <div className="or-share" role="img" aria-label={`${late} of ${active} active studies are in Phase 3`}>
                <span style={{ width: `${share}%` }} />
              </div>
            ) : null}
          </div>
          <ol className="or-docs">
            {(s.trials ?? []).map((t) => (
              <li key={t.id}>
                <a className="or-doc" href={t.url} target="_blank" rel="noopener noreferrer">
                  <span className="or-doc__date">{t.id}</span>
                  <span className="or-doc__body">
                    <span className="or-doc__meta">
                      {t.phases.length ? <span className="or-chip">{t.phases.map((p) => PHASE[p] ?? p).join(' / ')}</span> : null}
                      {words(t.status)}{t.updated ? ` · updated ${t.updated}` : ''}
                    </span>
                    <span className="or-doc__title">{t.title}</span>
                  </span>
                </a>
              </li>
            ))}
          </ol>
          <p className="or-foot">Most recently updated first. A study is attributed only when {core} is its lead sponsor.</p>
        </>
      ) : s.status === 'empty' ? (
        <p className="or-note">ClinicalTrials.gov lists no active study with {core} as lead sponsor. Subsidiaries that sponsor under their own name are not matched.</p>
      ) : (
        <SourceMissing section={s} what="ClinicalTrials.gov" />
      )}
    </div>
  )
}

function Recalls({ drug, device, core }: { drug: RecallSection; device: RecallSection; core: string }) {
  const answered = [drug, device].filter((s) => s.status === 'ok' || s.status === 'empty')
  const recalls = [...(drug.recalls ?? []), ...(device.recalls ?? [])]
    .sort((a, b) => b.reported.localeCompare(a.reported))
    .slice(0, 6)
  const missing = [drug, device].find((s) => s.status === 'unavailable' || s.status === 'not_configured')
  return (
    <div className="or-sec">
      <h3 className="or-sec__title">
        FDA enforcement reports
        <span>recalls where {core} is the recalling firm · openFDA</span>
      </h3>
      {answered.length ? (
        <div className="or-figures">
          {drug.status === 'ok' || drug.status === 'empty' ? (
            <div className="or-figure"><span className="or-figure__v sys-num">{drug.total ?? (drug.status === 'empty' ? 0 : '—')}</span><span className="or-figure__k">drug recalls on record</span></div>
          ) : null}
          {device.status === 'ok' || device.status === 'empty' ? (
            <div className="or-figure"><span className="or-figure__v sys-num">{device.total ?? (device.status === 'empty' ? 0 : '—')}</span><span className="or-figure__k">device recalls on record</span></div>
          ) : null}
        </div>
      ) : null}
      {recalls.length ? (
        <ol className="or-docs">
          {recalls.map((r) => (
            <li key={r.id}>
              <div className="or-doc or-doc--static">
                <time className="or-doc__date" dateTime={r.reported}>{r.reported}</time>
                <span className="or-doc__body">
                  <span className="or-doc__meta">
                    <span className="or-chip" data-class={r.classification.replace(/\s+/g, '').toLowerCase()}>{r.classification || 'unclassified'}</span>
                    {words(r.status)} · {r.id}
                  </span>
                  <span className="or-doc__title">{r.reason}</span>
                  <span className="or-doc__sub">{r.product}</span>
                </span>
              </div>
            </li>
          ))}
        </ol>
      ) : answered.length ? (
        <p className="or-note">No FDA enforcement report names {core} as the recalling firm.</p>
      ) : null}
      {missing ? <SourceMissing section={missing} what="openFDA" /> : null}
      {answered.length ? (
        <p className="or-foot">Class I is the most serious recall classification. openFDA data is published for research, not for medical decisions.</p>
      ) : null}
    </div>
  )
}

export default function OfficialRecord({ symbol }: { symbol: string }) {
  const [state, setState] = useState<{ for: string; d?: RecordResponse; failed?: boolean } | null>(null)

  useEffect(() => {
    let alive = true
    readResource<RecordResponse>(`/api/company/${encodeURIComponent(symbol)}/record`, 'artifact')
      .then((d) => { if (alive) setState({ for: symbol, d }) })
      .catch(() => { if (alive) setState({ for: symbol, failed: true }) })
    return () => { alive = false }
  }, [symbol])

  const current = state?.for === symbol ? state : null
  const d = current?.d
  const sections = d?.sections

  return (
    <Panel
      title="Official record"
      subtitle="agency documents, recalls and trials — context to read, never an input to the signal"
    >
      {!current ? (
        <StateBlock state="waking" title="Reading the official record" />
      ) : current.failed || !d || d.status !== 'ok' || !d.entity || !sections ? (
        <StateBlock
          state="unavailable"
          title="The official record could not be assembled"
          detail="EDGAR did not identify the registrant, and searching agency records by ticker alone would be a guess. Filings above are unaffected."
        />
      ) : (
        <div className="or-body">
          {sections.federal_register ? <Federal s={sections.federal_register} registrant={d.entity.name} /> : null}
          {d.entity.healthcare && sections.clinical_trials ? <Trials s={sections.clinical_trials} core={d.entity.core_name} /> : null}
          {d.entity.healthcare && sections.fda_drug_recalls && sections.fda_device_recalls ? (
            <Recalls drug={sections.fda_drug_recalls} device={sections.fda_device_recalls} core={d.entity.core_name} />
          ) : null}
          {!d.entity.healthcare ? (
            <p className="or-foot">
              FDA recalls and clinical trials are read only for registrants EDGAR classifies as healthcare;
              EDGAR lists {d.entity.name} under {d.entity.sic_description ?? `SIC ${d.entity.sic ?? 'unknown'}`}.
            </p>
          ) : null}
        </div>
      )}
    </Panel>
  )
}
