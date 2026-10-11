#!/usr/bin/env python3
"""Write docs/EXP_013_PREREGISTRATION.md from the live definition (so the document cannot disagree with the code it registers).

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/make_prereg_doc_013.py

Inputs: src/quant/study/exp013.py (definition and fingerprint) and experiments/EXP-012 (the realised standard errors used for the sensitivity paragraph).
Not covered by the fingerprint: the registered object is the document it writes and the method files it lists.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from src.quant.study import exp013  # noqa: E402


def main() -> None:
    fp = exp013.definition_fingerprint(REPO)
    paired = {r["contrast"]: r for r in csv.DictReader((REPO / "experiments/EXP-012/paired_tests.csv").open())}
    se = {k: abs(float(paired[k]["mean_diff"]) / float(paired[k]["hac_t"])) for k in ("T1", "T2", "T3")}
    lo, hi = (1.6449 + 0.8416) * se["T1"], (2.1280 + 0.8416) * se["T1"]
    reh = json.loads((REPO / "docs/research/market-signal-review-2026-10-11/validation/rehearsal_summary_013.json").read_text())
    chance = reh["unconditional_shares_by_chance"]
    top = max(max(abs(v["add_share"]), abs(v["drop_share"])) for v in chance.values())
    arms = "\n".join(f"| {k} | {len(v['features'])} | {v['note']}{' (' + str(len(v.get('seeds', (0,)))) + ' fits)' if v.get('seeds') else ''} |" for k, v in exp013.ARMS.items())
    family = "\n".join(f"| {k} | {l} - {r} |" for k, (l, r) in exp013.FAMILY.items())
    rule = "\n".join(f"- **{k}**: {v}" for k, v in exp013.ATTRIBUTION_RULE.items() if k in ("gain", "add_share", "drop_share", "CARRIES", "SHARES", "NOT_CARRYING", "note"))
    methods = "\n".join(f"- `{m}`" for m in exp013.METHOD_SOURCES)
    doc = f"""# EXP-013 preregistration - which columns carry the EXP-012 T1 gain?

Definition fingerprint: `{fp}`

Parent: EXP-012. Status: **EXPLORATORY - validation folds only - holdout sealed - promotion not assessed.** This document is committed and pushed to the research branch before any arm is fit; the
fingerprint is the SHA-256 of the canonical definition (`src/quant/study/exp013.py`, `DEFINITION`) and of the bytes of every method file in section 12. If the definition or a method file changes after
registration, the gate refuses to run.

## 1. Why this study, and what it is not

EXP-012 returned T1 SUPPORTED (adding six point-in-time columns to the rich set raised ridge Rank IC by +0.00515, Holm p 0.011) with caveats set out in `docs/EXP_012_RESULTS.md`: the gain is negative in the last two
validation years, the shifted placebo keeps about half of it, the boosted model gains nothing, and the six columns are not equal (four are ranks of filing-process variables, one is a count of missing fundamentals,
one is a composite that contains two variables already in the rich set). The question of which of them the gain depends on decides whether T1 is about disclosure behaviour or about something else. This study asks only that.

It is **not** a confirmation of T1, makes no claim of new alpha, and does not use the holdout. The eight folds have been looked at by EXP-006 to EXP-012 (1,029 trials were already on the ledger); this adds
34 ridge fits (16 arms and 18 placebo fits), 3 adjusted contrasts and 22 descriptive ones, and is counted as one more look.

Disclosed before registration: the coefficients of the final EXP-012 A5 model (fitted on all pre-holdout rows) were read. In absolute size the composite ranks 3rd of 82, lateness deterioration 4th, periodic-report
count 14th, amendments in two years 18th, missing-fundamentals count 36th and latest-report-amended 47th. These are in-sample coefficients of a collinear ridge model, not out-of-sample evidence.

## 2. Data

No new data. The frozen rich panel `{exp013.exp011.RICH_DATASET_ID}`, the label `fwd_rank_21`, the eight recorded folds, ridge alpha 10, the EXP-012 reliability table `{exp013.exp012.rel.VERSION}` (verified by hash before the
run), and the EXP-012 code for placebos and paired inference.

## 3. Arms

All ridge, alpha 10, deterministic. B1 and B5 reproduce EXP-012's A1 and A5 and are gates. Placebo arms replace the named columns of the corresponding add arm with a within-date permutation across firms
(five seeds, averaged) or a 252-session shift within each firm.

| Arm | Features | Description |
|---|---|---|
{arms}

## 4. Contrasts

Descriptive family, adjusted together with Holm (the only adjustment; the rest are descriptive and unadjusted): what each group adds to the rich set.

| Contrast | Difference |
|---|---|
{family}

Descriptive: each group against its permuted and shifted placebo (`P_vs_perm`, `P_vs_shift`, and likewise for M and U); each group's removal from B5 (`P_drop`, `M_drop`, `U_drop`); each single column added
(`add_<name>`) and removed (`drop_<name>`); and the total (B5 - B1). Groups: P the four filing-process ranks, M the missing-fundamentals count, U the composite.

## 5. Attribution rule (fixed before any result)

{rule}

## 6. Inference

The same as EXP-012: mean over dates of the paired difference of per-date Spearman Rank ICs; Newey-West with 4 lags; one-sided normal p; 95% moving-block bootstrap interval (block {exp013.exp012.BOOTSTRAP_BLOCK},
{exp013.exp012.BOOTSTRAP_DRAWS} draws, seed {exp013.exp012.BOOTSTRAP_SEED}); positive-fold counts. Economics (the frozen portfolio at 10 bp) are reported for every arm as exploratory and carry no inference.

## 7. What this design can resolve

In EXP-012 the realised standard errors of the paired differences were {se['T1']:.4f} (T1), {se['T2']:.4f} (T2) and {se['T3']:.4f} (T3). At about 0.002 per contrast, the smallest difference detectable with
80% power is {lo:.4f} for a single test and {hi:.4f} at the strictest Holm step. The whole T1 gain is +0.00515, so the per-column contributions (a few thousandths at most) are below what a single descriptive contrast
can resolve: **a NOT_CARRYING label may reflect low power and not absence.** The labels are a way of reading the table, not tests.

A rehearsal of the whole pipeline (all {reh['fits']} fits and the analysis) on a label shuffled across firms within each date (seed 20261012) completed in {reh['wall_seconds']:.0f} s with every prediction finite and every group
labelled {', '.join(sorted(set(reh['labels'].values())))}, as it must in a world with no signal (`docs/research/market-signal-review-2026-10-11/validation/rehearsal_summary_013.json`). The same rehearsal showed why the rule
needs the resolvability condition: the unconditional shares of the noise gain reached {top:.2f} by chance, and a first draft that labelled on shares alone returned SHARES for two groups.

## 8. Expected outcome, declared in advance

Reading the coefficients above, the prior expectation is that the composite (U) and the lateness deterioration (within P) carry most of the gain, the missing-fundamentals count (M) little, and the amendment ranks almost
none, because those are nearly constant. A CARRIES for U would indicate that the gain largely re-weights the lateness and staleness information already in the rich set and studied in the timeliness literature; a
CARRIES for M would indicate a coverage or age proxy; no CARRIES at all would indicate that the gain is spread across the block or arises from combinations of columns. None of these changes the registered analysis.

## 9. Acceptance gates before any contrast is computed

1. B1 and B5 reproduce EXP-012's A1 and A5 mean Rank IC to 1e-9 (enforced in code, unit-tested; the run aborts otherwise).
2. Every out-of-sample prediction is finite; no decision date is later than 2025-05-09.
3. The reliability table's sha256 equals its manifest; the parent artifacts verify by hash; the holdout guard reports SEALED.

## 10. Not claimed

No confirmation of T1; no claim about the holdout, other universes or horizons; no tuning of any parameter after this registration; nothing promoted. The labels are descriptive.

## 11. Outputs and reproduction

`experiments/EXP-013/`: `definition.json`, `config.json`, `per_arm_metrics.csv`, `fold_metrics.csv`, `paired_tests.csv`, `attribution.json`, `manifest.json`, `checkpoints/` (git-ignored).

```bash
.venv/bin/python -m scripts.quant.exp013 fingerprint        # must equal the fingerprint above
.venv/bin/python -m scripts.quant.exp013 gate               # refuses unless registered and pushed
.venv/bin/python -m scripts.quant.exp013 rehearse           # whole pipeline on a label shuffled within date (no result)
.venv/bin/python -m scripts.quant.exp013 run --workers 6    # the study
```

## 12. Method files covered by the fingerprint

{methods}
"""
    (REPO / "docs/EXP_013_PREREGISTRATION.md").write_text(doc)
    print("fingerprint", fp)


if __name__ == "__main__":
    main()
