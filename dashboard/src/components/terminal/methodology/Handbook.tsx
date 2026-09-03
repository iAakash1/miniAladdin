/**
 * Research handbook.
 *
 * Generated from the engine's own methodology table, not written out. Units,
 * annualisation, inputs and applicability come from the code that computes the
 * numbers, so the page cannot state a convention the engine no longer follows.
 *
 * The column that earns its place is "fails when". A list of assumptions is
 * only useful to a reader who is told what breaks them.
 */
'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'

import { Panel, Prose, Section, StateBlock, Status, Strip, Value } from '@/components/system'
import { ObjectHeader, StripSkeleton, TableSkeleton, Toolbar, ToolbarGroup, ToolbarSpacer } from '@/components/system/composition'
import { DataTable, type DataColumn } from '@/components/system/DataTable'
import { recordVisit } from '@/lib/research/history'

interface Entry {
  name: string
  unit: string
  annualisation: string
  inputs: string[]
  return_units_required: boolean
  minimum_observations: number
  purpose: string | null
  fails_when: string | null
  documented: boolean
}

interface Book {
  entries: Entry[]
  total: number
  documented: number
  minimum_observations: number
  source: string
  note: string
}

const UNIT_LABEL: Record<string, string> = {
  return: 'return',
  return_magnitude: 'magnitude',
  annualised_volatility: 'ann. vol',
  ratio: 'ratio',
  other: 'other',
}

const ANN_LABEL: Record<string, string> = {
  none: 'per period',
  sqrt_periods_per_year: '√T',
  periods_per_year: '× T',
  geometric_compounded: 'compounded',
}

export default function Handbook({ initialMeasure }: { initialMeasure?: string }) {
  const [book, setBook] = useState<Book | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(initialMeasure ?? null)

  useEffect(() => {
    let alive = true
    fetch('/api/quant/methodology')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: Book) => { if (alive) setBook(d) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [])

  // Filtering lives in the table now, so the page keeps one search affordance
  // rather than two that disagree about what they match.
  const rows = useMemo(() => book?.entries ?? [], [book])

  const columns: DataColumn<Entry>[] = useMemo(() => [
    { key: 'name', header: 'Measure', width: '22%', sort: (e) => e.name, text: (e) => e.name, render: (e) => <span className="sys-mono">{e.name}</span> },
    { key: 'unit', header: 'Unit', width: '12%', sort: (e) => e.unit, text: (e) => e.unit, render: (e) => <span className="sys-meta sys-meta--strong">{UNIT_LABEL[e.unit] ?? e.unit}</span> },
    { key: 'ann', header: 'Annualisation', width: '13%', sort: (e) => e.annualisation, text: (e) => e.annualisation, render: (e) => <span className="sys-meta sys-meta--strong">{ANN_LABEL[e.annualisation] ?? e.annualisation}</span> },
    { key: 'ret', header: 'Needs return units', width: '13%', sort: (e) => (e.return_units_required ? 1 : 0), render: (e) => <Status state={e.return_units_required ? 'blocked' : 'recorded'} label={e.return_units_required ? 'yes' : 'no'} /> },
    { key: 'purpose', header: 'Purpose', text: (e) => `${e.purpose ?? ''} ${e.fails_when ?? ''}`, render: (e) => <span style={{ fontSize: 'var(--t-meta)', color: 'var(--ink-muted)' }}>{e.purpose ?? '—'}</span> },
  ], [])

  if (error) {
    return (
      <Panel title="Handbook" state="unavailable">
        <StateBlock state="unavailable" title="The handbook could not be read" detail={`Request failed: ${error}.`} />
      </Panel>
    )
  }
  if (!book) {
    return (
      <>
        <StripSkeleton items={3} />
        <Panel title="Measures" state="waking" flush><TableSkeleton rows={12} columns={5} /></Panel>
      </>
    )
  }

  const entry = book.entries.find((e) => e.name === selected)

  return (
    <>
      <ObjectHeader
        glyph="H"
        name="Handbook"
        kind="how every number is computed"
        state="recorded"
        detail="generated from the engine's own methodology table"
        facts={[
          { label: 'Measures', value: book.total, digits: 0 , kind: 'count'},
          { label: 'With failure conditions', value: book.documented, digits: 0, kind: 'count' },
          { label: 'Minimum observations', value: book.minimum_observations, digits: 0, kind: 'count' },
        ]}
      />

      <Strip metrics={[
        { label: 'Measures', value: book.total, digits: 0 , kind: 'count'},
        { label: 'With failure conditions', value: book.documented, digits: 0, kind: 'count' },
        { label: 'Minimum observations', value: book.minimum_observations, digits: 0, kind: 'count', title: 'Below this a measure reports nothing rather than a number its sample cannot support' },
      ]} />

      <Toolbar>
        <ToolbarGroup label="trace">
          <Link href="/terminal/risk" className="sys-btn">risk</Link>
          <Link href="/terminal/evidence" className="sys-btn">evidence</Link>
          <Link href="/terminal/signals" className="sys-btn">signals</Link>
        </ToolbarGroup>
        <ToolbarSpacer />
        <span className="sys-meta">generated from the engine, so it cannot drift</span>
      </Toolbar>

      <Panel
        title="Measures"
        subtitle={`${rows.length} of ${book.total}`}
        flush
      >
        <DataTable
          columns={columns} rows={rows} rowKey={(e) => e.name}
          density="compact" filterPlaceholder="filter measures"
          selectedKey={selected ?? undefined}
          onSelect={(e) => {
            setSelected(e.name)
            recordVisit({ kind: 'method', id: e.name, label: e.name, detail: e.unit })
          }}
        />
      </Panel>

      {entry ? (
        <Panel title="Measure" subtitle={entry.name}>
          <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.4fr)' }}>
            <Section title="Derived from the engine">
              <table className="sys-table sys-table--compact">
                <tbody>
                  <tr><td>Unit</td><td className="num">{UNIT_LABEL[entry.unit] ?? entry.unit}</td></tr>
                  <tr><td>Annualisation</td><td className="num">{ANN_LABEL[entry.annualisation] ?? entry.annualisation}</td></tr>
                  <tr><td>Needs return units</td><td className="num">{entry.return_units_required ? 'yes' : 'no'}</td></tr>
                  <tr><td>Minimum observations</td><td className="num"><Value value={entry.minimum_observations} kind="count" /></td></tr>
                  <tr><td>Inputs</td><td className="num">{entry.inputs.join(', ') || '—'}</td></tr>
                </tbody>
              </table>
              <p style={{ margin: 0, fontSize: 'var(--t-micro)', color: 'var(--ink-faint)' }}>
                Read from {book.source}
              </p>
            </Section>
            <Section title="Authored">
              <div>
                <div className="sys-label" style={{ fontSize: 'var(--t-micro)', marginBottom: 'var(--d-1)' }}>Purpose</div>
                <p style={{ margin: '0 0 var(--d-3)', fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
                  {entry.purpose ?? '—'}
                </p>
                <div className="sys-label" style={{ fontSize: 'var(--t-micro)', marginBottom: 'var(--d-1)' }}>Fails when</div>
                <Prose tone="strong">
                  {entry.fails_when ?? '—'}
                </Prose>
              </div>
            </Section>
          </div>
        </Panel>
      ) : (
        <Panel title="Measure">
          <StateBlock state="unknown" title="No measure selected" detail="Choose a row to see its unit, how it is annualised, what it is computed from, and what makes it fail." />
        </Panel>
      )}

      <Panel title="Why this page is generated">
        <Prose>
          {book.note}
        </Prose>
      </Panel>
    </>
  )
}
