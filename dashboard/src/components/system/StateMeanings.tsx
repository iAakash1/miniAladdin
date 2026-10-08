import { STATE_ORDER, STATE_LABEL, STATE_TITLE, stateMeaningId } from './state-meaning'

/**
 * The definition of every research state, once per page, hidden.
 *
 * Each `Status` chip points at one of these with `aria-describedby`, so a
 * screen reader announces "stale, real but past its freshness window" without
 * a hundred chips each carrying their own copy. Rendered by the root layout so
 * every route that can show a chip has it. A server component with no state:
 * the cost is fifteen short paragraphs of markup.
 */
export default function StateMeanings() {
  return (
    <div hidden data-state-meanings>
      {STATE_ORDER.map((state) => (
        <p key={state} id={stateMeaningId(state)}>{STATE_LABEL[state]}: {STATE_TITLE[state]}</p>
      ))}
    </div>
  )
}
