# GitHub quality and verification report (Phase II)

Branch `research/market-signal-review-2026-10-11` of `https://github.com/iAakash1/miniAladdin` (public). Written 2026-10-12. The sections marked **FINAL** are completed after the last push; their values are in
the final report and in `RESEARCH_STATE.md`.

## 1. History audit: the two commits named in the brief

| Commit | What it contains | Finding |
|---|---|---|
| `cbce239` "Start the market-signal literature review: query bank, logged retrieval script, state checkpoint" | adds `MAILTO = "<account email>"` to the retrieval code, and the line "Identity for every commit: `iAakash1 <account email>`, no trailers" to `RESEARCH_STATE.md` | **Confirmed.** The constant was the address placed in `mailto` and User-Agent fields of the first scholarly-API requests (OpenAlex, Crossref, arXiv, NBER). Both occurrences were later removed from the tree (commit `312d0a1` removed the constant; the state file no longer holds it at HEAD) |
| `ecd178c` "Recover the screening work from the stopped runs and account for every agent" | adds `Path.home() / ".claude/projects/-Users-<user>-Downloads-omnisignal-final/<session id>"` literals to `code/audit_transcripts.py` and `code/make_recovery_artifacts.py`, and absolute local paths inside `recovery/*.csv` | **Confirmed.** Commit `88ec777` replaced the source literals with environment-variable lookups. At HEAD the session identifier appears nowhere; **14 lines of `recovery/transcript_audit.csv` still carry absolute local paths** (the local account name and project folder) |

Method: `git log -S` over the branch for the email, the `.claude/projects` literal and `/Users/`; `git grep` at HEAD and at every branch commit; raw author and committer metadata of all 20 branch commits
(all `iAakash1 <the configured address>`, no trailers, no tool credit in any message).

## 2. Risk assessment

| Item | Exposure | Operational risk | Notes |
|---|---|---|---|
| Account email in source at `cbce239`..`312d0a1` | public repository history | **low** | The same address is the author and committer address of every commit on the branch, and appears in pre-existing owner code (`src/quant/pit/sec_foundation.py`, `src/quant/pit/security_master.py`, `scripts/quant/build_pit_data.py`, one audit document) that Phase II did not touch. The privacy cost of the constant is the sending of the address to scholarly APIs (cannot be undone), not its presence in history |
| Account email in requests already made | third-party logs | **low, irreversible** | the owner decides whether to request deletion; nothing in the repository can undo it |
| Local account name and project folder in `recovery/transcript_audit.csv` | public repository | **low** | reveals a macOS user name and folder layout; no credential, token or host |
| Session identifier in `cbce239`..`88ec777` source | public history | **negligible** | an opaque identifier of a local session; cannot be used remotely |

No secret, token, key or credential was found anywhere on the branch (regex scan of all 177,615 added lines against the main branch for private keys, GitHub, OpenAI, Slack and Google key shapes, JWTs and
`key = "..."` assignments; the repository's own `gitleaks` workflow only runs on pushes to `main` and on pull requests, so it never scanned the branch).

## 3. Safe remediation without rewriting history

History is **not** rewritten and nothing is force-pushed. What can be done forward-only:

1. Replace the 14 absolute paths in `recovery/transcript_audit.csv` by repository-relative or hashed identifiers in a normal commit (the file would still hold them in older commits).
2. Add the account email and `/Users/` shapes to a local pre-commit check (the repository already has a `gitleaks` pre-commit hook configured in `.pre-commit-config.yaml`; a custom rule for these two patterns is a one-file change).
3. If the owner wants the email gone from history, the only complete remedy is a history rewrite of a public branch, which also changes every commit identifier that the registrations (`639eb65`, `a39400f`, ...) refer to, and
   is therefore **not recommended** now. GitHub's email-privacy setting protects future commits only and would break the identity the brief requires.
4. The SEC contact: the EXP-014 data acquisition sends the owner's address to the SEC only, through an environment variable read at run time (`src/quant/pit/edgar_client.py`); no request log, manifest or exception
   message ever contains it (tested). The live service still sends a placeholder agent because `SEC_USER_AGENT` is unset (owner action in `docs/OWNER_ACTIONS.md`).

## 4. Checks run on the Phase II changes (2026-10-12)

| Check | Result |
|---|---|
| New tests | 59 across `test_snapshot_archive.py` (25), `test_edgar_client.py` (8), `test_exp014_inference.py` (9) and `test_exp014.py` (17): all pass; the archive tests were mutation-checked (12 of 12 deliberate breakages caught); the inference tests compare every fast formula with an explicit refit |
| Quant test tree on the closing tree | 1,333 passed in 326 s |
| Full suite | 5,513 passed, 3 skipped (448 s) on the checkpoint tree. A second attempt on the closing tree stalled at 26% in a non-quant test using process pools and was killed; it is the intermittent teardown / process-pool hang documented in `PHASE2_HANDOFF.md` section 5, not a failure. Re-run once more at the end of Phase II |
| Static checks | `ruff check --select E9,F` clean on every new file; two unused-variable warnings remain in older scripts. Ruff 0.17.0 and mypy 2.4.0 were installed in a throwaway environment outside the repository (not added to the project's requirements). A type check was not run: the new modules are untyped in the repository's existing style |
| Secret and PII scan | regex scan of all added lines on the branch against `main` (private keys, GitHub, OpenAI, Slack and Google key shapes, JWTs, `key = "..."`): none; the account email and local paths: none in any Phase II file; `gitleaks` is not installed and its CI job does not run on branch pushes |
| Attribution scan | all 20 branch commits (and the two Phase II commits) are authored and committed by `iAakash1` with the configured address; no trailer, no tool credit in any message or file |
| Data-licence check | `/data/research_mid/` is ignored except the membership file; `research_papers/` (PDFs) is ignored; no data file of unreviewed licence is tracked; the request logs record URLs, statuses, sizes and body hashes only |
| Model reproducibility | the saved-artifact round trip (fresh process, 1e-9) is tested on synthetic rows; the real EXP-014 artifact is produced by the rehearsal and the registered run, not yet |
| Protected files | EXP-006/007 files compared by hash before and after (see `RESEARCH_STATE.md`) |
| Remote | verified after the push in the final report: remote SHA, raw author and committer of every new commit |
