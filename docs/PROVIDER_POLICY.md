# Provider policy and quota budget

OmniSignal separates two operations that have different cost and evidence
requirements:

- A fallback chain serves one value. It walks ordered providers until one
  supplies a usable answer.
- The evidence fabric corroborates a claim. It consults a small ordered set in
  parallel and retains every success and failure.

The evidence fabric is intentionally bounded. More vendors are not free:
they spend quota, add failure modes, increase memory pressure, and often add
no independent information. The source of truth is `fanout_limit` in
`src/providers/capabilities.py`.

| Capability | Fan-out limit | Reason |
|---|---:|---|
| Quote | 3 | Three readings can establish a majority and identify one stale venue. |
| Price series | 2 | Adjusted histories are large; two independent series expose material disagreement. |
| News | 3 | Coverage breadth and corroboration without calling every index. |
| News sentiment | 1 | Vendor scores are model-specific and not directly comparable. |
| Company profile | 3 | A bounded union covers identity fields while limiting provider load. |
| Fundamentals | 3 | A bounded union preserves complementary fields and conflicts. |
| Analyst targets/consensus | 2 | The spread is evidence; more vendor aggregates are not independent analysts. |
| Street, ownership, SEC/XBRL | 1 | Currently primary or uniquely implemented capabilities. |

Vendor order is policy order. Unhealthy, unconfigured, or cooling providers
are skipped, allowing the next eligible provider to occupy the budget. The
fallback chain can still walk farther when a user asks for a value and the
preferred sources cannot answer.

## Failure taxonomy

Provider health uses structured classes instead of guessing from display
text:

- `AUTH_FAILURE`: HTTP 401, invalid or expired credential; never retried.
- `NOT_ENTITLED`: HTTP 403, credential lacks the endpoint or plan; never retried.
- `RATE_LIMITED`: upstream HTTP 429.
- `TIMEOUT`: the transport or bounded library call exceeded its budget.
- `COOLDOWN`: the circuit is temporarily withholding calls.
- `DEGRADED`: a provider has recovered but retains recorded failures.
- `UNAVAILABLE`: transport/upstream/parse failure without a more specific state.
- `NOT_CONFIGURED`: required credential is absent; the provider was not called.
- `IDLE`: configured but not called since this process started; upstream health is unproven.
- `HEALTHY`: at least one observed request succeeded with no unresolved failure.

The macro board asks FRED first. BLS is a keyless fallback for the equivalent
seasonally adjusted CPI and unemployment series; BEA can supply the same real
GDP growth measure when its key is active. Neither source substitutes a
missing observation with zero or changes the deterministic macro gate.

`Retry-After` is honored only inside a short request-safe bound. A longer
server delay opens a bounded cooldown and returns immediately rather than
holding an API request or worker thread asleep. Provider diagnostics expose
last success, last failure class, and remaining cooldown without exposing
credentials.

## Visual provider policy

Logo.dev is the sole visual provider and supplies verified company identity.
Pexels/Unsplash and the `image_search` capability were removed: generic stock
photography is decoration, not evidence about the researched company.
