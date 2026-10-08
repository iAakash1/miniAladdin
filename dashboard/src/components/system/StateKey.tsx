import { STATE_LABEL, STATE_ORDER, STATE_TITLE } from './state-meaning'

/**
 * The visible key to the research states: the same words the chips carry, for
 * a reader on a touch screen or a keyboard who cannot hover. Linked from the
 * footer of every workspace (`/terminal/handbook#states`) so it is one tap or
 * one Tab away from any chip, and compact: a word and a sentence per state.
 */
export default function StateKey() {
  return (
    <section id="states" className="state-key" aria-labelledby="state-key-title">
      <h2 id="state-key-title" className="state-key__title">Key to states</h2>
      <dl className="state-key__list">
        {STATE_ORDER.map((state) => (
          <div key={state} className="state-key__row">
            <dt><span className="sys-status" data-state={state}>{STATE_LABEL[state]}</span></dt>
            <dd>{STATE_TITLE[state]}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}
