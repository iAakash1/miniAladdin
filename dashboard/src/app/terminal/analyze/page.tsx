import { redirect } from 'next/navigation'

/** Starting research is search (⌘K) from anywhere; this route is kept for old links. */
export default function AnalyzeRedirect() {
  redirect('/terminal/command')
}
