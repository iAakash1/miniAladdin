# Security

What this system protects, where it enforces it, and the specific mistakes the
enforcement is shaped around.

## Authentication

Clerk session JWTs (RS256), verified against Clerk's public JWKS. No SDK and no
network round-trip per request — the JWKS is fetched once and cached.

**A production deployment that verifies signatures but not the issuer is
refused.** `jwt.decode(issuer=None)` does not fail; it skips the `iss` check
entirely. Signature verification still runs, so this was never an open door,
but it silently drops a check the operator believes they have. So
`CLERK_JWKS_URL` set without `CLERK_ISSUER` makes `is_configured()` return
False in production, and persistence endpoints report themselves unconfigured
rather than authenticating under a weaker contract than intended.

Clerk session tokens carry no `aud`, so identity is signature + issuer +
expiry, with 10 seconds of leeway.

## Authorisation

Three **independent** dimensions. Conflating any two of them is a bug:

| Dimension | Values | Answers |
|---|---|---|
| Role | USER, ADMIN | what you may operate |
| Experience | BEGINNER, ADVANCED | how much detail you see |
| Entitlement | FREE, PRO | what you have paid for |

A beginner is not less trusted. An admin is not automatically advanced. A PRO
subscriber is not an operator.

Permissions are named for the **capability**, not the route, so adding a second
endpoint to an existing capability does not create a second place to forget the
check.

**Never rely only on frontend RBAC.** Hiding a navigation item is a
presentation choice; the boundary is the `Depends(require_permission(...))` on
the route. An ordinary signed-in account is refused at `/api/admin/diagnostics`
even if it constructs the request by hand.

**Ownership is checked on every row**, not inferred from the request. Every
repository query is scoped by `clerk_user_id`; a watchlist is not readable
because you know its id.

## Prompt injection

Third-party text — headlines, article bodies — is untrusted input that reaches
a model.

1. **Sanitise before storage.** `sanitise()` strips markup and control
   characters, collapses whitespace and truncates. Markup can carry hidden
   instructions; control characters can hide them from a human reviewing the
   same string.
2. **Flag what looks like an instruction.** `looks_like_injection()` marks text
   containing injection markers.
3. **Fence it in the prompt.** System prompts carry an explicit UNTRUSTED
   CONTENT clause naming the boundary.
4. **Make the attack pointless.** This is the one that matters: the signal,
   confidence and risk are attached to an answer **after** generation, copied
   from the scorecard. A model that follows an injected instruction changes the
   prose and nothing else. No model writes a number a reader acts on.

## Secrets

**Never in an error a caller can see.** By the time `requests` has raised, the
API key is already inside a formatted exception string, so `redact()` operates
on the message rather than on the URL — reconstructing the URL to re-encode it
would be fragile and easy to forget at the next call site. It covers `apikey`,
`api_key`, `token`, `access_token`, `client_secret` and their neighbours.

**Never in graph state.** `AnalysisState` is logged and served, so a failing
node records `type(exc).__name__` and not the message.

**Never raw to an ordinary user.** Backend faults become typed availability
states with a written explanation. The stack trace goes to the log.

## The paper-trading guarantee

`alpaca_paper` hardcodes `https://paper-api.alpaca.markets` and **refuses any
other host**. Not a default, not configuration — a refusal. It cannot be
pointed at a live endpoint by an environment variable, a config file, or a
test.

The cost is real and accepted: the paper tables cannot be rendered against a
local stub, so their alignment is checked at source rather than in a browser.
That is the correct trade. A guarantee with a test-only escape hatch is not a
guarantee.

The surface is named "Paper" everywhere, never "Trade" or "Portfolio". A nav
entry reading "Trade" has already implied something untrue.

## Serialisation

Starlette is configured with `allow_nan=False`. A `NaN` or `Infinity` reaching
a response is a serialisation failure rather than invalid JSON delivered to a
client that will parse it into something.

Every numeric boundary checks `math.isfinite` / `Number.isFinite`. Endpoint
tests assert no response contains a non-finite literal.

## What is not claimed

- No penetration test has been run against this deployment.
- The Redis job store has not been exercised against a real server; see
  [BACKGROUND_JOBS.md](BACKGROUND_JOBS.md).
- Rate limiting is per-provider (vendor cooldowns), not per-caller.
