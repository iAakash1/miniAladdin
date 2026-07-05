/* ============================================================
   Pure derivations for the Validation page narrative sections.
   Every threshold here mirrors the "good"/"bad" bands already stated
   in metricGlossary.ts, so the plain-English verdicts below are just
   an application of those documented rules to the numbers the backend
   already computed (src/services/backtest_service.py) — nothing here
   fabricates or recomputes a statistic.
   ============================================================ */

export interface FactorDiagnostic {
  ic: number | null
  sign_stability: number | null
  samples: number
}

export interface OverallHealth {
  label: 'Positive' | 'Mixed' | 'Weak' | 'Insufficient data'
  tone: 'pos' | 'warn' | 'neg'
  reasons: string[]
}

/**
 * A single plain-English read of "can I trust this model," from IC, hit
 * rate and Sharpe — the three headline checks (predictive power, directional
 * accuracy, risk-adjusted return). Thresholds match metricGlossary.ts.
 */
export function overallHealth(params: {
  ic: number | null
  hitRate: number | null
  sharpe: number | null
  samples: number
}): OverallHealth {
  const { ic, hitRate, sharpe, samples } = params
  if (samples < 20 || ic === null) {
    return { label: 'Insufficient data', tone: 'warn', reasons: ['Fewer than 20 walk-forward samples — not enough history to judge this ticker yet.'] }
  }

  const reasons: string[] = []
  let score = 0

  if (ic > 0.05) { score += 1; reasons.push(`IC of ${ic.toFixed(3)} clears the 0.05 bar for a meaningful single-name signal.`) }
  else if (ic < 0) { score -= 1; reasons.push(`IC of ${ic.toFixed(3)} is negative — the signal has been backwards over this window.`) }
  else { reasons.push(`IC of ${ic.toFixed(3)} is positive but modest.`) }

  if (hitRate !== null) {
    if (hitRate > 55) { score += 1; reasons.push(`Hit rate of ${hitRate}% is above the 55% bar for a real directional edge.`) }
    else if (hitRate < 48) { score -= 1; reasons.push(`Hit rate of ${hitRate}% is below chance.`) }
  }

  if (sharpe !== null) {
    if (sharpe > 1.0) { score += 1; reasons.push(`Strategy Sharpe of ${sharpe.toFixed(2)} is in the "good" band (> 1.0).`) }
    else if (sharpe < 0) { score -= 1; reasons.push(`Strategy Sharpe of ${sharpe.toFixed(2)} is negative over this window.`) }
  }

  if (score >= 2) return { label: 'Positive', tone: 'pos', reasons }
  if (score <= -1) return { label: 'Weak', tone: 'neg', reasons }
  return { label: 'Mixed', tone: 'warn', reasons }
}

/**
 * Deterministic flags for known failure modes — every condition here is a
 * direct threshold check against a number the backend already computed.
 * Returns [] when nothing is flagged (a clean bill of health is a valid,
 * expected result, not an omission).
 */
export function failureModes(params: {
  psi: number | null
  factorDiagnostics: Record<string, FactorDiagnostic>
  confusionMatrix: Record<'long' | 'flat' | 'short', { up: number; down: number }>
  scoreDistribution: Array<{ bin: string; count: number }>
}): string[] {
  const flags: string[] = []
  const { psi, factorDiagnostics, confusionMatrix, scoreDistribution } = params

  if (psi !== null && psi > 0.25) {
    flags.push(`Distribution drift: PSI of ${psi.toFixed(3)} is above the 0.25 threshold — the score distribution has shifted meaningfully between the first and second half of the tested window.`)
  }

  const unstable = Object.entries(factorDiagnostics).filter(
    ([, diag]) => diag.sign_stability !== null && diag.sign_stability < 0.5 && diag.samples >= 12,
  )
  if (unstable.length > 0) {
    flags.push(`${unstable.length} factor(s) show sign stability below 0.5 (essentially coin-flip over time): ${unstable.map(([name]) => name).join(', ')}.`)
  }

  const longTotal = confusionMatrix.long.up + confusionMatrix.long.down
  if (longTotal >= 8 && confusionMatrix.long.down > confusionMatrix.long.up) {
    flags.push(`Long calls have realized down more often than up (${confusionMatrix.long.down} vs ${confusionMatrix.long.up}) over this window.`)
  }
  const shortTotal = confusionMatrix.short.up + confusionMatrix.short.down
  if (shortTotal >= 8 && confusionMatrix.short.up > confusionMatrix.short.down) {
    flags.push(`Short calls have realized up more often than down (${confusionMatrix.short.up} vs ${confusionMatrix.short.down}) over this window.`)
  }

  // Bin labels are signed bucket-start floats (e.g. "-0.6", "+0.0", "0.2");
  // parsing the number directly is robust to bin width/count changing on
  // the backend, unlike matching specific label strings.
  const totalSamples = scoreDistribution.reduce((sum, bucket) => sum + bucket.count, 0)
  const centerSamples = scoreDistribution
    .filter((bucket) => Math.abs(parseFloat(bucket.bin)) <= 0.2)
    .reduce((sum, bucket) => sum + bucket.count, 0)
  if (totalSamples > 20 && centerSamples / totalSamples < 0.15) {
    flags.push('Score distribution is concentrated in the extreme tails rather than near zero — the model rarely sits at Hold, which is unusual for a well-behaved signal.')
  }

  return flags
}
