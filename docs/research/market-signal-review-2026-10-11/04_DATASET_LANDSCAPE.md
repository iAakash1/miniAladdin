# Dataset landscape

`datasets.csv` lists 26 datasets, nine held locally (L01-L09) and seventeen external (X01-X17), each with access and cost, licence or terms,
redistribution, point-in-time status, survivorship handling, a verification level and three 0-5 scores. This page explains the scoring, the evidence
behind it, and what it implies for the study.

## Scoring

- **pit_score**: 5 when every value carries a timestamp that proves it was public on the decision date and no later revision overwrites it; 3 when
  dated snapshots exist but coverage or revisions are uncertain; 0-1 when no usable timestamp exists or the data are known to be back-filled or survivor-biased.
- **licence_score**: 5 open and redistributable; 4 public data with an obligation (a declared user agent, attribution); 3 free but with restrictions
  or unread terms; 2 terms not reviewed; 1 conflicting or non-commercial only; 0 proprietary or paid.
- **fit_score**: usefulness to the question "when does public company information improve a cross-sectional ranking", given what can legally be held.

Scores are judgments, written next to the evidence. A row whose `verification` says "could not be read" or "search snippets only" has **not been verified**,
and its scores of 0 mean "unknown", not "bad".

## How well each dataset was verified

| Level | Datasets |
|---|---|
| Primary page read 2026-10-12 | SEC Financial Statement Data Sets and Notes (L01, X03), EDGAR fair-access rules (X01), FRED/ALFRED API documentation (X05), H.15 and Treasury (X06), Financial PhraseBank (X13), FNSPID (X14), FiQA (X15), XBRL US filing results and the DQC licence (X04), Kenneth French library (L07), AQR landing page (X07) |
| Local files with recorded hashes and independent checks | L01-L03, L08, L09 |
| Local inventory entry only | L04-L06 (rows, hashes and caveats are recorded; the vendor's terms were never reviewed) |
| Search snippets or secondary sources only | X02, X09, X12, X16 |
| Page could not be read | X08 (the CRSP document fetched was an unreadable PDF), X10, X11, X17 |

## What the evidence shows

1. **The best usable point-in-time source is public and already held.** The SEC filing registry carries an acceptance timestamp for every report, the
   statements are published "without change" from the as-filed reports (per the SEC's page), and the project has 58 quarterly archives plus validation
   manifests. This is why the registered study builds its new variables from it (L09: independent recomputation matched in 16,000 of 16,000 comparisons).
2. **The gold-standard commercial sources are out of reach and unpurchased.** CRSP (delisting returns) and Compustat/Capital IQ (as-originally-reported
   fundamentals) are institutional subscriptions with no redistribution; Sharadar is a paid product. No purchase was made and none is suggested without the
   owner's decision. Every price-based result therefore rests on the DoltHub community data, whose terms have not been reviewed and whose delisting bars are
   partial before 2017-10-26. That limits what any result can claim and is stated in the preregistration.
3. **No genuine history of vendor disagreement or provider health exists**, in the repository (checked 2026-10-12, `07_RESEARCH_CANDIDATES.md`) or among the external
   sources examined. A study that depends on it cannot be run on real data. It would require prospective logging, and inventing history is not done.
4. **Point-in-time text is the binding constraint for the multimodal direction.** Earnings-call transcripts are proprietary; news corpora found are either
   non-commercial, of unclear licence (FNSPID: its page contains contradictory statements) or not time-stamped for return work (PhraseBank, FiQA).
5. **A possible new reliability source needs an account.** XBRL US publishes per-filing data-quality rule results (the DQC rules), reachable only through an API that
   needs an access token. Whether those results are available as of the filing date is not established. It is a candidate for a follow-up, not part of EXP-012.
6. **Two operational points belong to the owner.** The SEC asks requesters to declare a user agent naming the organisation and a contact; the project's
   generic agent should be replaced by the owner's own details (this review did not supply an address, in keeping with the rule against sending the account
   email to unrelated services). The DoltHub licence review (L04-L06) is outstanding.

## Used in the registered study

L01 and L09 for the new variables; L08 as the panel; L03 for the identifier join. Nothing was downloaded for EXP-012: the filing registry was already held and
hash-checked (`data/manifests/reliability_v1_manifest.json`).
