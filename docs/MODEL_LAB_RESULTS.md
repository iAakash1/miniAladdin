# MODEL-LAB-001 results

Status: **SMOKE GATE IN PROGRESS — EXPLORATORY**

Dataset: Rich PIT v2 `ds-richpit2-6368cccdb94c62d0`, using only the pinned
`F0_UNAFFECTED_BASELINE_26` block. Revenue-affected feature sets are blocked.
The final holdout is sealed and untouched. EXP-012 is blocked and not prepared.

Initial development smoke attempts were retained as `INVALID` because the first
inner-window geometry produced only one split and later because method code was
not yet committed. They are implementation evidence, not model evidence.

Authoritative counts and trial metrics are generated into
`data/manifests/model_lab_summary.json` after each resumable run and rendered in
Quant Lab. This document is updated only from that ledger; negative results and
runtime failures are not removed.

No candidate is eligible or shortlisted during the smoke stage.
