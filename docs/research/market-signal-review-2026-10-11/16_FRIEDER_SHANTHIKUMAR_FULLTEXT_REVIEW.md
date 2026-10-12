# Full-text review: Frieder and Shanthikumar (2008), "After a Restatement: Long-Run Market and Investor Response"

Written 2026-10-12 from the owner-supplied PDF. This is the paper the previous session named as probably decisive and could not reach (SSRN refuses automated access). Page references are the **printed page numbers**
of the draft; the PDF page is the printed page plus one (the title and abstract page is unnumbered). What the authors report is kept apart from my reading, which is marked **Reading**.

## 1. Identification and verification

| Item | Value |
|---|---|
| File | `research_papers/phase2_fulltext/pdf/ssrn-1106855.pdf` (git-ignored; not duplicated anywhere in Git) |
| Size, hash | 604,497 bytes; SHA-256 `367c1fcf4e9f358a9ca7c904b08380de92bdb79f4af7ed2fa08ee780248bb932` |
| Readability | valid PDF 1.6; text extracted with `pypdf` in the isolated environment; **60 PDF pages**: title and abstract, 36 numbered text pages, references (pp. 37-41), Tables 1-11 (pp. 42-53) and Figures 1-6 |
| Title, authors, date | "After a Restatement: Long-Run Market and Investor Response", Laura Frieder (Krannert School of Management, Purdue University) and Devin M. Shanthikumar (Harvard Business School); draft dated **July 7, 2008** |
| Stable identifier | SSRN abstract 1106855, DOI 10.2139/ssrn.1106855 (Crossref and OpenAlex records agree on title, authors and year). The PDF itself carries no SSRN stamp, so the match rests on title, authors and year |
| Status | working paper. Neither Crossref nor OpenAlex lists a journal version (checked 2026-10-12); OpenAlex shows 12 citations, 5 of them from 2022 on, none about post-restatement returns |
| Read | every page, including the tables and the figure captions; the reference list was skimmed |

## 2. What the authors did

* **Event.** The first public announcement of an earnings restatement, hand-collected from PR Newswire, Business Wire and Dow Jones News Service articles for **NYSE firms from 1993 through 2002**; 534 announcements, 113 of them
  made together with an earnings release (pp. 12-13). The sample stops in 2002 "to avoid the effects of Sarbanes Oxley" (fn. 10, p. 12). Hand collection was chosen because many GAO entries are inconsequential and many
  restatements are absent from Audit Analytics (fn. 10-11, pp. 12-13).
* **Direction and exclusions.** Each announcement is coded negative, positive or mixed by its effect on the restated statements; 58.8% are unambiguously negative (p. 14). The study sample keeps negative restatements that are
  **not caused by an accounting-rule change** (33 negative rule-change cases dropped) and drops the 10% of announcements with the least trading in the three-day window; the main sample is **238 announcements** (pp. 14-15).
  Restating firms are smaller than the average NYSE firm (mean assets 7.7 billion dollars against 27.3 billion; p. 15).
* **Windows** (trading days relative to day 0): (-21,-2), (-1,+1), (2,21), (22,63), (64,126), (127,252).
* **Return adjustments** (pp. 5-7): raw; Daniel-Grinblatt-Titman-Wermers characteristic-adjusted (125 size, book-to-market and momentum portfolios); a matched-firm adjustment (same size and book-to-market portfolio,
  nearest on returns over (-252,-22), worst 1% of matches dropped); a firm-specific Fama-French-Carhart adjustment with loadings from five years of daily returns ending day -22; and **calendar-time portfolios** per window
  (value-weighted, equal-weighted as a check) regressed on the four factors (p. 7). Delisting returns from CRSP, with -0.3 substituted when missing and -1 as a check (fn. 16, p. 16). Standard errors are robust to
  heteroskedasticity and arbitrary within-firm correlation (notes to Tables 5-7).
* **Further evidence:** analyst forecast error and dispersion against a matched sample (IBES; pp. 16-17, 22-26), subsamples by cause, SEC involvement and firm characteristics (pp. 26-29), and quarterly 13F ownership by
  Bushee's transient, dedicated and quasi-indexing institutions (pp. 29-35).

## 3. What the authors report

| Result | Number (page or table) |
|---|---|
| Raw cumulative return, N = 238 | (-21,-2) -4.58% (t -3.07); (-1,+1) -3.78% (t -3.48); (2,21) -1.14%; (22,63) +1.97%; **(64,126) +4.29% (t 2.16)**; (127,252) +0.81% (t 0.30) (Table 5, p. 46) |
| Characteristic-adjusted | (64,126) **+4.96%**, t 2.60, N = 202; (127,252) +0.97%, t 0.36 (Table 6A, p. 47) |
| Matched-firm | (64,126) **+4.50%**, t 1.98, N = 194; (127,252) -2.32%, t -0.72 (Table 6B) |
| Firm-specific four-factor | (64,126) **+4.30%**, t 1.87, N = 227; (127,252) -2.78%, t -0.85 (Table 6C). The text (p. 19) quotes 4.96% for this window; the table says 4.30%, and the table is used here |
| Calendar-time value-weighted four-factor alpha, window (64,126) | 0.1075 in the table's daily units, t 2.38, which the authors convert to about 7% over three months; (127,252) -0.0346, t -1.14 (Table 7C, p. 48). With at least three stocks in the portfolio the alpha is 0.085 (t 1.79; 5.5%); equal-weighted 0.087 (t 2.25; 5.6%) (pp. 20-21) |
| Windows (2,21), (22,63) and (127,252) | not significant under any adjustment (Tables 5-7) |
| Other restatement types | positive restatements show no pattern; rule-change restatements show positive raw and market-adjusted returns from day 2 (fn. 21, p. 22) |
| Risk | return volatility is not higher in (64,126) than in the mirror window before; dividend omissions and write-offs, comparable shocks, are followed by negative drift in other studies (p. 21); the momentum loading becomes more negative after the restatement (-0.4585 against -0.1950; p. 20) |
| Timing | the positive return is not concentrated around the next earnings announcements (untabulated; p. 26) |
| Analysts | dispersion rises after the announcement and falls over months 3-5; forecast error does not turn overly negative (pp. 23-25, Figure 2, Table 8); in the 3-6 month window, larger falls in dispersion go with higher returns (p. 25) |
| Subsamples | similar before 2000 and in 2000-2002; far larger for SEC involvement (raw 17.8%, n = 21; 23.2% for investigations, n = 14; 3.1% where the SEC is not mentioned; p. 27); stronger for growth stocks (p. 29). Of 92 subsample-by-measure estimates only 4 are negative, none significant (fn. 22, p. 27); these are not independent tests |
| Institutions | transient and quasi-indexing institutions sell before the announcement and buy after it; dedicated institutions sell throughout; dedicated trading predicts returns, the others' trading does not or predicts negatively later (pp. 29-35, Tables 10-11) |

**Authors' conclusion (pp. 35-36):** despite negative returns before and at the announcement, restating NYSE firms earn significantly positive abnormal returns of more than 4% in months 3-6, which the authors attribute to
the resolution of information risk rather than to overreaction; they find no negative post-announcement drift.

## 4. Scope and limits, as stated and as apparent

**Stated by the authors:** NYSE firms only, 1993-2002, pre-Sarbanes-Oxley, with the extension to later years left to future work (pp. 12, 36); NYSE firms are larger and more stable than the market (fn. 10, p. 12), which the authors expect to
mute their results, while fn. 20 (p. 18) suggests that such firms may recover faster and more strongly than the universe of stocks; portfolio returns are before transaction costs (p. 20); ownership is observed quarterly, so trades cannot be dated within a quarter (fn. 19, p. 17); the paper cites
contrary evidence, negative market-adjusted returns over days (2,252) in Scholz (2008) and extended poor performance after restatements for heavily shorted firms in Desai et al. (2006) (fn. 20, p. 18; neither is read here).

**Reading (apparent from the design):**
* The only reliably non-zero post-announcement window is (64,126); six windows and three adjustments are examined without a multiplicity adjustment, and significance sits between the 1% and 10% levels with 194 to 227 events.
* Events are first announcements, which usually precede any amended filing; the paper says nothing about the filing of a 10-K/A or 10-Q/A, nor about restatements disclosed only inside a later periodic report.
* Cross-sectional dependence between events in the same calendar month is handled only through the calendar-time portfolios.
* The matched-firm benchmark conditions on past-year returns, which is a deliberate and strong control; the characteristic benchmark does not.
* A working paper from 2008 with one internal inconsistency (4.96% in the text, 4.30% in Table 6C). It has had no journal review that I can find.

## 5. How it relates to the treatments in EXP-012, EXP-013 and EXP-014

The treatments are **not interchangeable**, and this paper must not be read as evidence about ours.

| Dimension | Frieder and Shanthikumar | OmniSignal (EXP-012/013/014) |
|---|---|---|
| Event | first press-release announcement of a negative, non-rule-change earnings restatement | amendment to a periodic report (10-K/A, 10-Q/A and transition forms) in the SEC Financial Statement Data Sets |
| Content | hand-coded direction of the effect on income or revenue | numeric change of more than 1% in revenue, net income, assets, liabilities, equity or operating cash flow versus the previous version (category `core`); unchanged-number and unclassifiable amendments kept separate |
| Time zero | the announcement | the amendment's own acceptance time, usable from the first session whose close follows it |
| Window | six event windows; the finding is the 3-6 month window | a state variable: flagged for the trailing 730 days, with event-time bins as a diagnostic |
| Estimand | average abnormal return of the event firms; calendar-time alpha | coefficient on next-month cross-sectional return rank, conditional on date-by-sector effects and established controls; incremental rank IC and portfolio value separately |
| Population, era | NYSE, 1993-2002, large and stable firms | liquidity ranks 251-1,000 (EXP-014) and the top 250 (EXP-012/013), 2014-2025, delisted names included |
| Inference | firm-robust t statistics | wild-cluster bootstrap with few treated firms, two-way clustering, leave-out and placebo checks |

An earnings restatement, an amendment to a periodic report, an XBRL-bearing amendment and a value-changing amendment are four different objects. Many value-changing amendments follow an earlier announcement (an Item 4.02 8-K
or a press release) by weeks or months; some restatements never produce a 10-K/A; many amendments add exhibits or Part III information.

## 6. Does it weaken the novelty claim?

**Reading.** It changes the claim in two ways and weakens it in neither sense that matters most.

1. **It removes a premise I had written down.** My Phase II documents said "the sign is prior art", resting on an abstract of Gondhalekar, Joshi and McKendall (2012) that reports negative abnormal returns for four years after
   restatement announcements. This paper reports, for NYSE firms before Sarbanes-Oxley, a **rebound** in months 3-6 and **no** negative drift, and cites two studies that find the opposite for other samples. The long-run
   direction after restatements is therefore **contested and sample-dependent**, not established. "The sign is known" must be replaced by "the sign is disputed in event studies of restatement announcements, and unmeasured for
   content-classified amendments in the XBRL era".
2. **It confirms that the question has an old literature**, so a new paper cannot present long-run restatement returns as unexplored. What would be new has to be the estimand and the setting: a point-in-time, content-
   classified, cross-sectional test in the modern filing regime, with valid inference for few treated firms and an independent sample. That was already my assessment; the paper makes it firmer.

It does not make the amendment signal redundant: its treatment, era, population, horizon and estimand all differ (section 5), and a rebound that begins three months after a first announcement need not exist for
amendments that arrive later, are filtered on content and are observed in smaller, less stable firms.

## 7. Consequences for EXP-014 (made before registration)

1. **A competing prediction is now written into the protocol.** If the rebound exists in modern data, the coefficient on a flagged state pooled over 730 days could be small, positive, or negative early and positive later.
   EXP-014 therefore reports the core-amendment coefficient in four horizon bins after availability (a core amendment first usable 0-89, 90-179, 180-364 or 365-729 calendar days before the decision day), as a pre-specified descriptive
   secondary analysis (S11, implemented in `src/quant/study/exp014.py` and tested), so that a rebound in the days 64-126 range, about 90-180 calendar days, is visible if it is there. S12 (liquidity halves) was added in the same step for a reason from the design literature, not from this paper.
2. **A significant opposite sign gets its own label.** A positive H1 coefficient with a two-sided wild-cluster p below 0.05 is reported as **REVERSED** (implemented in `decide`, tested), not folded into NOT_REPLICATED. It would be evidence in the direction of
   this paper. It is descriptive and uncorrected and cannot create SURVIVES or FRAGILE.
3. **The mechanism is not assumed.** The paper's information-risk explanation predicts positive later returns; a negative association would instead point to persistent distress or quality, which the within-firm gate R7 and
   the event-time diagnostic are built to separate.

## 8. Limits of this review

One working paper, read in full; the studies it cites (Scholz 2008, Desai et al. 2006, Palmrose et al. 2004, Hribar, Jenkins and Wang 2004) are known only through its text. No data from the paper are reproducible from the
draft (the hand-coded sample is not published). Nothing here supports or refutes a result on the amendment signal itself.
