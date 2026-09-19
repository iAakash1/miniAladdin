# Dataset gap analysis

Audit date: 2026-09-19. Sizes are local snapshots, not promises of vendor
coverage. `datasets/` is about 14 GB and `data/research/` about 219 MB.

## What is actually present

| Family | Local snapshot | Research status | Principal gap |
|---|---|---|---|
| US OHLCV | 2,910,092 rows; 2012-01-03--2026-08-28 | Used | Corporate-action/delisting completeness before 2017 is partial |
| Universe | 184 monthly PIT snapshots; top 250 liquid names | Used | No historical sector/index membership or market-cap distribution in artifact |
| Splits | 3,993 rows since 2014-03-28 | Used | Earlier adjustment provenance |
| Dividends | 494,438 rows | Available | Ex-date/pay-date PIT semantics need fixtures |
| Treasury rates | 9,158 rows | Used | Vintage/revision handling absent unless ALFRED-backed |
| Options vol history | 691,007 rows since 2019-05-10 | Available, unused by EXP-006 | IV methodology, survivorship, and license unknown |
| Options daily aggregate | 1,918,396 rows since 2019-02-09 | Available, unused | Not full quote/contract surface; sparse short history |
| Earnings EPS history | 168,473 rows | Available, unused | As-reported/revision semantics |
| Earnings calendar | 117,601 rows | Availability aligned | Timestamp precision and corrections |
| EPS estimates | 7,060,412 rows | Vintage dated, unused | Coverage and vendor redistribution terms |
| Sales estimates | 7,060,412 rows | Vintage dated, unused | Same; consensus construction methodology |
| Income statements | 270,925 rows | Available, unused | No filing/restatement vintage |
| Balance-sheet components | about 284k rows each | Available, unused | No filing/restatement vintage |
| Cash flow | 176,631 rows | Available, unused | No filing/restatement vintage |
| Fama-French factors | Local | Evaluation support | Version and download provenance should be pinned |
| News/transcripts | Live product only | Not research-ready | No durable licensed PIT archive/session alignment |
| Insider/institutional filings | Not normalized | Missing | SEC Forms 3/4/5 and 13F are feasible public inputs |

## Gap priorities

| Priority | Gap | Why it matters | Close condition |
|---:|---|---|---|
| 1 | Security master: identifiers, sector, exchange, shares, delistings | Enables neutralization, exposure controls, and honest survivorship accounting | PIT mapping with effective dates, delisting return policy and identifier tests |
| 2 | Filing-time fundamentals | Current rows cannot distinguish original filings from restatements | SEC accession/acceptance timestamp plus versioned facts |
| 3 | Estimate-revision provenance | Revision breadth exists locally but quality is unmeasured | Coverage matrix, vintage monotonicity, source/license record |
| 4 | Event text and structured guidance | Recent research finds incremental earnings-disclosure information | Timestamped 8-K/exhibit corpus with reproducible parser and no future exhibits |
| 5 | Insider transactions | Cheap orthogonal public signal candidate | Form 4 filing/transaction timestamps, role and clustered-trade features |
| 6 | Options surface quality | Potential forward-looking signal but weak incremental evidence and high cost | Contract-level synchronized quotes, filters, IV method and license |
| 7 | Borrow/shorting and realistic costs | Long/short backtests otherwise overstate feasibility | PIT borrow availability/fee and market-impact model |

## Leakage, survivorship, and sample risks

- Every source must store both economic period and first-available timestamp.
  A period-end date is not an availability date.
- Statements must be versioned by SEC acceptance/accession. Without that,
  backfilled restatements are prohibited as historical features.
- Delisted securities and delisting returns must remain in the evaluation
  frame. Missing observations cannot be silently treated as zero returns.
- Options require synchronized underlying timestamps, stale/open-interest
  filters, quote-quality controls, and explicit post-close availability.
- Estimate histories need a monotone vintage test and a same-day cutoff.
- The 2019 options start provides few regimes. It cannot support claims about
  long-cycle robustness.
- Vendor terms can allow analysis while forbidding redistribution. Store raw
  data outside git and commit only manifests, hashes, schemas, and permitted
  aggregates.

## Dataset readiness rubric

A family is `READY` only if it has schema validation, row-count/date coverage,
content hash, license/source record, identifier mapping, availability-time
rules, leakage fixtures, missingness by date and universe, and a deterministic
rebuild. Otherwise it is `RESEARCH_ONLY` or `BLOCKED`. By this standard the
frozen OHLCV/universe core is ready for comparison work; statement revisions,
options, news, and new filing feeds are not yet ready for model selection.
