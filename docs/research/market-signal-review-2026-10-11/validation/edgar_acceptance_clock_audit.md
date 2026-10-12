# Audit of the EDGAR submissions registry's acceptance timestamps

Generated from `data/manifests/edgar_filings_v1.json` (companies: 2,098; filings kept: 481,027; request log `data/manifests/edgar_requests_submissions.jsonl`).

## Finding

The `acceptanceDateTime` field of the SEC's submissions JSON (documented as UTC, serialised with a trailing `Z`) is **not reliable**. Compared on 96,429 filings that are also in the Financial Statement Data Sets
(whose stamps are New York wall-clock time at minute resolution), only 71.8% of registry stamps equal the FSDS stamp plus the correct UTC offset (4 hours in summer time, 5 in winter).
25.0% are 8 or 10 hours ahead (the offset applied twice) and 3.3% show the New York clock labelled as UTC.

| Population (registry stamp minus FSDS clock) | Filings | Share | 10-K/10-Q whose filing date obeys the 17:30 rule if the registry stamp is read as UTC | ...if the FSDS stamp is read as New York time |
|---|---|---|---|---|
| clock_unconverted (0 h) | 3,144 | 3.3% | 91.5% | 99.2% |
| double_converted (+8/+10 h) | 24,096 | 25.0% | 33.9% | 99.2% |
| utc_correct (+4/+5 h) | 69,189 | 71.8% | 99.3% | 99.2% |

How the test works: EDGAR assigns a filing the next business day's date when it is accepted after 17:30 New York time. A stamp that is wrong by 4 to 10 hours violates that rule often; a correct one almost never. The FSDS
stamp obeys it for 99.2% of 10-K and 10-Q filings in every population, so it is the reliable clock. This is an inference from the rule, backed by six hand checks against EDGAR's own filing index pages:

| Accession | Population | Filing date | EDGAR index page "Accepted" (New York) | Registry JSON stamp |
|---|---|---|---|---|
| `0001558370-19-009443` | +8 h | 2019-10-30 | 2019-10-30 16:17:46 | 2019-10-31T00:17:46Z |
| `0000080424-16-000212` | +8 h | 2016-08-09 | 2016-08-09 16:03:15 | 2016-08-10T00:03:15Z |
| `0001047469-11-001229` | +10 h | 2011-02-24 | 2011-02-24 07:03:13 | 2011-02-24T17:03:13Z |
| `0001628280-23-004842` | 0 h | 2023-02-23 | 2023-02-23 16:25:20 | 2023-02-23T16:25:20Z |
| `0000794170-21-000052` | +4 h | 2021-09-02 | 2021-09-02 16:09:32 | 2021-09-02T20:09:32Z |
| `0001103982-23-000006` | +5 h | 2023-02-03 | 2023-02-03 12:06:38 | 2023-02-03T17:06:38Z |

## Consequences

* A study that uses the registry stamp as an availability time can place a filing **earlier** than it was public (the unconverted population, by 4 to 5 hours: enough to cross the 16:00 close) or **later** (the double-converted
  population, by 4 to 10 hours). The first is look-ahead.
* There is a second, rarer trap: 31 filings (0.006%) carry a **filing date more than one day earlier than the acceptance date** (delinquent filers submitting old reports; the largest gap is
  633 days). Using the filing date as availability would place such a filing 21 months before it existed.

## What this project does

* Availability of amendments and periodic reports: the FSDS stamp, in New York time, with the 16:00 rule (`src/quant/pit/sec_facts.available_session`).
* Registry events that the FSDS lacks (Item 4.02 8-Ks, late-filing notices, amendments without financial statements): `event_date = max(filing date, date of the stamp)`, usable from the first session **after** that date.
  A shifted stamp can then only delay an event by a day, never advance it, and a back-dated filing date cannot advance it.
* The registry is a current-state download (retrieved on the date in the request log); acceptance times of accepted filings do not change, but withdrawn filings, if any, would be absent.

## Limits

The audit covers 10-K and 10-Q-type filings that are in the FSDS (those with financial statements). Whether 8-K stamps are shifted by the same share is not tested; the conservative rule above does not depend on it.
No claim is made about why the field behaves this way.
