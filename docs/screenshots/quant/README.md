# /quant screenshots

**Environment: LOCAL.** Captured from `next dev` on `localhost:3000` against the
FastAPI backend on `127.0.0.1:8000`, reading the real experiment artifacts in
`experiments/`. These are **not** production or staging captures — nothing here
is deployed, because nothing has been promoted.

Regenerate with:

```bash
scripts/docs/capture_quant_screenshots.sh
```

## What the capture script changes, and why it reverts

Two temporary edits are required to photograph this page, and the script reverts
both on EXIT — including on failure or interrupt:

1. **`/quant` is auth-gated**, like the rest of the terminal. Signing in from a
   script would mean handling credentials, so the route is made public for the
   duration instead. The page's data comes from the FastAPI backend either way,
   so the render is identical to the authenticated one.
2. **Sections are native `<details>`** and default to collapsed. Headless Chrome
   screenshots before running any supplied JS, so they are opened in the source
   for the capture.

Neither change is ever committed. Verify with `git status` after running.

## The captures

| File | Viewport | Shows |
|---|---|---|
| `01-quant-research-full-LOCAL.png` | 1440×3050 | The whole page: deployment banner, holdout lock, experiment history, model intelligence with verdicts, leakage controls, regime analysis, cost sensitivity, overfitting diagnostics, provenance |
| `02-deployment-status-holdout-LOCAL.png` | 1440×900 | Above the fold: `NO_MODEL` and `HOLDOUT LOCKED` |
| `03-quant-mobile-LOCAL.png` | 430×1400 | Responsive behaviour |

## What they show, which is a negative result

The page was designed so it reads the same whether the research succeeded or
failed, and these captures are the failed case:

* **`NO_MODEL`** — read from the model registry, not from the leaderboard below
  it. No result on the page can change it.
* **`HOLDOUT LOCKED — contract not armed`.**
* **`random_forest` labelled `OVERFIT`**, with the gate table that produced the
  label: `ic_t_stat 1.911` against a required 2.0, `gross_sharpe −0.276` and
  `net_sharpe −0.598` against a required > 0.
* **Baselines inline with learned models**, marked but not separated.
* **Regime rows carry their date counts**, and four of five read `INSUFFICIENT`.
* **`EXP-002` still listed, marked `VOID`**, with the reason.

A known cosmetic issue is visible in the mobile capture: the shared
`TerminalShell` header overflows horizontally at 375px. It predates this work and
affects every terminal page equally; the quant sections themselves scroll their
wide tables internally and do not push the document.
