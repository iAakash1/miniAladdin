# /quant screenshots

**Environment: LOCAL — `UNVERIFIED IN PRODUCTION`.**

Captured from `next dev` on `localhost:3000` against the FastAPI backend on
`127.0.0.1:8000`, reading the real experiment artifacts in `experiments/`.

These are **not** production captures. `mini-aladding.vercel.app` serves the
frontend, but this build of `/quant` has not been deployed and verified there at
the time of capture, and the page is behind Clerk auth — signing in from a script
would mean handling the owner's credentials, which is not done. Production
verification requires the owner to authenticate in a browser after deploy.

Regenerate the full-page capture with:

```bash
scripts/docs/capture_quant_screenshots.sh
```

## What the capture script changes, and why it reverts

`/quant` is auth-gated like the rest of the terminal. The script makes the route
public **for the duration only** and restores it on EXIT — including on failure
and on interrupt — then *verifies* the route is gated again before returning.
The page's data comes from the FastAPI backend either way, so the render is
identical to the authenticated one.

An earlier version of this script restored with `git checkout` over a path that
included an untracked file. Git failed on the whole pathspec and restored
neither, leaving `/quant` publicly routable. It now restores from byte copies and
greps the result to prove the gate is back.

## The captures

Section crops are taken from one full-page render at 1440 px, using bounding
boxes read from the live DOM — so each file is a real region of a real page, not
a separate re-render.

**Two experiments appear.** Most captures show **EXP-006** (the newest study, and
what `/quant` selects by default). `04-ablation-LOCAL.png` shows **EXP-005**,
because EXP-006 is not an ablation study and correctly renders no ablation
section. Both are real pages; neither is staged.

| File | Shows |
|---|---|
| `01-overview-LOCAL.png` | EXP-006 — deployment banner (`NO_MODEL`), holdout lock, the finding card, research overview |
| `02-experiments-LOCAL.png` | Experiment explorer — EXP-005, EXP-004, EXP-002 VOID |
| `03-models-LOCAL.png` | Model comparison, gate table, train-vs-validation scatter, per-fold IC |
| `04-ablation-LOCAL.png` | **EXP-005** — feature-family ablation, arm chart, contrast cards |
| `05-walkforward-LOCAL.png` | Fold timeline with purge/embargo and the locked holdout, spread curve |
| `06-integrity-LOCAL.png` | Research integrity checks and negative controls |
| `07-datasets-LOCAL.png` | Dataset coverage with point-in-time status per source |
| `08-registry-LOCAL.png` | Model registry counts, rejection reasons, training pipeline |
| `01-quant-research-full-LOCAL.png` | The whole page in one image |
| `03-quant-mobile-LOCAL.png` | Responsive behaviour at 430 px |

## What they show, which is a negative result

The page was designed to read the same whether the research succeeded or failed.
These captures are the failed case:

* **`NO_MODEL`** — read from the model registry, not the leaderboard below it.
* **`HOLDOUT LOCKED — contract not armed`**, with the window and session count.
* **`NO ROBUST EVIDENCE OF EDGE`** with the strongest surviving evidence stated
  in full: IC, t, gross Sharpe, net Sharpe, baseline delta, deflated Sharpe p,
  and `REJECTED`.
* **Every ablation contrast reads `NO IMPROVEMENT`**, and the callout labels the
  highest observed t-statistic `HYPOTHESIS — NOT A RESULT`.
* **Regime rows carry their date counts**; four of five read `INSUFFICIENT
  EVIDENCE`.
* **`EXP-002` still listed and marked `VOID`**, with the reason.

## Known cosmetic issue

At 375 px the shared `TerminalShell` header overflows horizontally
(`scrollWidth` 1004 vs viewport 375). It predates this work and affects every
terminal page equally. The quant sections themselves scroll their wide tables
inside their own containers and do not push the document.
