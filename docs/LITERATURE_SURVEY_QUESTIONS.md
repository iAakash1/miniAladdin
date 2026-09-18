# Literature survey questions

> The survey itself has not happened. This document defines what it needs to
> answer, so the person who does it — a future pass of this project, or the
> student themself in a dedicated literature phase — knows what "done" looks
> like before starting. **No paper, author, dataset, or finding is named
> below.** Naming one without having actually read and verified it would be
> exactly the fabrication this document exists to avoid, and a wrong citation
> in a final-year project is a worse outcome than an honestly incomplete
> reference list.

## How to use this list

Each question should be answered with: the actual papers/sources found,
what each claims, whether the claim was tested on data/costs/universe
comparable to this project's (US-listed common equities, realistic
transaction costs, walk-forward evaluation), and — critically — whether the
result replicated or has been challenged since. A survey that reports only
positive results from one search pass is not a survey; it is a citation list
assembled to support a conclusion already reached.

## Questions

1. What target formulations currently perform best for cross-sectional stock
   selection — point regression on forward return, quantile regression,
   learning-to-rank objectives, or classification of a binned outcome? Which
   of these has the most support from work that evaluates *net of realistic
   costs*, not just raw predictive accuracy?

2. Which recent work applies learning-to-rank methods (as opposed to return
   regression) specifically to cross-sectional equity selection, and what
   was the reported improvement, if any, once costs and multiple-testing
   correction are accounted for?

3. Which datasets or feature families show *incremental* signal after costs
   — i.e., not "this feature correlates with returns" but "this feature adds
   information beyond what the existing panel already captures, net of what
   it costs to trade on"? This project's own EXP-004/EXP-005 findings (every
   additional source tested made the model worse) are the standard this
   question needs to be checked against, not assumed to generalise from.

4. Which published work uses analyst estimate revisions (EPS, revenue,
   price-target) as a predictive feature for cross-sectional selection, and
   over what universe and holding period?

5. Which published work uses options-derived predictors (implied
   volatility, skew, term structure, put/call activity) for equity selection
   rather than for volatility or options-pricing research specifically?

6. Which published work uses insider transaction or institutional-ownership
   data as a selection signal, and does the reported edge survive after
   accounting for the lag between an actual transaction and its public
   disclosure?

7. Which methods for sector- or size-neutralising a cross-sectional signal
   are standard in this literature, and which of them is appropriate for a
   universe this project's size (tens, not thousands, of names) rather than
   requiring a broad-market cross-section to estimate reliably?

8. Which methods explicitly optimise for turnover or transaction cost during
   training, rather than measuring cost sensitivity only after the fact —
   and do any report the net-of-cost improvement this project's own Phase J
   research question (`NEXT_QUANT_RESEARCH_PLAN.md`) is asking about?

9. Which recent models remain robust specifically in **walk-forward**
   evaluation (not cross-validation on shuffled data, which leaks temporal
   information for a time-series problem) — and separately, which models
   that reported strong cross-validated results were later shown not to hold
   up walk-forward?

10. Which datasets used in this literature are publicly or academically
    accessible (not proprietary vendor feeds this project has no budget for),
    and which of those overlap with data sources this project already has
    access to (FRED, SEC XBRL, the existing market-data providers)?

11. Of the datasets in question 10, which can legally and practically be used
    in a student research project — licensing terms, academic-use
    provisions, and any restriction on publishing results derived from them?

12. Which approaches reported positive results before costs but were shown to
    fail, or were not retested, after realistic transaction costs and
    execution lag were applied? This project's own EXP-006 result (weak
    detectable signal, cost-adjusted promotion still blocked) is exactly this
    shape of finding, and the survey should look specifically for how common
    it is in the broader literature rather than treating it as unusual.

13. Which of the results found were tested on a universe comparable to this
    project's (US-listed common equities, similar market-cap range and
    liquidity) rather than on a broader or differently-composed universe
    where the same feature might not transfer?

14. Which papers publish code, data, or a fully specified methodology
    sufficient to attempt a reproduction — as opposed to reporting a result
    with no path to checking it?

15. Given the remaining timeline of this project, which one or two of the
    approaches found are actually feasible to implement and evaluate
    properly (with the same walk-forward and multiple-testing discipline as
    the existing research ledger) before the project's final submission,
    as opposed to being correct-but-out-of-scope for a B.Tech final-year
    timeline?

## What "done" looks like

A completed survey answers each question above with real, checked sources —
or states plainly that the search did not find a good answer to a particular
question, which is itself a useful and honest finding. It feeds directly into
prioritising `NEXT_QUANT_RESEARCH_PLAN.md`'s ten candidate directions: the
survey's job is to say which of those ten has the strongest existing evidence
behind it, not to introduce new directions the plan does not already name.
