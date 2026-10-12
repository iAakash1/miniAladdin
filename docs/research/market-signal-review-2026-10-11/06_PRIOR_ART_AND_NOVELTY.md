# Prior art and novelty audit

> **Phase II update (2026-10-12).** Read levels for fourteen works were upgraded to a full-text extract and seven more were found or re-read at abstract level; see `12_FULLTEXT_REVIEW_AND_NOVELTY_MATRIX.md` and `fulltext_ledger.csv`.
> The sentence below, "No full text was read", is superseded for those works only. Two findings change this page: long-run underperformance after restatements is documented (Gondhalekar, Joshi and McKendall 2012, abstract level),
> and point-in-time SEC construction has a published benchmark (Liu 2026, abstract level). The overall novelty rating stays **low**; one probably decisive paper (Frieder and Shanthikumar 2008) is still unread.

## The claim being tested

> **EXP-012 (`docs/EXP_012_PREREGISTRATION.md`).** Properties of a company's *disclosure process*, measured point in time from the SEC filing registry alone (amendments to periodic reports,
> whether the latest report has been amended, a shortfall of periodic reports, a deterioration of filing lateness against the firm's own history), add information to a cost-aware
> machine-learning ranking of US equities beyond a rich point-in-time fundamentals set, either directly or as moderators of the fundamentals signals, and the effect is not reproduced by
> placebos built from the same variables.

The registration states in section 2 that the underlying idea is not new. This page checks how much of it is, against the 89 works in `03_ANNOTATED_BIBLIOGRAPHY.md`, the screening ledger, and the searches in
`01_REVIEW_PROTOCOL.md`. Read levels: every comparison below rests on an abstract, a title, or verified bibliographic metadata. **No full text was read.**

## The claim, decomposed

| Component | Closest prior work | Verdict |
|---|---|---|
| **1. Reliability of the information behind a signal conditions how well the signal predicts** | Information uncertainty strengthens continuation (Zhang 2006) and post-earnings drift (Francis, LaFond, Olsson and Schipper 2007); accounting quality and delayed processing across firms (Chen, Khan, Kogan and Serafeim 2020); accrual reliability and pricing (Richardson, Sloan, Soliman and Tuna 2005); earnings quality and returns (Chan, Chan, Jegadeesh and Lakonishok 2001) | **Not new.** Established in accounting and finance for two decades. |
| **2. Filing timeliness predicts returns** | Bannouh, Geng and Peeters (2019): faster filers earn a premium; Brooks, Cheng, Liu and Yu (2023): earlier 10-K filers have better future earnings and returns; Givoly and Palmon (1982) on timeliness; Alford, Jones and Zmijewski (1994) and Bartov and Konchitchki (2017) on late filing | **Not new** for lateness itself. EXP-012's `lag_deterioration` (lateness against the firm's own previous four reports) is a variation, not a distinct idea. |
| **3. Amendments and restatements carry information** | Market reactions to restatement announcements (Palmrose, Richardson and Scholz 2001/2004), restatements and cost of capital (Hribar and Jenkins 2004), predicting misstatements (Dechow, Ge, Larson and Sloan 2011), earnings manipulation and enforcement (Dechow, Sloan and Sweeney 1996), firms that correct earnings (Kinney and McDaniel 1989; DeFond and Jiambalvo 1991), cost of misreporting (Karpoff, Lee and Martin 2008) | **Largely covered as events and outcomes.** These works study the announcement reaction, the causes, or the penalty. None of them found by this search uses a *running, point-in-time count of amendments* as a cross-sectional predictor or moderator. That gap is real in the sense of "not found", with the limits below. |
| **4. Constructing these variables strictly point in time from the filing registry and nothing else** | The vintage and data-revision literature is macro (Guo 2009; Forecasting in the Fog 2026; Ahmad 2026) or epidemiological (Bracher and Funk 2026); Freyberger et al. (2024) treat missing characteristics | **A measurement contribution, small.** The SEC registry carries an acceptance time for each report, so the construction is feasible and checkable. The rule "usable from the first session after acceptance" is already the repository's standard. |
| **5. Test as direct predictor *and* moderator, inside a frozen, cost-aware ML ranking pipeline, against placebos that destroy the firm link** | Machine-learning asset pricing (Gu, Kelly and Xiu 2020; Chen, Pelger and Zhu 2023), design-choice sensitivity (Lalwani et al. 2025), credibility standards (Harvey, Liu and Zhu; Hou, Xue and Zhang; Jensen, Kelly and Pedersen) | **Methodological care, not a new finding.** The design is stricter than most applied papers (preregistered, placebo-controlled, trial ledger, noise floor), which is a reason a null would be credible, not a source of novelty. |
| **6. Cross-source (vendor) disagreement or data-provider health as a signal** | Analyst dispersion (Diether, Malloy and Scherbina 2002), machine-forecast disagreement (Bali et al. 2023), the unreliability of disagreement proxies (Goulding, Harvey and Kurtovic 2026) | **Cannot be tested here.** No history of provider disagreement exists in the repository or in any source examined (`07_RESEARCH_CANDIDATES.md`); it is not claimed. |

**Update after EXP-013:** the part of the EXP-012 result that survives attribution is the count of recent amendments to periodic reports. That is the least novel component: restatements and the returns that follow them are a long-standing topic (rows 12, 13 and 13b), and the contribution is only the point-in-time state-variable form.

**Overall novelty rating: low to medium.** Components 1 and 2 are established, component 3 is covered as events, and the remainder is a careful combination plus a measurement. A reasonable referee would call the
question incremental. What would still be worth a paper is an honest, well-powered answer to a question the literature answers only in pieces; if the answer is no, that is a legitimate finding too.

**Confidence in that rating: moderate-low.** Reasons: abstract-level reading only; the retrieval found 20 of 26 known anchor works (`01_REVIEW_PROTOCOL.md`); accounting journals are reached only through
Crossref's fuzzy matching; SSRN could not be searched; and a second index (Semantic Scholar, keyless) answered only part of the probe (below). Reasoning in the other direction: the closest paper on filing lateness
(Bannouh et al.) has two recorded citations, neither on the topic, which suggests the area has had little follow-up in machine-learning pipelines, but a citation count is not proof.

## Closest works, compared (the strongest 26)

| # | Work | Read | What it does | Overlap with EXP-012 | What EXP-012 does differently |
|---|---|---|---|---|---|
| 1 | Zhang 2006, *J. Finance* | abstract | Higher information uncertainty goes with stronger price continuation and larger return predictability | Moderation of predictability by information quality | Uses filing-process variables, not size, age, volatility or dispersion; ML ranking; placebos |
| 2 | Francis, LaFond, Olsson, Schipper 2007 | abstract | Information uncertainty explains the size and profitability of post-earnings drift | Moderation, event setting | Cross-sectional ranking, not an earnings-announcement window |
| 3 | Chen, Khan, Kogan, Serafeim 2020 | abstract | Returns of good-accounting-quality firms predict those of matched poor-quality firms (delayed processing) | Accounting-quality channel | Variables are filing behaviour, not accrual-based quality |
| 4 | Richardson, Sloan, Soliman, Tuna 2005 | metadata | Reliability of accruals and the persistence and pricing of earnings | The word and concept "reliability" | Filing-process reliability, not accrual reliability |
| 5 | Chan, Chan, Jegadeesh, Lakonishok 2001 (NBER w8308) | metadata | Earnings quality and returns | Reporting quality priced | Point-in-time process variables, ML |
| 6 | Sloan 1996 | metadata | Accruals anomaly | Foundational quality-of-earnings evidence | Not tested; context |
| 7 | Bannouh, Geng, Peeters 2019 (SSRN) | abstract | Reporting lag predicts returns: faster filers earn a premium; determinants include document similarity and sentiment change | **Closest on one variable** (`filing_lag_days`) | Lag is one of five components; tested within a rich set against placebos |
| 8 | Brooks, Cheng, Liu, Yu 2023 (SSRN) | abstract | Earlier 10-K filers have better future earnings and returns | Timeliness as a predictor | As above |
| 9 | Givoly, Palmon 1982 | metadata | Timeliness of annual earnings announcements | Historical precedent | Context |
| 10 | Alford, Jones, Zmijewski 1994 | metadata | Extensions and violations of the 10-K filing requirement | Late filing as an event | Continuous state variable, not an event |
| 11 | Bartov, Konchitchki 2017 | metadata | SEC filings, deadlines and capital-market consequences | Filing-deadline effects | Context |
| 12 | Palmrose, Richardson, Scholz 2001 | metadata | Market reaction to restatement announcements | Amendments as events | Running count, cross-sectional |
| 13 | Hribar, Jenkins 2004 | metadata | Restatements, earnings revisions and cost of capital | Restatement consequences | Predictive, not explanatory |
| 13b | Frieder, Shanthikumar 2008 (SSRN) "After a Restatement: Long-Run Market and Investor Response" | title only (abstract unavailable) | Title indicates long-run market response after restatements | **Closest to the EXP-013 finding** (recent amendments predict later returns) | Amendment count as a rolling point-in-time state variable in a ranking model; not read |
| 14 | Dechow, Ge, Larson, Sloan 2011 | metadata | Predicting material accounting misstatements from public data | Predicts misstatements, the *cause* behind amendments | Predicts returns |
| 15 | Dechow, Sloan, Sweeney 1996 | metadata | Earnings manipulation and SEC enforcement | Context | Context |
| 16 | Kinney, McDaniel 1989; DeFond, Jiambalvo 1991 | metadata | Characteristics of firms that correct earnings; incidence of accounting errors | Who amends | Not about returns |
| 17 | Karpoff, Lee, Martin 2008 (SSRN version 2005) | metadata | Cost to firms of misreporting | Context | Context |
| 18 | Cohen, Malloy, Nguyen 2020 (NBER 2018) "Lazy Prices" | metadata | Changes in 10-K text predict returns | A filing-derived, point-in-time signal that investors under-use | Text, not process; not tested here |
| 19 | Loughran, McDonald 2014 | metadata | Readability of financial disclosures | Filing-derived characteristic | Not tested |
| 20 | Freyberger, Hoeppner, Neuhierl, Weber 2024 | abstract | Missing characteristics: conditional-mean imputation with weighted least squares in a GMM framework; improved out-of-sample predictability | Missingness in ML panels | Missingness kept as NaN and tested as information (`rel_missing`) |
| 21 | Guo 2009 | abstract | Real-time versus revised data weakens the consumption-wealth forecast | Point-in-time discipline | Firm-level, filing-based |
| 22 | Diether, Malloy, Scherbina 2002 | abstract | Analyst forecast dispersion predicts lower returns | Uncertainty as a predictor | Source-side, not analyst dispersion |
| 23 | Bali, Kelly, Mörke, Rahman 2023 | abstract | Dispersion across machine forecasts predicts returns | ML disagreement | Different object |
| 24 | Goulding, Harvey, Kurtovic 2026 | abstract | Investor-disagreement proxies are nearly uncorrelated | Measurement reliability of a proxy | Different object |
| 25 | Sanderink 2026 (preprint) | abstract | Two-level uncertainty and a trade/no-trade decision for cross-sectional rankers | Uncertainty-aware ranking | Reliability of the *evidence*, not of the model's output |
| 26 | Gu, Kelly, Xiu 2020; Lalwani et al. 2025 | abstract | ML return prediction; results move with design choices | The pipeline class | Frozen configuration, no search |

## What the searches could and could not show

- Broad review: 143 queries across Crossref, arXiv, NBER and (partly) OpenAlex; 12 targeted queries on restatements, late filing, amendments and XBRL quality; 18 metadata lookups for the accounting works.
- A fifth index, Semantic Scholar, was probed with eight queries aimed at the combination. It throttles keyless callers: only the first two queries were answered (`semantic_scholar_log.csv`), and a retry
  sequence was stopped on purpose. The one relevant hit is in the table above (Brooks et al. 2023); the rest were off-topic or tangential (text mining of 10-Ks, belief dispersion, volatility).
  Six of the eight queries are therefore unanswered, and this probe adds little confidence.
- **Not reached:** SSRN (automated access refused), Google Scholar, Scopus and Web of Science, subscription journal sites, non-English work. A study in an accounting journal that this search missed would
  lower the novelty rating further.
- Sensitivity against 26 known anchors: 77%. A claim that "nothing was found" is correspondingly weak.

## What would change the verdict

1. A full-text reading of Bannouh et al. (2019) and Brooks et al. (2023) to see whether they already include filing-process variables beyond lateness (reading access is the obstacle, not cost).
2. A forward-citation trace from Zhang (2006), Chen et al. (2020) and the restatement papers for machine-learning follow-ups (the OpenAlex daily allowance resets at 00:00 UTC; the script is ready).
3. A check of the accounting journals' own search (The Accounting Review, Journal of Accounting and Economics, Review of Accounting Studies) for "amendment" or "restatement" as a *return predictor*. Requires access.

## Positioning that survives this audit

- Do not describe the reliability idea or lateness as new.
- The honest contribution is: (a) point-in-time, vendor-free construction and a checkable validation of four disclosure-process variables; (b) a preregistered test that they add nothing, or something, beyond a rich
  fundamentals set, against placebos; (c) the null or the effect with its noise floor.
- A positive result would be a modest empirical paper in an applied journal. A null is still a publishable-quality negative result in a venue that values preregistered tests, but the venue list in
  `10_JOURNAL_POSITIONING.md` is for the owner to confirm.
