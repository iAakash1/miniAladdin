/**
 * The two independent controls between a paper order and a broker, drawn.
 *
 * Gate one decides WHO: a signed-in user must be named in the operator
 * allowlist. Gate two decides WHERE: the broker client is fixed to Alpaca's
 * paper host and refuses to start against any other. The live host is shown
 * as refused because it is — there is no configuration that reaches it.
 */
/** What the server reported about one gate; `unknown` when it was not checked. */
export type GateState = 'open' | 'closed' | 'unknown'

/**
 * Each gate is drawn from its own reading. Both can be closed at once — a
 * deployment with neither credentials nor operators is the default — and a
 * gate that was never checked is drawn neutral rather than passed.
 */
export default function PaperGates({ who, where }: { who: GateState; where: GateState }) {
  const owners = who
  const creds = where
  return (
    <figure className="pg" aria-label="How a paper order reaches the broker">
      <ol className="pg-flow">
        <li className="pg-node">
          <span className="pg-node__k">You</span>
          <span className="pg-node__v">order ticket · review · confirm</span>
        </li>
        <li className="pg-gate" data-state={owners}>
          <span className="pg-gate__k">Gate 1 · who</span>
          <span className="pg-gate__v">signed-in user named in the operator allowlist</span>
        </li>
        <li className="pg-gate" data-state={creds}>
          <span className="pg-gate__k">Gate 2 · where</span>
          <span className="pg-gate__v">paper credentials, host fixed to paper-api.alpaca.markets</span>
        </li>
        <li className="pg-node pg-node--broker">
          <span className="pg-node__k">Alpaca Paper</span>
          <span className="pg-node__v">simulated fills · no real funds</span>
        </li>
      </ol>
      <p className="pg-live">
        <span className="pg-live__x" aria-hidden>×</span>
        Live trading host — refused by construction; no setting reaches it. Research signals never place orders.
      </p>
    </figure>
  )
}
