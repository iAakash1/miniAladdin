'use client'

/**
 * Cross-sectional rankings, one dimension at a time.
 *
 * Two things this component is careful about.
 *
 * **Trending is not a recommendation.** A security can lead the trending tab
 * while carrying a SELL verdict, so the model signal is rendered on every row
 * of every tab — including that one. A reader who sees "trending" without the
 * verdict beside it has been told half a fact.
 *
 * **A missing number is drawn as missing.** Every financial field arrives
 * nullable and renders as an em dash. Nothing is coerced to zero, because a
 * price of "$0.00" and a price we could not obtain are different claims and
 * only one of them is ours to make.
 */

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'

import { DataTable } from '@/components/system/DataTable'
import { EmptyLine, Panel, Prose, StateBlock, Strip } from '@/components/system'
import {
  type CategoryKey, type ExploreCategory, type ExploreResponse, type ExploreRow,
  fetchCategories, fetchExplore, freshness, signalTone,
} from '@/lib/explore'

const dash = '—'

function num(value: number | null | undefined, digits = 2, suffix = ''): string {
  return value === null || value === undefined || !Number.isFinite(value)
    ? dash
    : `${value.toFixed(digits)}${suffix}`
}

function pct(value: number | null | undefined, digits = 0): string {
  return value === null || value === undefined || !Number.isFinite(value)
    ? dash
    : `${(value * 100).toFixed(digits)}%`
}

const TREND_LABEL: Record<string, string> = {
  trending_up: 'Trending up',
  trending_down: 'Trending down',
  high_attention: 'High attention',
}

/** The column that explains the tab you are on. */
function categoryValue(row: ExploreRow, key: CategoryKey): string {
  switch (key) {
    case 'overall': return num(row.overall_rank, 1)
    case 'trending': return num(row.trend_score, 1)
    case 'momentum': return num(row.momentum_percentile, 0)
    case 'quality': return num(row.quality_percentile, 0)
    case 'value': return num(row.value_percentile, 0)
    case 'profitability': return num(row.profitability_sector_percentile, 0)
    case 'performance': return row.performance_grade
      ? `${num(row.performance_score, 0)} · ${row.performance_grade}`
      : num(row.performance_score, 0)
    case 'low_risk': return num(row.risk_score, 0)
    case 'news_buzz': return num(row.news_buzz, 0)
    case 'analyst_upside': return pct(row.analyst_upside, 1)
    default: return dash
  }
}

function categorySort(row: ExploreRow, key: CategoryKey): number | null {
  switch (key) {
    case 'overall': return row.overall_rank
    case 'trending': return row.trend_score
    case 'momentum': return row.momentum_percentile
    case 'quality': return row.quality_percentile
    case 'value': return row.value_percentile
    case 'profitability': return row.profitability_sector_percentile
    case 'performance': return row.performance_score
    case 'low_risk': return row.risk_score
    case 'news_buzz': return row.news_buzz
    case 'analyst_upside': return row.analyst_upside
    default: return null
  }
}

interface Filters {
  sector: string
  signal: string
  maxRisk: string
  minConfidence: string
}

const EMPTY: Filters = { sector: '', signal: '', maxRisk: '', minConfidence: '' }

export default function ExploreBoard({ mode = 'advanced' }: { mode?: 'beginner' | 'advanced' }) {
  // Beginner and advanced open different depths of the *same* analysis. The
  // link differs; the security behind it, and its verdict, do not.
  const securityHref = (symbol: string) =>
    mode === 'beginner'
      ? `/beginner/company/${encodeURIComponent(symbol)}`
      : `/terminal/security?symbol=${encodeURIComponent(symbol)}`

  const [categories, setCategories] = useState<ExploreCategory[]>([])
  const [active, setActive] = useState<CategoryKey>('overall')
  const [filters, setFilters] = useState<Filters>(EMPTY)
  const [data, setData] = useState<ExploreResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let live = true
    void fetchCategories()
      .then((list) => live && setCategories(list))
      .catch(() => live && setCategories([]))
    return () => { live = false }
  }, [])

  // The request is issued asynchronously so no state is set synchronously in
  // the effect body — a synchronous setState there re-renders before the
  // browser paints and cascades through the tab and filter state.
  //
  // `live` is the race guard: switching tabs twice quickly leaves two
  // requests outstanding, and without it the slower one lands last and
  // silently overwrites the tab the reader is actually looking at.
  useEffect(() => {
    let live = true
    void (async () => {
      setLoading(true)
      setError(null)
      try {
        const body = await fetchExplore({
          category: active,
          sector: filters.sector || undefined,
          signal: filters.signal || undefined,
          max_risk: filters.maxRisk ? Number(filters.maxRisk) : undefined,
          min_confidence: filters.minConfidence ? Number(filters.minConfidence) : undefined,
          limit: mode === 'beginner' ? 12 : 40,
        })
        if (live) setData(body)
      } catch (e) {
        if (live) setError((e as Error).message)
      } finally {
        if (live) setLoading(false)
      }
    })()
    return () => { live = false }
  }, [active, filters, mode])

  const sectors = useMemo(
    () => [...new Set((data?.results ?? []).map((r) => r.sector))].sort(),
    [data],
  )
  const activeCategory = categories.find((c) => c.key === active)

  return (
    <>
      <nav aria-label="Ranking dimension" className="xp__tabs">
        {(categories.length ? categories : [{ key: 'overall', label: 'Overall' } as ExploreCategory]).map((c) => (
          <button
            key={c.key}
            type="button"
            className="xp__tab"
            aria-pressed={active === c.key}
            data-active={active === c.key}
            onClick={() => setActive(c.key)}
          >
            {c.label}
          </button>
        ))}
      </nav>

      {activeCategory ? (
        <Panel title={activeCategory.label}>
          <Prose>{activeCategory.blurb}</Prose>
        </Panel>
      ) : null}

      <Panel title="Filters">
        <div className="xp__filters">
          <label className="xp__field">
            <span>Sector</span>
            <select
              value={filters.sector}
              onChange={(e) => setFilters({ ...filters, sector: e.target.value })}
            >
              <option value="">All sectors</option>
              {sectors.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label className="xp__field">
            <span>Model signal</span>
            <select
              value={filters.signal}
              onChange={(e) => setFilters({ ...filters, signal: e.target.value })}
            >
              <option value="">Any signal</option>
              <option value="Strong Buy">Strong Buy</option>
              <option value="Buy">Buy</option>
              <option value="Hold">Hold</option>
              <option value="Sell">Sell</option>
              <option value="Strong Sell">Strong Sell</option>
            </select>
          </label>
          <label className="xp__field">
            <span>Max risk</span>
            <input
              type="number" min={0} max={100} placeholder="any"
              value={filters.maxRisk}
              onChange={(e) => setFilters({ ...filters, maxRisk: e.target.value })}
            />
          </label>
          <label className="xp__field">
            <span>Min confidence</span>
            <input
              type="number" min={0} max={100} placeholder="any"
              value={filters.minConfidence}
              onChange={(e) => setFilters({ ...filters, minConfidence: e.target.value })}
            />
          </label>
          <button type="button" className="xp__reset" onClick={() => setFilters(EMPTY)}>
            Reset
          </button>
        </div>
      </Panel>

      {data?.stale ? (
        <StateBlock
          state="stale"
          title="These rankings are not current"
          detail={data.stale_reason ?? 'the last refresh did not complete'}
        >
          <Prose>
            Shown because out-of-date rankings a reader knows about are more
            useful than an empty page they cannot interpret.
          </Prose>
        </StateBlock>
      ) : null}

      {loading ? (
        <StateBlock state="waking" title="Ranking the universe" detail="one cached sweep" />
      ) : error ? (
        <StateBlock state="unavailable" title="Rankings unavailable" detail={error} />
      ) : !data || data.results.length === 0 ? (
        <EmptyLine label="No securities">
          Nothing in the universe met both the eligibility policy and these
          filters. Widening the filters is the first thing to try.
        </EmptyLine>
      ) : (
        <>
          <Strip
            metrics={[
              { label: 'Shown', value: data.count, kind: 'count' },
              { label: 'Eligible', value: data.eligible_count, kind: 'count' },
              { label: 'Evaluated', value: data.evaluated_count, kind: 'count' },
              { label: 'Updated', value: freshness(data.generated_at) ?? dash },
            ]}
          />
          <DataTable
            rows={data.results}
            rowKey={(r) => r.symbol}
            density="compact"
            filterPlaceholder="filter by symbol or company"
            initialSort={{ key: 'category', direction: activeCategory?.descending === false ? 'asc' : 'desc' }}
            empty="No security matched these filters."
            onSelect={(r) => { window.location.href = securityHref(r.symbol) }}
            columns={[
              {
                key: 'security', header: 'Security',
                text: (r) => `${r.symbol} ${r.company_name}`,
                sort: (r) => r.symbol,
                render: (r) => (
                  <>
                    <Link href={securityHref(r.symbol)} className="wl__sym">{r.symbol}</Link>
                    <span className="xp__company">{r.company_name}</span>
                    {active === 'trending' && r.trend_direction ? (
                      <span className="xp__trend">
                        {TREND_LABEL[r.trend_direction] ?? r.trend_direction}
                      </span>
                    ) : null}
                  </>
                ),
              },
              {
                key: 'price', header: 'Price', numeric: true,
                sort: (r) => r.price,
                render: (r) => (r.price === null ? dash : `$${num(r.price)}`),
              },
              {
                key: 'signal', header: 'Model signal',
                // Present on every tab, trending included. Attention and
                // verdict are different facts and the reader needs both.
                sort: (r) => r.model_signal,
                render: (r) => (
                  <span className="xp__signal" data-tone={signalTone(r.model_signal)}>
                    {r.model_signal ?? dash}
                  </span>
                ),
              },
              {
                key: 'category', header: activeCategory?.label ?? 'Score', numeric: true,
                sort: (r) => categorySort(r, active),
                render: (r) => categoryValue(r, active),
              },
              {
                key: 'risk', header: 'Risk',
                // Sorted on the number, displayed as the band. Null sorts
                // last in both directions, so an unmeasured security never
                // heads an ascending risk column and reads as the safest.
                sort: (r) => r.risk_score,
                render: (r) => r.risk_level ?? dash,
              },
              {
                key: 'confidence', header: 'Confidence', unit: '0-100', numeric: true,
                sort: (r) => r.confidence,
                render: (r) => r.confidence ?? dash,
              },
              {
                key: 'data', header: 'Data', unit: 'complete', numeric: true,
                sort: (r) => r.data_completeness,
                render: (r) => pct(r.data_completeness),
              },
              {
                key: 'why', header: 'Strongest factor', optional: true,
                text: (r) => r.top_positive ?? '',
                sort: (r) => r.top_positive,
                render: (r) => <span className="xp__why">{r.top_positive ?? dash}</span>,
              },
              {
                key: 'caution', header: 'Main caution', optional: true,
                text: (r) => r.top_caution ?? '',
                sort: (r) => r.top_caution,
                render: (r) => <span className="xp__why">{r.top_caution ?? dash}</span>,
              },
            ]}
          />
          <Panel title="How to read this">
            <Prose>
              A high position is a statement about where a security sits among
              the {data.evaluated_count} this system can currently score — not a
              forecast, and not advice. Trending measures movement and
              attention: a security falling hard on heavy coverage ranks highly
              there and may carry a Sell signal at the same time.
            </Prose>
            <Prose>
              Universe {data.universe_version} · scoring {data.scoring_version}
              {data.data_as_of ? ` · prices as of ${data.data_as_of}` : ''}
            </Prose>
          </Panel>
        </>
      )}
    </>
  )
}
