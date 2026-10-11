# Journal positioning

Written 2026-10-12. Status: **a map for the owner's decision, not a recommendation to submit.** Two things the brief asked for could not be done from primary sources and are stated
as such: ranking quartiles were not verified (section 2), and one publisher's AI policy was not retrieved (section 4).

## 1. What the paper would be

The paper is whatever EXP-012 returns. The registered study is exploratory, uses validation folds only, and the prior-art audit (`06_PRIOR_ART_AND_NOVELTY.md`) rates its novelty low to
medium. Three outcomes are possible, and the venue list differs for each:

| Outcome | What the paper is | Realistic venue type |
|---|---|---|
| Null on T1 to T3 (the most likely, given a thin new block and about 250 liquid names) | A preregistered, placebo-controlled negative result: disclosure-process reliability adds nothing to a rich point-in-time set | Venues that value rigor, replication or null results |
| Supported, but fragile or small | A modest empirical note with an honest noise floor | Applied empirical finance and financial-analysis journals |
| Supported and robust | A contribution to the information-quality literature, still incremental | Applied empirical finance or accounting journals |

A top-tier finance outcome (Journal of Finance, Journal of Financial Economics, Review of Financial Studies) is not a realistic target for this design and is not proposed.

## 2. Candidate venues (to be checked by the owner before any submission)

Quartiles could **not** be verified. SCImago answered automated requests with HTTP 403 and was not worked around; Journal Citation Reports is subscription-only. The single value found,
on a secondary aggregator, was Journal of Empirical Finance in Finance with quartile Q1 and an SJR of about 0.94 for a year ending in 2025; it is unconfirmed. Every other quartile
below is "not checked". A quartile is also not a reason to choose a venue; fit is.

| Venue | Publisher | Why it could fit | Ranking | Registered or null-result friendly (from search snippets; verify) |
|---|---|---|---|---|
| Journal of Empirical Finance | Elsevier | applied empirical asset pricing and forecasting | Q1 (Finance) per one secondary source, unverified | not known |
| Journal of Banking & Finance | Elsevier | broad empirical finance | not checked | not known |
| International Review of Financial Analysis | Elsevier | applied financial analysis and data-driven methods | not checked | not known |
| Finance Research Letters | Elsevier | short empirical notes | not checked | not known |
| Pacific-Basin Finance Journal; Journal of Financial Markets | Elsevier | markets and microstructure-adjacent empirical work | not checked | not known |
| Quantitative Finance | Taylor and Francis | methods in quantitative finance | not checked | not known |
| Journal of Accounting Research | Wiley | disclosure and reporting quality; a registered-reports format has been used for conference issues | not checked | yes, for past conference issues (search snippet) |
| Review of Financial Studies | Oxford University Press | ran registered-report issues in 2018 and 2019 on set themes (search snippet) | not checked | historical only |
| Accounting Open | Elsevier, American Accounting Association | states openness to replications and null results (publisher listing) | not checked | yes, by its stated aim |
| Journal of Behavioral and Experimental Finance | Elsevier | offers registered reports (publisher guidelines), but its scope is behavioural | not checked | yes, but the scope does not fit |
| Critical Finance Review | independent | its remit includes replications; whether it takes null results was **not confirmed** by this search | not checked | not confirmed |

Not proposed: Review of Accounting Studies, Journal of Accounting and Economics, Contemporary Accounting Research (novelty bar above what the audit supports), and Expert Systems with
Applications (machine-learning breadth, weaker fit with an information-economics question).

## 3. Everything the submission would need that the repository already has, and what it lacks

| Item | State |
|---|---|
| Preregistration committed before the run, with a content fingerprint | yes: `docs/EXP_012_PREREGISTRATION.md`, enforced by `prereg_gate` |
| Independent registry timestamp | **no**: a GitHub commit is not a neutral registry. OSF or a finance registry would add one; creating an account is the owner's decision |
| Data availability | SEC public data and a derived table that can be rebuilt in seconds; the price panel comes from DoltHub community data whose terms were never reviewed (`datasets.csv` L04), which must be resolved before releasing any derived dataset |
| Code availability | yes, in the repository; the research branch is pushed |
| Prior art and novelty claim stated honestly | yes, `06_PRIOR_ART_AND_NOVELTY.md` |
| Full-text reading of the closest works | **no**: abstract and metadata only; required before a literature section is written |
| Conflict of interest | the author owns the product the research serves; to be declared |

## 4. Generative-AI disclosure: a flagged conflict

The repository rule is that no automated tool is named as author, co-author or contributor in commits, source, documentation or metadata. That rule governs the repository. **A journal declaration is a
different document with a different purpose, and the repository rule cannot justify leaving a required disclosure out or making a false one.** The screening protocol (`01_REVIEW_PROTOCOL.md`) records that
title-and-abstract screening and classification of 2,011 records was done by automated agents applying a written rubric, and the code and text of this work were prepared with automated assistance. Whether
that triggers a declaration depends on the chosen journal's policy, summarised below; the owner has to decide the wording and confirm the facts.

| Publisher | Policy page (fetched 2026-10-12) | What it requires, in brief |
|---|---|---|
| Elsevier | Generative AI policies for journals; page says updated June 2026 | A declaration immediately before the references naming the tool, the reason, and that the authors reviewed and take responsibility; AI cannot be an author; AI used in the research process (analysis, code, selecting or collating references) must be described in Methods with tool, version and developer, and AI use to select or generate references must be declared |
| Wiley | Ethics guidelines; "Last updated: July 2026" | Disclosure at submission and in the article when AI substantially edits, develops or translates content; AI cannot be an author; authors remain responsible for all claims, citations and analyses; grammar and spelling tools are exempt |
| Taylor and Francis | AI policy; no date shown (2026 footer) | Authors must acknowledge any use of generative AI, with the tool's full name and version, how it was used and why; AI must not be listed as an author; "literature classification" and "coding assistance" are listed as supported uses; no fabricated or substituted data |
| Springer Nature | **not retrieved**: the policy page redirected to an authorisation page | to be read directly |
| Oxford University Press, Journal of Accounting Research, others | not checked | to be read directly |

What this means in practice, for the owner to decide:

1. The Methods section would need to describe the automated screening truthfully: what performed it, the version, the rubric, the agreement statistics in `01_REVIEW_PROTOCOL.md`, and the classifier-assisted triage of the
   300 unscreened records.
2. A declaration for assisted preparation of code and text would be needed where the chosen journal asks for it, and any statement that a human reviewed the output should be made only if that review took place. The
   bibliography relations were written from abstracts and must be checked against the papers by a person before they are relied on.
3. None of these policies requires, or is served by, crediting an automated tool as an author, and none conflicts with keeping the repository free of attribution. The two just have to be consistent with what was done.

## 5. Before any submission

- Read the target journal's current author guidelines and AI policy yourself, and check its ranking in SCImago and Journal Citation Reports for the current year.
- Replace abstract-level statements about the closest works with full-text reading (`06_PRIOR_ART_AND_NOVELTY.md`, "What would change the verdict").
- Re-run the final numbers from the committed code, quote the registration commit, and state in the paper that the study was exploratory on folds already examined by earlier experiments (trial ledger: 1,029 cumulative trials before this study).
- Resolve the DoltHub terms (L04 to L06) and decide on an independent registry entry.
