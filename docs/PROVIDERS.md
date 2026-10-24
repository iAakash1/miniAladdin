# Data providers

How OmniSignal reaches its data vendors, how it decides which one to ask, what
it records about each, and how to configure, observe and extend the layer. The
code is the authority; each section names the file it describes.

## The pieces

| Piece | File | Answers |
|---|---|---|
| Adapter base | `src/providers/base.py` (`VendorClient`) | How one vendor is called: key, rate limit, timeout, retries, cooldown, error classes, health, recent calls |
| Adapters | `src/providers/vendors/*.py` | One class per vendor, named by `NAME`; public methods are its operations |
| Capability registry | `src/providers/capabilities.py` | Every question the system can ask, the method that answers it, and how several answers combine |
| Provider families | `src/providers/providers.py`, `src/providers/__init__.py` | Fallback chains and fan-outs per domain (market data, fundamentals, news, macro, filings, …) |
| Catalog | `src/providers/catalog.py` | Who each vendor is, how it is reached, what its terms say and when that was checked |
| Registry view | `src/providers/registry_view.py` | One merged record per vendor for the providers page |
| Endpoints | `api/index.py` | `/api/providers/registry` (the page), `/api/providers/health` (the status bar), `/api/providers/capabilities` (the capability matrix for API clients); all three read the same provider families (`_provider_groups`) |
| Page | `dashboard/src/components/terminal/providers/ProviderConsole.tsx` | `/terminal/providers` |

Discovery is by introspection, not by list. A vendor supports a capability when
it has the capability's method (`capabilities.supported`). Every adapter
instance registers itself (`base.live_vendors`), and the registry view also
describes catalogued adapters whose service has not loaded yet, with zero
instances. `tests/test_provider_catalog.py` fails if an adapter has no catalog
entry or an entry has no adapter.

## Calling a vendor

Every HTTP call goes through `VendorClient._request_json`. Library calls
(yfinance, fredapi) go through `timed_call`. Both apply:

- **A local rate limit.** A token bucket per vendor, `DEFAULT_RPM` per minute,
  overridable with `PROVIDER_<NAME>_RPM`. One token per physical request,
  retries included.
- **A timeout.** `TIMEOUT_SECONDS` per HTTP request, `CALL_TIMEOUT_SECONDS` per
  library call. A timed-out library call releases the request; its thread may
  run on, since a Python thread cannot be killed.
- **Bounded retries.** Up to `MAX_RETRIES` (default 2), on transient failures
  only: timeouts, transport errors, HTTP 429 and 5xx. The delay is
  `BACKOFF_BASE × 2^attempt` plus up to `BACKOFF_JITTER` (25%) of itself at
  random. A 429's `Retry-After` is honored up to `MAX_RETRY_AFTER_SECONDS`; a
  longer one opens a cooldown instead of sleeping. 401, 402/403, 404/422,
  unreadable replies and vendor error envelopes are never retried.
- **Cooldowns.** After `COOLDOWN_AFTER_FAILURES` consecutive vendor-level
  failures the vendor is skipped for `COOLDOWN_SECONDS`. A rejected credential
  benches it for `AUTH_COOLDOWN_SECONDS` (15 min), then one probe per window.
- **Redaction.** Credential query parameters are redacted where error text is
  built (`base.redact`), for library errors as well as HTTP ones. The registry
  view also strips URLs from error text before it leaves the server.

Only `VendorError` leaves an operation: an adapter that misreads a reply raises
a `parse_failure`, which counts toward the cooldown like any other fault.

### Error classes

`FailureClass` in `base.py`: `rate_limited`, `auth_failure`, `not_entitled`,
`timeout`, `upstream_failure`, `parse_failure`, `local_limiter`, `unavailable`.
Vendors that report a refusal in a 200 body are classified from its wording
(`classify_api_error`). A 404/422 about one input, or an empty answer, is not a
vendor fault: it is recorded with scope `request` and does not degrade the
vendor or count toward its cooldown.

### Empty is not failed

"The vendor said nothing matches" is recorded as an `empty` outcome and
returned as no data. "The vendor did not answer usefully" is a failure with a
class. Callers keep the two apart: an outage returns "unavailable", never an
empty list. Valid zeros are values, not gaps.

## Health states

`VendorClient.health_snapshot`. First match wins:

| State | Means |
|---|---|
| `DISABLED` | The operator took it out of routing (`PROVIDER_DISABLED`) |
| `NOT_CONFIGURED` | No credential, so it was never asked |
| `DEV_ONLY` | Not used outside local development |
| `AUTH_FAILURE` | Its latest answer refused the credential |
| `COOLDOWN` | Paused after repeated failures |
| `STALE` | Nothing observed inside the health window |
| `RATE_LIMITED`, `NOT_ENTITLED`, `TIMEOUT`, `UNAVAILABLE` | Its latest answer was that failure |
| `IDLE` | Configured, never called in this process |
| `DEGRADED` | Answering, with vendor-level failures inside the window, or a plan that excludes some operations |
| `HEALTHY` | Answered inside the window, and nothing vendor-level failed there |

Inside the window each snapshot counts calls as `ok` (answered, including
"nothing matches"), `failed` (the vendor's faults) and `declined` (a 404 about
one input, a plan boundary, or our own rate limiter). Only `failed` degrades a
vendor.

The health window is `PROVIDER_HEALTH_WINDOW_SECONDS` (default 6 h). Health is
*availability evidence* about the vendor; the freshness of a value is a separate
fact carried by each result's provenance (its `as_of` and retrieval time).

When several instances of one vendor exist (SEC EDGAR has three), the registry
view sums their counters and reports the most severe state
(`registry_view.STATE_RANK`): failure outranks success, and recent success
outranks staleness and idleness.

**Counters are per process.** They reset when the server restarts and are not
persisted; on Cloud Run each instance has its own. The page prints when the
process started. No live probes are run when the page opens.

## Routing

Each provider family declares its chains and fan-outs in
`src/providers/providers.py`. A vendor is asked only if it is `available`:
configured and not disabled. Benched vendors (cooling down or with a rejected
key) are skipped by fallback chains. Capabilities declare how several answers
combine (`reconciliation`: `median`, `union`, `distribution`, `per_vendor`,
`dedupe`, `primary`, `none`) and the largest fan-out. Fallback stays inside one
capability, so a fallback never substitutes data of a different kind. The order
inside a chain is fixed in code (deterministic). No vendor is ranked cheaper or
more reliable without a measurement.

`PROVIDER_DISABLED` (comma- or space-separated names) is the switch for a vendor
whose license is in question or that misbehaves. It holds on every routing
path, because every path checks `available`, and it does not touch the
credential.

## Recent calls and observability

Each instance keeps its last 40 calls (`RECENT_EVENTS`): time, operation (the
adapter method that made it), outcome, HTTP status, duration, attempt number,
scope and the API request id (`X-Request-Id`), so a failure on the page can be
matched to its log line. Symbols, parameters, URLs and payloads are **not**
recorded, because every signed-in reader can see the page.

Metrics: `vendor.call` latency by vendor/operation/outcome,
`vendor.rate_limited`, `vendor.cooldown`, `vendor.credential_rejected`,
`vendor.unreadable_rows` (`src/observability/metrics.py`, `/api/metrics`).

## Caching and retention

Vendor answers are cached in process memory (`src/providers/cache.py`,
`InMemoryCache`), keyed by question and inputs, with a lifetime per domain set
in the provider families (`providers.py`: a quote 60 s, a daily series 5 min,
fundamentals 1 h). An expired entry is retained for a while and returned
flagged as stale only when every vendor in the chain fails. Some services cache
a failed answer for a shorter time so an outage is retried soon
(`DEGRADED_TTL_SECONDS` in `official_record.py`, `company_intelligence.py`,
`graph_service.py`). The provider layer writes nothing to the database; results
in a signed-in user's history or saved reports are stored under that user's id. Raw
vendor payloads are not persisted, which is also what the reviewed terms
require where they speak to it (Finnhub: delete data when the subscription
ends). See `docs/LEGAL_REVIEW.md` for each provider's terms status.

## The providers page

`/terminal/providers` reads `/api/providers/registry` and shows: a summary
(registered, configured, answered recently, failing, constrained, stale or idle,
not configured, disabled), capabilities with no eligible source, a searchable
and filterable catalog, a detail panel per provider (configuration by variable
name, capabilities, counters, recent calls, request policy, source and terms,
advisories), and the coverage of each capability. **Refresh** re-reads the
registry and says whether anything changed. There is no credential form and no
live "test" button: credentials are configured on the backend, and probing
vendors from a page any signed-in user can open would spend shared quota.

## Configuration

Credentials live on the backend only (Secret Manager bindings on Cloud Run,
`miniAladdin/.env` locally). The frontend never receives a vendor key; the
registry carries each variable's **name** and whether it is set, never its
value.

| Variable | Read by | Effect when missing |
|---|---|---|
| `<VENDOR>_API_KEY` etc. (see the table in `docs/LEGAL_REVIEW.md`) | that adapter's `KEY_ENV` | Vendor is `NOT_CONFIGURED`; capabilities fall to other vendors or return "unavailable" |
| `SEC_USER_AGENT` | `sec_vendor.py` | EDGAR receives a placeholder identifier; the page raises an advisory. Set it to a name and a mailbox you read |
| `SEC_API` | `sec_vendor.py` | Optional key for a paid SEC mirror; EDGAR itself is keyless |
| `PROVIDER_DISABLED` | `base.py` | Unset: every configured vendor is eligible |
| `PROVIDER_HEALTH_WINDOW_SECONDS` | `base.py` | 21600 (6 h) |
| `PROVIDER_<NAME>_RPM` | `base.py` | The adapter's `DEFAULT_RPM` |

To test one integration locally: set its variable in `miniAladdin/.env`, start
the API from `miniAladdin/` with `.venv/bin/uvicorn api.index:app --port 8000`,
make a request that uses it, and read `/api/providers/registry` — the vendor's
`recent` calls show the outcome. Unit tests never call real vendors (`tests/test_provider_catalog.py`
uses mocked sessions); `tests/test_live_smoke.py` is separate and opt-in.

## Adding a provider

1. Subclass `VendorClient` in `src/providers/vendors/`. Set `NAME`, `KEY_ENV`
   (or `None`), `DEFAULT_RPM` and, if it differs, `TIMEOUT_SECONDS`.
2. Implement the capability methods it can answer (`get_price`, `get_news`, …;
   see `capabilities.py`). Call `self._get_json(...)` or `self.timed_call(...)`;
   pass `expect=dict` or `list` when the shape is known. Return the domain
   schema from `src/providers/schemas.py`, or `None` for "nothing matches".
3. Add a `ProviderInfo` to `src/providers/catalog.py`. Record the terms as
   `not_located`, `located` or `reviewed` — only what you actually checked.
4. Add it to the provider family's vendor list and chain in
   `src/providers/providers.py`.
5. Add tests with a mocked session: success, the vendor's error envelope, 401,
   429, timeout, malformed JSON, an empty answer.
6. Document its variable in `docs/LEGAL_REVIEW.md` (generated table) and set the
   secret on the backend.

## Known limits

- Counters are per process and per Cloud Run instance, and reset on deploy.
- Recent calls are kept in memory only (40 per instance).
- Health is inferred from real traffic; a vendor nobody has used reads idle or
  stale until it is called.
- Several adapters call vendors without naming the operation; their recent calls
  are named after the adapter method instead (`get_filings`), which is the
  finest grain available without editing each adapter.
- Present-day downloads of historical data are not point-in-time snapshots; the
  research datasets document which values were captured when.
