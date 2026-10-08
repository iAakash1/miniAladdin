# Testing

How the suites are meant to run, and the rules that keep them honest.

```bash
# backend — about 7 minutes, about 5,400 tests
.venv/bin/python -m pytest tests/ --ignore=tests/test_live_smoke.py

# frontend (from dashboard/)
node --import tsx --test tests/*.test.ts     # same tests as `npm test`, without tsx's IPC socket
npx tsc --noEmit && npm run lint && npm run build
```

Running the backend suite from a copy of the tree (so that nothing edits it mid-run) needs more than
`git archive`: six quant tests read git-ignored research data (`data/research`, `data/curated`, and the
`predictions_*.parquet` files under `experiments/`), and EXP-011 stamps its receipts with a git commit.
Copy those directories into the snapshot (copy, do not link: the tests write there), delete the
snapshot's `experiments/EXP-011/checkpoints`, `git init` and commit inside it, and run it with the
repository's own interpreter. On a bare `git archive` those tests fail (a missing file, or a receipt with no
commit), which is the snapshot's fault and not the code's.

## The environment contract

A test must measure this code, not a vendor's uptime or the contents of a
developer's `.env`. `tests/conftest.py` enforces that for every test:

- **No credentials.** Every `*_API_KEY`, `*_KEY`, `*_SECRET`, `*_TOKEN` variable
  and every `SUPABASE_`, `CLERK_`, `APCA_`, `ALPACA_`, `PAPER_TRADING`,
  `METRICS_RESET`, `ADMIN_CLERK` variable is removed before the test runs. Several
  modules call `load_dotenv()` at import, so a developer machine otherwise starts
  with live provider keys and the Supabase service-role key already in the
  process. A test that needs a value sets it (`monkeypatch.setenv`), which states
  the dependency.
- **No live network.** Any DNS lookup or connection to a non-loopback host is
  refused and recorded, and the test is then **failed even if the code under
  test caught the error** — vendor clients swallow their own failures by design,
  so a test would otherwise pass while quietly depending on the internet.
  Proxy variables are removed too, so a proxy on loopback cannot carry a
  request out.

Two ways out, both deliberate:

```python
@pytest.mark.live_network          # the test genuinely needs a real service
```

```bash
OMNI_NETWORK_GUARD=record OMNI_NETWORK_REPORT=attempts.tsv pytest …   # inventory, don't fail
```

## Tests that drive a whole route

`/api/research/…` and `/api/dashboard` fan out to many vendors. Patch the ones
the test is about, and add the two fixtures for the rest:

- `offline_network` — HTTP and vendor library calls raise an ordinary
  connection error before any lookup, so the route takes its normal degraded path.
- `synthetic_series(symbol)` — a deterministic price series as a provider answer.
  Patch `providers.market_data.get_series` with it.

A test that asserts over something the route builds must first assert that it
was built. An assertion over an empty list is true, and the dashboard test once
passed offline for exactly that reason.

## Rules learned the hard way

- **Never edit a source file while the suite runs.** `inspect.getsource` reads
  the file from disk with the line numbers of the code already imported, and
  returns the wrong function.
- **Do not run the frontend build alongside the backend suite.** CPU contention
  made a timing-sensitive test flake once.
- **No test may compare a frozen data snapshot with the wall clock.** The Dolt
  earnings-calendar test did, and failed for good on 2026-10-02 when the
  clone's last scheduled date fell behind the calendar. It anchors on the
  clone's own latest commit now.
- **`NEXT_PUBLIC_*` values are inlined only where the literal
  `process.env.NEXT_PUBLIC_X` appears.** Unit tests that inject their own
  environment cannot see this; read the compiled chunk.

## Authorization

`tests/test_authorization_matrix.py` runs the real auth dependency with only
the token → user lookup stubbed: anonymous and unverifiable tokens get 401,
unconfigured authentication fails closed (503), another user's object gets
404 and is left untouched, and permission gates (paper trading, admin,
metrics reset) get 403. A real Clerk session is not available to a test.

## Protected research

The EXP-006 / EXP-007 artifacts, checkpoints and the holdout are never modified
by a code change. Before and after any pass, hash
`artifacts/experiments/EXP-007/final_selection.json`,
`experiments/EXP-007/search.json` and
`experiments/EXP-007/checkpoints/configs.jsonl` (the last is git-ignored) and
confirm they are identical.
