# Path A versus Path B: which paper, on the evidence

Status: **decision written 2026-10-12 before EXP-014 is run; the choice of primary path is conditional on the stated triggers. Revised later the same day after the full-text reading of Frieder and Shanthikumar and the 2022 to 2026 update (`16_...`, `17_...`): the premise "the sign is prior art" is withdrawn, the REVERSED outcome is added to the trigger table, and nothing else in the decision changed.**

* **Path A - reliability-aware financial signals.** Does the reliability of the filings behind a signal (here: amendments that change the reported numbers) carry information beyond established characteristics?
* **Path B - reproducible point-in-time evaluation of OmniSignal's live scorer.** Can the scorer that is deployed be evaluated honestly on past dates, and what does it earn?

The two are kept apart: Path B concerns the product's own composite and its inputs, Path A concerns a research variable and the research stack. Evidence about one does not transfer to the other without a bridging
experiment (`05_OMNISIGNAL_SIGNAL_AUDIT.md`, finding 1).

## 1. Comparison

| Criterion | Path A | Path B |
|---|---|---|
| Closest papers (read level in `12_FULLTEXT_REVIEW_AND_NOVELTY_MATRIX.md`) | Gondhalekar et al. 2012 (AB), Irani and Xu 2011 (AB), Files et al. 2009 (AB), Desai et al. 2006 (AB), Frieder and Shanthikumar 2008 (FT, all pages), Ghosh et al. 2025/2026 (FT, in part), Zhu 2026 and Ahn 2026 (AB), Cohen et al. 2020 (FT), Chan et al. 2006 (FT) | Liu 2026 (AB), Yang and Zhu 2026 (AB), Perignon et al. 2024 (AB), Bracher and Funk 2026 (FT), Daniel et al. 2009 (FT), Glasserman and Lin 2023 (FT), Benhenda 2026 (FT), Sanderink 2026 (FT) |
| Exact gap | A point-in-time, content-classified, cross-sectional test of the amendment variable on an independent firm sample with valid inference for few treated firms, and its cost-aware value | A replayable evaluation protocol for a deployed multi-factor scorer whose inputs are provider snapshots that were never archived |
| Data feasibility and licensing | SEC filings are public records (acceptance times validated; `data/manifests/edgar_filings_v1.json`); FSDS public; prices from a public Dolt dataset whose redistribution terms are unreviewed, so derived statistics are published, prices are not | Only price-derived parts can be replayed on past dates (45% of the composite weight, provider equivalence unverified); everything else needs a prospective archive and each provider's terms |
| Testable with real data now | **Yes.** Done on the discovery sample; EXP-014 tests an independent sample | **Partly.** Price-derived sleeves yes; fundamentals, news and macro no |
| Baseline | Conventional ridge and boosted rankings on 76 point-in-time features; explicit controls | The repository's conventional models; random strategies on the same data (Daniel et al.) |
| Falsification | Placebos (permuted and shifted blocks), event-time leads, comparator amendments, leave-out of firms, years and sectors, label-shuffled rehearsal | Shifted timestamps; random constrained portfolios |
| Compute | Small (minutes to an hour on a laptop) | Small for the replayable part; prospective capture costs time, not compute |
| Publishability (no ranking claimed) | Incremental. The sign is **contested** (a positive rebound in Frieder and Shanthikumar, negative drift in other work); a rigorous preregistered independent test with a data-quality finding is a defensible contribution for an applied empirical-finance or accounting-data audience **whatever the sign**, and a clean failure is a defensible replication note. No venue ranking is claimed | Methodology and software: a documented archive and a worked audit of what cannot be replayed; low as an empirical paper until a year of prospective data exists |

## 2. Evidence so far

* Path A, discovery sample (`validation/phase2_*`): the association is real by every inference that respects firm dependence (wild-cluster bootstrap p of about 1e-4 for 18 treated firms; still significant
  after removing the 10 most influential), lives in amendments that change the numbers (-0.245 rank units against -0.049 for unchanged-number amendments), and is not a machine-learning gain (the paired
  rank-IC increment is fragile). The sample is the one that produced the finding, so none of this is confirmation.
* Path B: the replay audit (`13_PIT_ARCHIVE_DESIGN.md`) shows that 40% of the composite's weight cannot be evaluated on past dates by any method available today.

## 3. Decision

**Primary: Path A, conditional on EXP-014.** Triggers fixed now:

| EXP-014 outcome | Primary paper | Path B |
|---|---|---|
| SURVIVES | Path A: independent replication of the amendment signal, the split by content, the timestamp finding, the negative-or-small economic result |
| REVERSED | Path A re-framed: the registered direction fails and the opposite sign appears (the rebound of Frieder and Shanthikumar is the prior); the age bins S11 show where in time; any further claim needs a new registered study, not an edit of this one | Software and audit note (archive + replay table), separate |
| FRAGILE | Path A as a measured, qualified result: where the association holds and where it does not | as above |
| NOT_REPLICATED or INCONCLUSIVE | Path A as a replication study with the negative result as the finding, plus the data-quality contribution; no claim of a signal | Path B becomes the main forward-looking contribution (prospective archive and a pre-registered evaluation plan for the price-derived sleeves) |

Path B is not abandoned in any branch: the archive is built, and a bridging experiment on the price-derived sleeves remains the cheapest honest statement the product can make about its own score. It is not
started here because the brief for this phase forbids production changes and a bridging experiment needs its own preregistration.
