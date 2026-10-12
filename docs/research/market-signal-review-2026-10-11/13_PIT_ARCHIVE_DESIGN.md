# Point-in-time snapshot archive: design, guarantees and the replay audit of the live scorer

Status: **implemented and tested on 2026-10-12 as a research-side library** (`src/quant/pit/snapshot_archive.py`, `tests/quant/test_snapshot_archive.py`, 25 tests). Nothing in the production service imports it,
nothing is scheduled, and no provider snapshot has been collected yet. **It cannot reconstruct any past value.** Its only effect is that values captured from now on can be replayed later.

## 1. Why it exists

The live scorer takes most of its inputs from providers at request time (`05_OMNISIGNAL_SIGNAL_AUDIT.md`). The provider overwrites its answer the next day and the product keeps none of them, so a backtest of
those factors can only use a later, revised value: the same leakage that Bracher and Funk (2026) found in a retrospective forecasting benchmark, and the reason macro studies use ALFRED vintages (Agyekum and
Obese 2026). A ledger of what the system saw, and when, is the minimum needed to ever evaluate the scorer honestly.

## 2. What a record holds

| Field | Meaning | Checked |
|---|---|---|
| `source_id`, `record_type` | the provider and the kind of document (fundamentals, analyst, news item, macro release) | non-empty |
| `instrument_id` | namespaced identity: `cik:`, `security:`, `figi:`, `isin:`, `ticker:` or `series:` | a bare ticker is refused (tickers are reused) |
| `retrieved_at` | when this system obtained the payload, UTC, timezone-aware | observed captures must be within 5 minutes of the writer's clock and cannot go backwards |
| `published_at`, `published_kind` | when the provider says it was published, and whether that is `vendor_stated`, `first_observed` or `unknown` | never later than `retrieved_at`; `unknown` when absent |
| `effective_date` | the date the payload describes | ISO date |
| `payload_sha256`, `payload_bytes`, `reference` | the content (stored gzip, once, by hash) or only a pointer | a record without payload must carry a reference and `reference_only` retention |
| `schema_version`, `source_version` | the payload schema and the provider API or data revision | non-empty |
| `licence`, `redistribution`, `retention` | terms: `allowed`/`not_allowed`/`unknown`; `indefinite`, `reference_only` or `delete_after:YYYY-MM-DD` | non-empty, parsed |
| `validation_status`, `validation_notes` | `unvalidated`, `valid`, `invalid` | enumerated |
| `capture` | `observed` (this system retrieved it at the stated time) or `asserted` (an importer says so) | asserted records are excluded from replays unless asked for |
| `record_id`, `prev_hash`, `chain_hash` | hash of the content, and the chain up to it | recomputed by `verify()` |

## 3. Guarantees, and how each is tested

| Guarantee | Test |
|---|---|
| Append-only: an edit, a deleted record or a torn last line is detected | `test_an_edited_record_a_deleted_record_and_a_torn_tail_are_detected` |
| Corrupted payloads are detected on verify and on read | `test_a_corrupted_payload_is_detected_on_verify_and_on_read` |
| A re-capture with unchanged content is a no-op; content that flips A, B, A is three records | `test_identical_recapture_is_a_noop_but_a_flip_flop_is_three_records` |
| `as_of(t)` never shows a later record, and says nothing before coverage starts | `test_append_then_replay_as_of_never_shows_the_future` |
| Timestamp consistency (published after retrieved, naive times, back-dating, future stamps, going backwards) | `test_timestamp_consistency_is_enforced`, `test_observed_captures_cannot_go_backwards_...` |
| Missing or invalid fields are refused and nothing is written | `test_records_with_missing_or_invalid_fields_are_refused` (12 cases) |
| Retention can purge a payload but never a record; shared content survives while any holder needs it | `test_a_missing_payload_is_a_problem_unless_its_retention_has_ended`, `test_expire_payloads_keeps_content_still_needed_by_another_record` |
| A tampered hash cannot make verify read outside the archive | `test_a_tampered_payload_hash_cannot_make_verify_read_outside_the_archive` |
| Reproducibility: the same inputs give byte-identical segments and the same head | `test_same_inputs_give_byte_identical_archives_and_the_same_head` |

A mutation check was run: twelve deliberate breakages of the module (timestamp rule, chain check, record-hash check, payload-hash check, duplicate rule, skew rule, monotonicity, cutoff, asserted filter, torn-tail
flag, namespace rule, shared-payload expiry) were each caught by at least one test.

**Tamper evidence.** The chain protects against accidental or partial edits. A party that rewrites the whole archive consistently would leave a different head hash, so `anchor()` returns `{records, head, at}` to be
copied somewhere the archive does not control (a commit, a log) at regular intervals.

## 4. What it does not do

* It does not reconstruct history. `coverage()` shows the first observed capture per source; `as_of` before that returns nothing, never a later value, and there is no back-fill method.
* A `vendor_stated` publication time is only as good as the vendor. The archive records which kind of evidence stands behind it.
* It is single-writer (an advisory file lock serialises appends) and scans the archive on each batch; `append_many` amortises that. It is meant for research volumes (thousands of records a day), not a high-rate feed.
* Licence fields record terms; they do not decide them. Whether a provider's terms allow storage at all must be settled before any capture starts, and the payload of a `not_allowed` source should be stored
  as a reference only.

## 5. Replay audit of the live scorer (`live_scorer_replayability.csv`, 37 rows)

| Layer | Rows | Replayable today | Notes |
|---|---|---|---|
| Factors | 15 | 7 from prices (6 momentum, reversal); 3 only approximately from SEC filings (quality); **5 not replayable** (4 fundamental, 1 news) | provider equivalence of adjusted closes is not established |
| Risk components | 9 | 9 from prices and benchmarks | the macro and liquidity components also need the gate inputs |
| Macro gate | 1 | not replayable | FRED at the latest release; ALFRED vintages blocked by a missing key |
| Sleeves, confidence deductions | 12 | depend on the members | inherit the weakest input |

Weighted by the composite's sleeve weights (momentum 0.40, news 0.20, fundamental 0.20, quality 0.15, reversal 0.05): **about 45% of the weight is replayable from prices today, 15% only through a different
SEC-based definition, and 40% (news and fundamental sleeves) cannot be replayed at all.** A backtest of the whole composite is therefore impossible on past data; a bridging experiment on the price-derived
sleeves is possible, and the archive is the only route to the rest.

## 6. What remains before it is used

1. A review of each provider's terms for caching and retention (blocking).
2. A capture job that writes `observed` records for the fields in the replayability table, behind a feature flag, not in the request path.
3. A periodic `anchor()` commit and a scheduled `verify()`.
4. A year of capture before any evaluation of the news or fundamental sleeves is attempted. Until then the interface should say that those sleeves are not validated on a point-in-time panel.
