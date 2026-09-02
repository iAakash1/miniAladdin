# Reference integration matrix

Every concept extracted from the reference systems, its disposition, and where
it landed. Status is what is **true in the repository now**, not a plan.

`P0` required · `P1` high value · `P2` useful · `P3` future

| # | Concept | Source | Why it matters | OmniSignal equivalent | Priority | Status |
|---|---|---|---|---|---|---|
| 1 | Declared freshness per data kind | Fincept `TopicPolicy` | Freshness belongs to the data, not the screen | `envelope.FreshnessPolicy`, 6 policies with written reasons | P0 | **Implemented** |
| 2 | Value and provenance as one object | OpenBB standard models | A number that cannot be questioned cannot be trusted | `envelope.DataEnvelope` | P0 | **Implemented** |
| 3 | Status derived, never asserted | Both | Callers labelled data they never measured | `Status` enum, computed in `DataEnvelope.status` | P0 | **Implemented** |
| 4 | Provenance in the panel container | OpenBB widget contract | Makes omission the hard path | `Panel` takes source/asOf/status | P0 | **Implemented** |
| 5 | Methodology beside the metric | OpenBB | Sharpe without a cost assumption is unfalsifiable | `Metric.method`, `EnvelopeMetric` | P0 | **Implemented** |
| 6 | Server-owned methodology text | OpenBB | Two components had drifted describing one number | `_decision_envelopes` in the selection service | P1 | **Implemented** |
| 7 | One-directional layer rule | Fincept | "Where did this come from" always answerable | Route → View → Service → Domain → Provider | P0 | Held; now documented |
| 8 | `waking` distinct from `unavailable` | Ours, prompted by Fincept's TTLs | 43s cold start read as an outage | `inference_client._from_exception` | P0 | **Implemented** |
| 9 | `recorded` distinct from `stale` | Ours, prompted by OpenBB status | An artifact is dated, not decaying | ttl-less policy returns `recorded` | P1 | **Implemented** |
| 10 | Command-first navigation | Both | Researchers arrive with a question, not a route | Palette with section-level deep links | P1 | Partial — entity + route search, no typed commands |
| 11 | Desks, not feature lists | Fincept bounded contexts | Navigation should follow a workflow | Market → Research → Factors → Quant → Models → Portfolio | P0 | **Implemented** |
| 12 | Canonical symbol vocabulary | Fincept `Instrument` | Provider ticker disagreements | — | P3 | Not needed at one provider |
| 13 | Subprocess env whitelisting | Fincept | Credential-shaped vars reach child processes | — | P2 | **Open follow-up** |
| 14 | Provider abstraction / routing | OpenBB | Swappable providers | — | P3 | Overhead at our provider count |
| 15 | 200-model standard taxonomy | OpenBB | Provider-agnostic domains | Envelope only | P3 | Rejected — scale mismatch |
| 16 | Auto-generated REST | OpenBB | Scales to a large surface | Hand-written endpoints | P3 | Rejected — ours are readable |
| 17 | Draggable/docked dashboards | Both | User-arranged layouts | — | — | **Rejected on integrity grounds** |
| 18 | Node/workflow editor | Fincept | Visual pipeline composition | — | — | **Rejected** — a UI for uncounted trials |
| 19 | Agent fleet | Fincept | Many personas | — | — | Rejected — personas are not evidence |
| 20 | 100+ connectors | Fincept | Data breadth | — | — | Rejected — EXP-005/007 measured that more sources *reduce* information here |
| 21 | Broker adapters, order matching | Fincept | Execution | — | P3 | Rejected — no venue, no promoted model |
| 22 | SQLite TTL cache | Fincept | One fetch, many subscribers | Artifact caching | P3 | Rejected — second cache to invalidate |
| 23 | In-process pub/sub hub | Fincept `DataHub` | 54 live screens share fetches | — | P3 | Rejected — no subscribers in a request-scoped app |
| 24 | Screens declare persisted state | Fincept `IStatefulScreen` | Explicit state lifetime | URL-held context | P2 | Web-native equivalent held |

## Licence position

Both references are **AGPL-3.0**; Fincept additionally restricts commercial,
internal and hosted use of its open build. AGPL copyleft reaches network use, so
incorporating either codebase would oblige this repository to publish under the
same terms.

**No code, markup, styling, schema files or assets from either project are
present here.** Every item marked *Implemented* is an independent implementation
of a documented architectural idea. No affiliation or endorsement is claimed.
