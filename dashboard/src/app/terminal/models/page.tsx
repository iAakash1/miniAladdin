import { redirect } from 'next/navigation'

/**
 * Compatibility redirect.
 *
 * This route rendered a second Models surface on the old shell. Every
 * analysis it held now lives in the model workbench and the deployed model, so keeping it
 * alive would mean maintaining two implementations of one workspace — which is
 * how the two of them drift apart and start disagreeing.
 *
 * The URL is preserved because it was linked and bookmarked. The duplicate
 * implementation is not.
 */
export default function LegacyModelsPage() {
  redirect('/terminal/lab')
}
