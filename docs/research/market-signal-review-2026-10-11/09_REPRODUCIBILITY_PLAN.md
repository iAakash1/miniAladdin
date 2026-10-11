# Reproducibility plan

Everything here has been run at least once on the machine below. Where a step needs an account, a licence or a decision that belongs to the owner, it says so.

## 1. Environment

Apple silicon, 12 cores, macOS, Python 3.12.11, numpy 2.2.6, pandas 2.3.3, pyarrow 18.1.0, scipy 1.18.1, scikit-learn 1.7.2. Dependencies are in `requirements-quant.txt` (the web process
does not import scikit-learn). Ridge fits take seconds; the six boosted fits take about 15 minutes each, in parallel. The full registered run took the time recorded in
`experiments/EXP-012/manifest.json` (`compute.wall_seconds`).

Process pools do not start inside the default tool sandbox of this development environment (semaphore limits), so the study is run outside it. That is a property of the sandbox, not of the code.

## 2. From nothing to the table (what an outsider would do)

| Step | Command | Needs | Result |
|---|---|---|---|
| 1. Environment | `python3.12 -m venv .venv && .venv/bin/pip install -r requirements-quant.txt` (it includes `requirements.txt`) | internet | interpreter with the libraries; the versions used are listed above |
| 2. SEC archives | `.venv/bin/python -m scripts.quant.build_pit_data estimate` then `download-sec` | internet; **set `SEC_USER_AGENT` to your own organisation and contact**, as the SEC asks; at most 10 requests per second | 58 quarterly ZIPs, 5.26 GB, 2011Q1 to 2025Q2, with self-recorded SHA-256 in `data/manifests/sec_download_manifest.json` |
| 3. Curated facts and registry | `build-facts-v3`, `build-security-master-v3` (same script) | step 2 | `data/curated/sec_v3/filings.parquet` (371,229 filings) and the facts store |
| 4. Price and other inputs | the existing local Parquet and Dolt datasets recorded in `data/manifests/data_inventory.json`; acquisition history in `docs/DATA_ACQUISITION_PLAN.md` and `docs/LOCAL_DATA_INVENTORY_FINAL.md` | the licence review the owner has not yet done (`datasets.csv` L04 to L06) | the daily panel inputs |
| 5. Rich point-in-time panel | `build-rich-panel` (same script) | steps 3 and 4 | `ds-richpit-ff3d3f556488b7da`, content hash `ff3d3f556488b7da...` |
| 6. Reliability table | `.venv/bin/python -m src.quant.pit.reliability build` | steps 3 and 5 | `reliability_v1.parquet` (sha256 `042ac1fc12957f25...`) and its manifest; about 10 seconds |
| 7. Independent check | `.venv/bin/python docs/research/market-signal-review-2026-10-11/code/validate_reliability.py` | step 6 | 0 mismatches in 16,000 comparisons |
| 8. Tests | `.venv/bin/python -m pytest tests/quant -q` | steps 1 to 6 | all pass |
| 9. Registration | `.venv/bin/python -m scripts.quant.exp012 fingerprint` must equal the fingerprint in the preregistration; `gate` must pass | the research branch pushed | the run is refused otherwise |
| 10. Rehearsal (optional) | `.venv/bin/python -m scripts.quant.exp012 rehearse --workers 6 --rehearsal-output /tmp/exp012_rehearsal` | step 6 | the whole pipeline on a label shuffled within each date; all verdicts must be NOT_SUPPORTED; no result about the hypotheses |
| 11. The study | `caffeinate -dimsu .venv/bin/python -m scripts.quant.exp012 run --workers 6` | steps 1 to 9 | `experiments/EXP-012/` |
| 12. Inference from a saved model | `.venv/bin/python -m scripts.quant.exp012 infer --artifact experiments/EXP-012/model/A5.joblib --input rows.parquet --output scores.csv` | step 11 | scores for rows that carry every listed feature |

Step 4 is the one an outsider cannot complete without the owner: the community price data's terms have not been reviewed, so the project does not redistribute anything derived from it. Everything that depends only on SEC data
(steps 2, 3, 6, 7) is reproducible by anyone with the filing archives.

## 3. Determinism and seeds

| Component | Seed or rule |
|---|---|
| Ridge arms | deterministic given the data (alpha 10, no search) |
| Boosted arms | seeds 0, 1, 2 (frozen settings from EXP-010A); the EXP-010A noise floor (Rank IC seed SD 0.00158; net Sharpe seed SD 0.0817) is the yardstick |
| Permutation placebos | five seeds (0 to 4) per arm; the within-date shuffle is `numpy.random.default_rng(seed)` |
| Shift placebo | 252 sessions (50 grid rows) within firm; deterministic |
| Moving-block bootstrap | block 6, 4,000 draws, seed 20261012 |
| Rehearsal label shuffle | seed 20261012 |
| Process order | does not affect results: each task is independent and checkpointed with a content hash |

## 4. Identity checks built into the run

- `prereg_gate`: the preregistration is committed, embeds the current fingerprint, and the commit is an ancestor of `origin/research/market-signal-review-2026-10-11`.
- The fingerprint covers the canonical definition and the bytes of twelve method files (listed in the preregistration, section 14). Changing any of them after registration makes the gate refuse.
- Parent artifacts (EXP-006 and EXP-007) are verified by hash before the run; the holdout guard must report SEALED.
- The reliability table's sha256 must equal its manifest.
- Arms A0 and A1 must reproduce EXP-011's E0 and E1 mean Rank IC to 1e-9, every prediction must be finite, and no decision date may lie after 2025-05-09; otherwise the run aborts before any contrast is computed.
- Checkpoints carry the fingerprint and a prediction hash; a checkpoint from different code is ignored, not reused.

## 5. What is not reproducible by design

- Anything that needs the sealed holdout (2025-08-26 to 2026-08-28). It is untouched, and this study does not open it.
- The screening decisions of the literature review depend on automated agents. The rubric, the per-record decisions and the agreement statistics are all in this folder, so a reader can re-screen a sample; a rerun
  will not give identical labels.
- The literature retrieval depends on the state of four public indexes on the days it ran; every response is logged with a SHA-256 (`search_log.csv`), but the raw files are git-ignored for licence reasons.

## 6. Continuous integration

The repository's only workflow is a secret scan (`.github/workflows/gitleaks.yml`). There is no CI job that runs the quant tests. The tests above are run locally; adding a CI job for `tests/quant/test_reliability.py` and
`tests/quant/test_exp012.py` is a small change that the owner can approve.
