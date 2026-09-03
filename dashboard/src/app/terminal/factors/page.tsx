import { redirect } from 'next/navigation'

/**
 * Compatibility redirect.
 *
 * This route rendered a second Factors surface on the old shell. Every
 * analysis it held now lives in the factor workbench, cross-section and ablation, so keeping it
 * alive would mean maintaining two implementations of one workspace — which is
 * how the two of them drift apart and start disagreeing.
 *
 * The URL is preserved because it was linked and bookmarked. The duplicate
 * implementation is not.
 */
export default function LegacyFactorsPage() {
  redirect('/terminal/factorlab')
}
