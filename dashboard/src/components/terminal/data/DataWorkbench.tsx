/**
 * Data & Provenance workbench.
 *
 * This surface is new, but almost none of what it shows is. `/api/ml/features`
 * and `/api/ml/datasets` have been serving a complete point-in-time contract —
 * 27 features with their lookback, availability lag and PIT safety; 19 datasets
 * with their survivorship and ingestion classification — and nothing in the
 * product had ever called them.
 *
 * That is the gap this workspace closes. The product's claim is that it will
 * tell you how much a number can be trusted; the evidence for that claim was
 * being computed and thrown away.
 *
 * Nothing here is derived, aggregated or scored. Every field is passed through
 * from the contract the backend already publishes.
 */
'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'

import {
  Panel, Provenance, Section, StateBlock, Status, Strip, Value,
  type ResearchState,
} from '@/components/system'
import { DataTable, type DataColumn } from '@/components/system/DataTable'
import { ObjectHeader, StripSkeleton, TableSkeleton, Toolbar, ToolbarGroup, ToolbarSpacer } from '@/components/system/composition'
import { Histogram } from '@/components/system/charts'
import { recordVisit } from '@/lib/research/history'
import Inspector, { type InspectorSection } from '@/components/system/Inspector'
import type { ResearchObject } from '@/lib/research/objects'

interface Feature {
  name: string
  group: string
  description: string
  rationale?: string
  formula?: string
  lookback_sessions: number | null
  availability_lag_sessions: number | null
  point_in_time_safe: boolean
  cross_sectional?: boolean
  direction?: string
  required_columns?: string[]
}

interface Dataset {
  dataset_id: string
  source: string
  repository?: string
  table?: string
  description?: string
  point_in_time: string
  point_in_time_note?: string
  survivorship: string
  survivorship_note?: string
  ingestion?: string
  columns?: string[]
}

interface FeatureCatalog {
  features: Feature[]
  feature_count: number
  labels: unknown[]
  unsafe_features: Feature[]
  max_lookback_sessions: number | null
}

interface DatasetCatalog {
  datasets: Dataset[]
  total: number
  training_admissible: number
  excluded: Dataset[]
  gated: Dataset[]
}

type Tab = 'datasets' | 'features'

/** A dataset's PIT classification maps onto the product's trust vocabulary. */
function pitState(value: string): ResearchState {
  const v = (value || '').toLowerCase()
  if (v.includes('point_in_time') || v === 'true' || v.includes('pit')) return 'recorded'
  if (v.includes('gated') || v.includes('restricted')) return 'blocked'
  if (v.includes('unknown')) return 'unknown'
  return 'stale'
}

export default function DataWorkbench() {
  const [features, setFeatures] = useState<FeatureCatalog | null>(null)
  const [datasets, setDatasets] = useState<DatasetCatalog | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('datasets')
  const [selected, setSelected] = useState<string | null>(null)
  // The inspector opens over the workspace rather than navigating away, so
  // following a reference does not cost the reader the table they were reading.
  const [inspecting, setInspecting] = useState<ResearchObject | null>(null)

  useEffect(() => {
    let alive = true
    Promise.all([
      fetch('/api/ml/features').then((r) => (r.ok ? r.json() : Promise.reject(new Error(`features ${r.status}`)))),
      fetch('/api/ml/datasets').then((r) => (r.ok ? r.json() : Promise.reject(new Error(`datasets ${r.status}`)))),
    ])
      .then(([f, d]) => { if (alive) { setFeatures(f); setDatasets(d) } })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [])

  const datasetColumns: DataColumn<Dataset>[] = useMemo(() => [
    { key: 'id', header: 'Dataset', width: '22%', sort: (d) => d.dataset_id, text: (d) => d.dataset_id, render: (d) => <span style={{ fontFamily: 'var(--font-mono)' }}>{d.dataset_id}</span> },
    { key: 'source', header: 'Source', width: '14%', sort: (d) => d.source, text: (d) => d.source, render: (d) => d.source },
    {
      key: 'pit', header: 'Point in time', width: '16%', sort: (d) => d.point_in_time, text: (d) => d.point_in_time,
      render: (d) => <Status state={pitState(d.point_in_time)} label={d.point_in_time} />,
    },
    {
      key: 'surv', header: 'Survivorship', width: '16%', sort: (d) => d.survivorship, text: (d) => d.survivorship,
      render: (d) => <span className="sys-meta" style={{ color: 'var(--ink)' }}>{d.survivorship}</span>,
    },
    { key: 'ingest', header: 'Ingestion', width: '14%', sort: (d) => d.ingestion ?? null, text: (d) => d.ingestion ?? '', render: (d) => <span className="sys-meta" style={{ color: 'var(--ink)' }}>{d.ingestion ?? '—'}</span> },
    { key: 'cols', header: 'Columns', unit: 'count', numeric: true, sort: (d) => d.columns?.length ?? null, render: (d) => <Value value={d.columns?.length ?? null} digits={0} /> },
  ], [])

  const featureColumns: DataColumn<Feature>[] = useMemo(() => [
    { key: 'name', header: 'Feature', width: '22%', sort: (f) => f.name, text: (f) => `${f.name} ${f.description}`, render: (f) => <span style={{ fontFamily: 'var(--font-mono)' }}>{f.name}</span> },
    { key: 'group', header: 'Group', width: '14%', sort: (f) => f.group, text: (f) => f.group, render: (f) => f.group },
    {
      key: 'pit', header: 'PIT safe', width: '12%', sort: (f) => (f.point_in_time_safe ? 1 : 0),
      render: (f) => <Status state={f.point_in_time_safe ? 'recorded' : 'blocked'} label={f.point_in_time_safe ? 'safe' : 'unsafe'} />,
    },
    {
      key: 'lookback', header: 'Lookback', unit: 'sessions', numeric: true, sort: (f) => f.lookback_sessions,
      render: (f) => <Value value={f.lookback_sessions} digits={0} title="Sessions of history the feature reads" />,
    },
    {
      key: 'lag', header: 'Availability lag', unit: 'sessions', numeric: true, sort: (f) => f.availability_lag_sessions,
      render: (f) => <Value value={f.availability_lag_sessions} digits={0} title="Sessions between the observation and the moment it could be known" />,
    },
    {
      key: 'xs', header: 'Cross-sectional', width: '12%', sort: (f) => (f.cross_sectional ? 1 : 0),
      render: (f) => <span className="sys-meta" style={{ color: 'var(--ink)' }}>{f.cross_sectional ? 'yes' : 'no'}</span>,
    },
    {
      key: 'dir', header: 'Direction', width: '12%', optional: true, sort: (f) => f.direction ?? null,
      render: (f) => <span className="sys-meta" style={{ color: 'var(--ink)' }}>{f.direction ?? '—'}</span>,
    },
  ], [])

  if (error) {
    return (
      <Panel title="Data catalogue" state="unavailable">
        <StateBlock
          state="unavailable"
          title="The catalogue could not be read"
          detail={`The request failed with: ${error}. No values are shown in its place, because a data contract that cannot be read is not a data contract that is empty.`}
        />
      </Panel>
    )
  }

  if (!features || !datasets) {
    return (
      <>
        <StripSkeleton items={7} />
        <Panel title="Catalogue" state="waking" flush><TableSkeleton rows={10} columns={6} /></Panel>
      </>
    )
  }

  const selectedDataset = datasets.datasets.find((d) => d.dataset_id === selected)
  const selectedFeature = features.features.find((f) => f.name === selected)

  const inspectorSections = (): InspectorSection[] => {
    if (inspecting?.kind === 'dataset') {
      const d = datasets.datasets.find((x) => x.dataset_id === inspecting.id)
      if (!d) return []
      return [
        {
          title: 'Contract',
          fields: [
            { label: 'Source', value: d.source },
            { label: 'Repository', value: d.repository ?? '—' },
            { label: 'Table', value: d.table ?? '—' },
            { label: 'Point in time', value: d.point_in_time, title: d.point_in_time_note },
            { label: 'Survivorship', value: d.survivorship, title: d.survivorship_note },
            { label: 'Ingestion', value: d.ingestion ?? '—' },
            { label: 'Columns', value: String(d.columns?.length ?? '—') },
          ],
        },
        {
          title: 'Notes',
          body: (
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              {d.description ?? 'No description recorded.'}
            </p>
          ),
        },
      ]
    }
    if (inspecting?.kind === 'feature') {
      const f = features.features.find((x) => x.name === inspecting.id)
      if (!f) return []
      return [
        {
          title: 'Contract',
          fields: [
            { label: 'Group', value: f.group },
            { label: 'Lookback', value: `${f.lookback_sessions ?? '—'} sessions`, title: 'History the feature reads' },
            { label: 'Availability lag', value: `${f.availability_lag_sessions ?? '—'} sessions`, title: 'Between the observation and the moment it could be known' },
            { label: 'Point in time', value: f.point_in_time_safe ? 'safe' : 'unsafe' },
            { label: 'Cross-sectional', value: f.cross_sectional ? 'yes' : 'no' },
            { label: 'Direction', value: f.direction ?? '—' },
            { label: 'Requires', value: f.required_columns?.join(', ') || '—' },
          ],
        },
        {
          title: 'Definition',
          body: (
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              {f.description}
            </p>
          ),
        },
      ]
    }
    return []
  }

  return (
    <>
      {inspecting ? (
        <Inspector
          object={inspecting}
          state={
            inspecting.kind === 'feature'
              ? (features.features.find((f) => f.name === inspecting.id)?.point_in_time_safe ? 'recorded' : 'blocked')
              : pitState(datasets.datasets.find((d) => d.dataset_id === inspecting.id)?.point_in_time ?? '')
          }
          sections={inspectorSections()}
          onClose={() => setInspecting(null)}
        />
      ) : null}

      <ObjectHeader
        glyph="D"
        name="Data"
        kind="dataset and feature contracts"
        state="recorded"
        detail={`${datasets.total} datasets · ${features.feature_count} features`}
        facts={[
          { label: 'Datasets', value: datasets.total, digits: 0 , kind: 'count'},
          { label: 'Admissible', value: datasets.training_admissible, digits: 0 },
          { label: 'Gated', value: datasets.gated?.length ?? 0, digits: 0 },
          { label: 'Features', value: features.feature_count, digits: 0 , kind: 'count'},
          { label: 'PIT unsafe', value: features.unsafe_features?.length ?? 0, digits: 0 },
          { label: 'Max lookback', value: features.max_lookback_sessions, digits: 0, unit: 'sess' , kind: 'sessions'},
        ]}
      />

      <Strip metrics={[
        { label: 'Datasets', value: datasets.total, digits: 0 , kind: 'count'},
        { label: 'Training admissible', value: datasets.training_admissible, digits: 0, title: 'Datasets whose point-in-time and survivorship classification permit training use' },
        { label: 'Gated', value: datasets.gated?.length ?? 0, digits: 0, title: 'Available but withheld from training' },
        { label: 'Excluded', value: datasets.excluded?.length ?? 0, digits: 0 },
        { label: 'Features', value: features.feature_count, digits: 0 , kind: 'count'},
        { label: 'PIT unsafe', value: features.unsafe_features?.length ?? 0, digits: 0, title: 'Features that could not be computed from information available at the time' },
        { label: 'Max lookback', value: features.max_lookback_sessions, digits: 0, unit: 'sess', title: 'The longest history any registered feature reads. Sets the minimum warm-up before any model can score.' , kind: 'sessions'},
      ]} />

      <Toolbar>
        <ToolbarGroup label="trace">
          <Link href="/terminal/provenance" className="sys-btn" style={{ textDecoration: 'none' }}>provenance</Link>
          <Link href="/terminal/providers" className="sys-btn" style={{ textDecoration: 'none' }}>providers</Link>
          <Link href="/terminal/evidence" className="sys-btn" style={{ textDecoration: 'none' }}>models</Link>
        </ToolbarGroup>
        <ToolbarSpacer />
        <span className="sys-meta">point-in-time contracts, as published</span>
      </Toolbar>

      <Panel
        title="Catalogue"
        subtitle={tab === 'datasets' ? `${datasets.total} datasets` : `${features.feature_count} features`}
        flush
        actions={
          <div style={{ display: 'flex', gap: 0, border: '1px solid var(--rule)' }}>
            {(['datasets', 'features'] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => { setTab(t); setSelected(null) }}
                className="sys-focusable"
                style={{
                  font: '500 var(--t-micro)/1 var(--font-sans)',
                  letterSpacing: 'var(--tracking-label)',
                  textTransform: 'uppercase',
                  padding: '4px 10px',
                  border: 0,
                  cursor: 'pointer',
                  background: tab === t ? 'var(--p-inverse)' : 'transparent',
                  color: tab === t ? 'var(--p-base)' : 'var(--ink-muted)',
                }}
              >{t}</button>
            ))}
          </div>
        }
      >
        {tab === 'datasets' ? (
          <DataTable
            columns={datasetColumns}
            rows={datasets.datasets}
            rowKey={(d) => d.dataset_id}
            density="compact"
            filterPlaceholder="filter datasets"
            selectedKey={selected ?? undefined}
            onSelect={(d) => {
              setSelected(d.dataset_id)
              const obj = { kind: 'dataset' as const, id: d.dataset_id, label: d.dataset_id, detail: d.source }
              recordVisit(obj)
              setInspecting(obj)
            }}
          />
        ) : (
          <DataTable
            columns={featureColumns}
            rows={features.features}
            rowKey={(f) => f.name}
            density="compact"
            filterPlaceholder="filter features"
            initialSort={{ key: 'lookback', direction: 'desc' }}
            selectedKey={selected ?? undefined}
            onSelect={(f) => {
              setSelected(f.name)
              const obj = { kind: 'feature' as const, id: f.name, label: f.name, detail: f.group }
              recordVisit(obj)
              setInspecting(obj)
            }}
          />
        )}
      </Panel>

      {tab === 'features' ? (
        <Panel
          title="Lookback distribution"
          subtitle="the warm-up every model inherits"
        >
          <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'minmax(0,1.4fr) minmax(0,1fr)' }}>
            <Histogram
              values={features.features
                .map((f) => f.lookback_sessions)
                .filter((v): v is number => typeof v === 'number' && Number.isFinite(v))}
              unit="sessions of history read"
              bins={18}
              title=""
              marks={features.max_lookback_sessions
                ? [{ at: features.max_lookback_sessions, label: 'max', color: 'var(--e-warn)' }]
                : undefined}
            />
            <Section title="Why the longest one matters">
              <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
                A panel cannot produce a complete feature row until every feature
                has its history, so the longest lookback in the registry — currently
                {' '}{features.max_lookback_sessions ?? '—'} sessions — sets the warm-up
                before any model can score its first observation. Adding one
                long-lookback feature costs that much data from the front of every
                experiment.
              </p>
            </Section>
          </div>
        </Panel>
      ) : null}

      {selectedDataset ? (
        <>
          <ObjectHeader
            glyph="D"
            name={selectedDataset.dataset_id}
            kind={`dataset · ${selectedDataset.source}`}
            state={pitState(selectedDataset.point_in_time)}
            detail={selectedDataset.point_in_time}
            object={{ kind: 'dataset', id: selectedDataset.dataset_id, label: selectedDataset.dataset_id, detail: selectedDataset.source }}
            facts={[
              { label: 'Columns', value: selectedDataset.columns?.length ?? null, digits: 0 },
              { label: 'Survivorship', value: selectedDataset.survivorship, digits: 0 },
              { label: 'Ingestion', value: selectedDataset.ingestion ?? null, digits: 0 },
            ]}
            actions={
              <button className="sys-btn" onClick={() => setSelected(null)}>clear</button>
            }
          />
        <Panel title="Contract" subtitle={selectedDataset.dataset_id} state={pitState(selectedDataset.point_in_time)}>
          <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)' }}>
            <Section title="Classification">
              <Provenance steps={[
                { label: 'Source', value: selectedDataset.source },
                ...(selectedDataset.repository ? [{ label: 'Repository', value: selectedDataset.repository }] : []),
                ...(selectedDataset.table ? [{ label: 'Table', value: selectedDataset.table }] : []),
                { label: 'Point in time', value: selectedDataset.point_in_time },
                { label: 'Survivorship', value: selectedDataset.survivorship },
                ...(selectedDataset.ingestion ? [{ label: 'Ingestion', value: selectedDataset.ingestion }] : []),
              ]} />
            </Section>
            <Section title="Notes">
              <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
                {selectedDataset.description ?? '—'}
              </p>
              {selectedDataset.point_in_time_note ? (
                <p style={{ margin: 0, fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
                  <strong style={{ color: 'var(--ink)' }}>PIT: </strong>{selectedDataset.point_in_time_note}
                </p>
              ) : null}
              {selectedDataset.survivorship_note ? (
                <p style={{ margin: 0, fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
                  <strong style={{ color: 'var(--ink)' }}>Survivorship: </strong>{selectedDataset.survivorship_note}
                </p>
              ) : null}
            </Section>
          </div>
        </Panel>
        </>
      ) : null}

      {selectedFeature ? (
        <>
          <ObjectHeader
            glyph="F"
            name={selectedFeature.name}
            kind={`feature · ${selectedFeature.group}`}
            state={selectedFeature.point_in_time_safe ? 'recorded' : 'blocked'}
            detail={selectedFeature.point_in_time_safe ? 'point-in-time safe' : 'not point-in-time safe'}
            object={{ kind: 'feature', id: selectedFeature.name, label: selectedFeature.name, detail: selectedFeature.group }}
            facts={[
              { label: 'Lookback', value: selectedFeature.lookback_sessions, digits: 0, unit: 'sess', title: 'History this feature reads' },
              { label: 'Availability lag', value: selectedFeature.availability_lag_sessions, digits: 0, unit: 'sess', title: 'Between the observation and the moment it could be known' },
              { label: 'Cross-sectional', value: selectedFeature.cross_sectional ? 'yes' : 'no', digits: 0 },
              { label: 'Direction', value: selectedFeature.direction ?? null, digits: 0 },
            ]}
            actions={
              <button className="sys-btn" onClick={() => setSelected(null)}>clear</button>
            }
          />
        <Panel
          title="Definition"
          subtitle={selectedFeature.name}
          state={selectedFeature.point_in_time_safe ? 'recorded' : 'blocked'}
        >
          <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)' }}>
            <Section title="Contract">
              <Provenance steps={[
                { label: 'Group', value: selectedFeature.group },
                { label: 'Lookback', value: `${selectedFeature.lookback_sessions ?? '—'} sessions` },
                { label: 'Availability lag', value: `${selectedFeature.availability_lag_sessions ?? '—'} sessions` },
                { label: 'Point in time', value: selectedFeature.point_in_time_safe ? 'safe' : 'unsafe' },
                ...(selectedFeature.direction ? [{ label: 'Direction', value: selectedFeature.direction }] : []),
                ...(selectedFeature.required_columns?.length
                  ? [{ label: 'Requires', value: selectedFeature.required_columns.join(', ') }] : []),
              ]} />
            </Section>
            <Section title="Definition">
              <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
                {selectedFeature.description}
              </p>
              {selectedFeature.formula ? (
                <pre style={{
                  margin: 0, padding: 'var(--d-2)', background: 'var(--p-sunken)',
                  border: '1px solid var(--rule)', fontSize: 'var(--t-meta)',
                  fontFamily: 'var(--font-mono)', overflowX: 'auto', color: 'var(--ink)',
                }}>{selectedFeature.formula}</pre>
              ) : null}
              {selectedFeature.rationale ? (
                <p style={{ margin: 0, fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
                  {selectedFeature.rationale}
                </p>
              ) : null}
            </Section>
          </div>
        </Panel>
        </>
      ) : null}

      {!selected ? (
        <Panel title="Selection">
          <StateBlock
            state="unknown"
            title="No row selected"
            detail="Choose a dataset or a feature above to see its point-in-time contract, its survivorship classification and the columns it depends on."
          />
        </Panel>
      ) : null}
    </>
  )
}
