import { redirect } from 'next/navigation'

/**
 * Compatibility redirect.
 *
 * /quant was the research terminal: verdicts, gates, the search, the ablation,
 * the deployed model, the book. Every one of those was rebuilt in the
 * workbench — the holdout preflight on Gates, the deployed model on Models,
 * the ablation on Factors, the search on Experiments, the selection population
 * and the verdict on Evidence, the allocators on Book.
 *
 * Evidence is where it lands, because that is the question /quant existed to
 * answer: not what was trained, but whether it should be believed.
 */
export default function LegacyQuantPage() {
  redirect('/terminal/evidence')
}
