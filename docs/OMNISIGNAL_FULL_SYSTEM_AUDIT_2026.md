# OmniSignal full-system audit (2026-09-20)

Scope: the point-in-time data foundation, the research record through EXP-011 (prepared), and an evidence-based review of the product surface.
Method: what was **measured** is stated with its number; what was **inspected only** (code and tests present) is labelled as such; what was **not done** is listed.
No holdout data, licensed raw data, research PDF, secret or model promotion is involved anywhere in this pass.

## 1. Research record

| Study | Recorded result | Note |
|---|---|---|
| EXP-006 | NEGATIVE | weak ordering (~0.03 Rank IC) + ~20x turnover |
| EXP-009A | cost effect only | top-k dropout cut turnover ~66%; not new signal |
| EXP-009B / C / D | no ordering gain / no reliable analyst value / equivalent | negative results kept |
| EXP-010A | noise floor | Rank IC seed SD 0.00158; net Sharpe seed SD 0.0817 |
| EXP-010B | `ECONOMICALLY_IMPROVED` (validation only) | turnover −66%, net Sharpe up in 10/10 seeds, folds 1/6/7 worse; **not perfectly blind** (seed-0 prototype seen before thresholds) |
| EXP-011 | **prepared, not run** | fingerprint `d5dd80d2…d9aa`, commit `679596a` |

The cadence question is closed for this research cycle. Summaries: `docs/EXP_010A_RESULTS.md`, `docs/EXP_010B_RESULTS.md`; the API/UI research history (`/api/quant/research-history`) shows all of the above, including negative and not-run studies.

## 2. Data foundation (measured)

* **Local inventory** (`docs/LOCAL_DATA_INVENTORY_FINAL.md`, `data/manifests/data_inventory.json`): 18 normalised datasets (measured rows, symbols, dates, bytes, columns, hashes), 11 stores; nothing large or licensed is tracked.
* **SEC archives** (`data/manifests/sec_archive_verification.json`): 58/58 present, 2011Q1–2025Q2 continuous, 5,259,572,200 bytes, every size equal to sec.gov's Content-Length, every SHA-256 and CRC good, all four members present, 402,145 filings. The SEC publishes no checksums, so hashes are self-recorded provenance.
* **Defects found in the previous curated store (v2)** and fixed in `sec-core-facts-v3` (`docs/SEC_TAG_MAP_AUDIT.md`): 56.3% of mapped rows were dimensional (segment/component) facts that v2 admitted; `unit` was null in 100% of rows (currencies could mix); the `as_of` view preferred the fallback tag; coverage was limited to today's ticker-resolvable CIKs, which made fundamentals missing-not-at-random for delisted names. v3: 14,574,206 consolidated rows from 369,971 filings and 14,408 CIKs.
* **Availability**: acceptance time in US Eastern; at or after 16:00 → next session; 200,000 sampled real rows show 0 same-day after-close and 0 before-acceptance.
* **Restatement invariance on real data**: 2019Q1–Q4 truncated at 2019-07-01; 150,514 later vintages of pre-cut keys and 11,347 later amendment rows exist; every earlier row and both views identical.
* **Validation**: `python -m scripts.quant.build_pit_data validate-all` → `data/manifests/pit_validation.json`, overall **BLOCKED** (ALFRED needs a key), with `security_master_pit_gate` **PARTIAL**; every other check PASS.

## 3. Security master (`docs/PIT_SECURITY_MASTER_STATUS.md`)

CIK identity; ticker windows dated by price data (capped at the 2025-05-09 cutoff); links graded A/B (trusted), C/D/X/UNRESOLVED (never used for features). 813 of 950 tickers resolved; 37 unresolved; 96 links to filers with no 10-K/10-Q; genuine ticker reuse detected (e.g. `AI`, `AA`); one successor linked on exact name continuity. SIC as of each filing → Fama-French 12/17/48 from the Kenneth French files (no GICS). Share counts: 33,028 cover-page, 45,095 balance-sheet, 69,497 labelled weighted-average proxy. Exit evidence: 82 EXACT (Form 25), 78 APPROXIMATED; no delisting return invented. **`security_master_pit = false`**: trusted identity 91.8–95.0% by fold against 95%.

## 4. Rich PIT panel (`docs/RICH_PIT_PANEL_AUDIT.md`, `docs/PIT_FEATURE_CATALOG.md`)

`ds-richpit-ff3d3f556488b7da`: 139,292 in-universe name-dates, 762 securities, 76 features (26 unchanged baseline + 50 documented). Built twice with byte-identical output. Leakage suite (truncation invariance, future-price and label perturbation, ticker relabelling, missing-not-zero, baseline pass-through) passes on a synthetic world. Controls (size, industry-relative) are withheld. Names about to exit are less often resolved (trusted 85.3% vs 93.6%, n=109): stated, not hidden.

## 5. Product surface (inspected; behaviour covered by existing tests)

* **Registry**: 69 experimental, 34 retired, 0 validated/promoted. Product copy carries "EXPERIMENTAL / promotion BLOCKED".
* **Portfolio / Book**: all eight typed failures exist in `quant_portfolio_service.py` with tests; no fake-portfolio fallback found.
* **Decision Quality**: STRONG/ACCEPTABLE/WEAK/INSUFFICIENT is defined as evidence quality, not win probability.
* **API availability**: typed states (NOT_CONFIGURED, INSUFFICIENT_DATA, DEPENDENCY_UNAVAILABLE, PERMISSION_DENIED, …) exist in `availability.py`.
* **Paper**: paper-only, fail-closed owner authorisation, tests present. No weakening made.
* **LLM authority**: decision-authority and invariance tests exist; the LLM does not decide BUY/SELL.
* **Research history**: new `/api/quant/research-history` endpoint and a `ResearchHistory` panel on the Experiments page; a not-run study can never read as complete or promoted (tests in both languages).
* **Not re-audited behaviourally this pass**: the agent pipeline, dashboard state rendering beyond static checks, provider fabric.

## 6. Security and claims

* Secret-pattern scan of tracked files: 0 real secrets; one documented placeholder; no `.env` in history; no PDFs / raw SEC / large Parquets tracked (`research_papers/` is ignored). No secret was printed.
* `npm audit` (production): 1 critical + 8 high + 1 moderate → **0** after `next` 16.1.6 → 16.3.5 and non-breaking fixes; `tsc`, ESLint, 569 unit tests and `next build` re-verified. Python dependency audit **not run**.
* Claims: no "state-of-the-art", "production-ready" or "battle-tested" in product code; "outperform"/"profitable" occur only as descriptive factor language or benchmark arithmetic; nothing describes a model as promoted or validated.

## 7. Governance

Holdout untouched (`SEALED`), every experiment manifest records `touched: false`. EXP-008 untouched. New experiments follow new-ID → preregister → push → gate → run. Every commit is authored and committed by `iAakash1 <aakashjawle101@gmail.com>` with no attribution trailers.

## 8. Tests

* Backend, whole `tests/` tree, run **twice**: **2,999 passed, 3 skipped** in both runs (of which the quant suite is 1,152+). Five Kaggle-pipeline tests were added after those runs and pass (`tests/quant/test_kaggle_pipeline.py`).
* Frontend: `tsc --noEmit` clean, ESLint clean, **569** unit tests passed, `next build` succeeded (after the `next` 16.3.5 upgrade).
* Playwright E2E: **not run** (requires an authenticated session; no auth bypass attempted).
* New tests this pass cover: SEC archive audit, v3 fact store (exclusions, availability, views, restatement invariance), security master (keys, reuse, grades, successors, exits, shares), as-of attachment and the coverage gate, PIT fundamentals (TTM algebra, truncation), rich-panel leakage, feature catalog, EXP-011 (rule, receipts, resume, synthetic end-to-end), Kaggle export/import, research history.

## 9. Data licences (summary; full table in `docs/LOCAL_DATA_INVENTORY_FINAL.md`)

| Source | Terms as recorded | Redistribution / product use |
|---|---|---|
| SEC Financial Statement Data Sets, submissions and companyconcept APIs | US government public data; fair access <= 10 requests/s with a declared User-Agent (followed: <= ~7.5/s) | not committed for size; product use pending an attribution review |
| DoltHub `stocks` / `options` / `earnings` / `rates` clones | "open data on DoltHub" note in the manifests, **terms not reviewed** | not assumed; nothing committed; the Kaggle export refuses without an explicit acknowledgement |
| Kenneth French SIC and factor files | free for research | mapping files kept ignored under `data/raw/french_sic/`; hashes recorded |
| Research papers (`research_papers/`) | copyrighted PDFs | `.gitignore`d; none tracked |

Bulk SEC files, curated Parquets, rich-panel Parquets and Kaggle bundles are all git-ignored; only schemas, manifests, hashes and aggregate coverage are tracked.
