# Production incidents — 2026-09-18

This record covers the two production failures observed after commit
`bd41ec9`: authenticated Paper screens returned 401, and the Book endpoint
returned 500. Both were runtime integration defects, not presentation issues.

## Paper 401

The backend contract was correct. Account, positions, orders, preview, submit
and cancel all depend on `require_paper_trader`, which first verifies a Clerk
bearer token and then checks the explicit `PAPER_TRADING_OWNERS` allowlist.

The browser client was wrong: protected reads used the public `readResource`
primitive and mutations used bare `fetch`. A visible Clerk session therefore
did not become an `Authorization` header, so FastAPI correctly treated the
requests as anonymous.

The fix keeps public-resource semantics unchanged:

- `readAuthResource` delegates to the same bounded TTL/single-flight cache but
  uses `authFetch`.
- Every private cache key is namespaced by Clerk session id (user id fallback).
  If no stable identity is available, private caching is disabled. A later
  session can never receive a response cached under only the request URL.
- Order submit/cancel invalidate the current session's private cache.
- `/api/paper/access` applies the existing authentication and owner dependency
  without touching Alpaca. The UI calls it once before fetching broker state,
  so signed out, non-owner and authorized states are distinct and a denial is
  not repeated in three panels.
- Status remains public and exposes only broker configuration and whether an
  operator allowlist exists. It never exposes owner ids or credentials.

No Paper endpoint was made public and the broker host remains hardcoded to
`https://paper-api.alpaca.markets`.

## Book 500

Render application logs showed the exact traceback:

```text
quant_portfolio_service.build
  -> src.quant.risk.engine
  -> src.quant.risk.coherent
  -> from scipy.optimize import minimize_scalar
ModuleNotFoundError: No module named 'scipy'
```

`scipy` existed on the research workstation but was absent from the deploy
requirements, so local tests masked the contract error. The import occurred
before the service checked for the ignored prediction artifact, which is why
even an experiment with no files returned 500. `scipy` is now pinned and the
artifact availability check occurs before numerical imports.

The full EXP-006 predictions file remains a regenerable research artifact. A
deploy/export step now writes a compact model-specific runtime artifact:

```text
python -m scripts.quant.export_runtime_portfolio
```

The committed EXP-006 export contains the frozen gradient-boosting rows needed
by Book/Risk/Covariance, not the research dataset: 100,246 rows, 754 symbols,
2017-05-05 through 2025-05-09, about 1.1 MB. Adjacent metadata records schema,
experiment/model/target, source and output hashes, coverage and rank semantics.
The loader verifies schema and content hash before use.

Known operational conditions return HTTP 200 with a stable typed reason:
missing/unreadable/incompatible/integrity-failed artifact, missing model,
insufficient names/history, missing numerical runtime, and infeasible allocator.
Unexpected programming failures are not blanket-caught.

## Regression and deployment checks

- Frontend tests assert bearer headers for access/account/positions/orders,
  preview, submit and cancel; same-session single-flight; cross-session cache
  isolation; and post-mutation invalidation.
- Backend tests retain the anonymous 401, signed-in non-owner 403 and owner
  access contract, including the broker-free access probe.
- Clean-deployment tests remove every prediction artifact and block SciPy,
  then call every allocator through the API and require a typed 200 response.
- Corrupt and schema-incompatible artifacts are also required not to 500.
- The committed compact artifact must construct the default risk-parity book
  while the ignored workstation artifact is unavailable.
- `scripts/deployment_smoke.py` checks health, quant status, methods, Book,
  Paper status, recommendations, Explore, frontend build and inference health.
  With `CLERK_SMOKE_TOKEN`, it additionally performs protected Paper reads and
  preview only. It never submits or cancels an order and never prints the token.
