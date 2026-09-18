'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { Grid, Panel, Prose, StateBlock, Status, Strip } from '@/components/system'

interface InferenceStatus {
  configured?: boolean
  health?: { status?: string; model_loaded?: boolean; error?: string; detail?: string }
}

interface QuantStatus {
  deployment_status?: string
  total_entries?: number
  production?: number
  candidates?: number
}

interface ProviderStatus {
  providers?: Record<string, { status?: string; healthy?: boolean }>
  summary?: { healthy?: number; degraded?: number; unavailable?: number }
}

export default function RuntimeHealth() {
  const [inference, setInference] = useState<InferenceStatus | null>(null)
  const [quant, setQuant] = useState<QuantStatus | null>(null)
  const [providers, setProviders] = useState<ProviderStatus | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let live = true
    Promise.allSettled([
      fetch('/api/providers/health').then((response) => response.ok ? response.json() : Promise.reject()),
      fetch('/api/quant/inference/status').then((response) => response.ok ? response.json() : Promise.reject()),
      fetch('/api/quant/status').then((response) => response.ok ? response.json() : Promise.reject()),
    ]).then(([providerResult, inferenceResult, quantResult]) => {
      if (!live) return
      if (providerResult.status === 'fulfilled') setProviders(providerResult.value as ProviderStatus)
      if (inferenceResult.status === 'fulfilled') setInference(inferenceResult.value as InferenceStatus)
      if (quantResult.status === 'fulfilled') setQuant(quantResult.value as QuantStatus)
      setFailed([providerResult, inferenceResult, quantResult].every((result) => result.status === 'rejected'))
    })
    return () => { live = false }
  }, [])

  if (failed) {
    return <StateBlock state="unavailable" title="Runtime health unavailable" detail="Provider, registry and inference checks could not be read." />
  }

  const providerRows = providers?.providers ? Object.values(providers.providers) : []
  const healthy = providers?.summary?.healthy
    ?? providerRows.filter((provider) => provider.healthy || provider.status === 'ok').length
  const loaded = inference?.health?.model_loaded === true

  return (
    <Grid>
      <Panel
        title="Provider health"
        state={providers ? 'live' : 'waking'}
        actions={<Link href="/terminal/providers" className="sys-meta sys-meta--strong">All providers →</Link>}
      >
        {providers ? (
          <Strip metrics={[
            { label: 'Healthy', value: healthy, kind: 'count' },
            { label: 'Degraded', value: providers.summary?.degraded ?? null, kind: 'count' },
            { label: 'Unavailable', value: providers.summary?.unavailable ?? null, kind: 'count' },
          ]} />
        ) : <StateBlock state="waking" title="Checking providers" />}
      </Panel>

      <Panel
        title="Inference"
        state={loaded ? 'experimental' : inference ? 'unavailable' : 'waking'}
        actions={<Link href="/terminal/lab" className="sys-meta sys-meta--strong">Models →</Link>}
      >
        {inference ? (
          <>
            <Status state={loaded ? 'live' : 'unavailable'} label={loaded ? 'SERVICE READY' : 'SERVICE UNAVAILABLE'} />
            <Prose size="fine">{inference.health?.detail ?? inference.health?.error ?? 'Research-only inference; promotion state is separate.'}</Prose>
          </>
        ) : <StateBlock state="waking" title="Checking inference" />}
      </Panel>

      <Panel
        title="Research registry"
        state={quant ? (quant.deployment_status === 'SERVING' ? 'production' : 'blocked') : 'waking'}
        actions={<Link href="/terminal/evidence" className="sys-meta sys-meta--strong">Evidence →</Link>}
      >
        {quant ? (
          <Strip metrics={[
            { label: 'Status', value: quant.deployment_status ?? 'unknown' },
            { label: 'Registered', value: quant.total_entries ?? null, kind: 'count' },
            { label: 'Production', value: quant.production ?? null, kind: 'count' },
            { label: 'Candidates', value: quant.candidates ?? null, kind: 'count' },
          ]} />
        ) : <StateBlock state="waking" title="Reading registry" />}
      </Panel>

      <Panel title="Agent runs" state="recorded">
        <Prose size="tight">Run the real specialist graph and inspect claims, evidence, reconciliation and validation.</Prose>
        <Link className="sys-btn" href="/terminal/agents">Open agent observatory</Link>
      </Panel>
    </Grid>
  )
}
