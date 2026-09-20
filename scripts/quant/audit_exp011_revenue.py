"""Build the outcome-blind EXP-011 revenue-mapping impact audit."""

from __future__ import annotations

import json
from pathlib import Path

from src.quant.pit.revenue_mapping_audit import run
from src.quant.pit.sec_foundation import atomic_json

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data/manifests/exp011_revenue_mapping_impact.json"
DOCUMENT = ROOT / "docs/EXP_011_REVENUE_MAPPING_IMPACT_AUDIT.md"


def _table(rows: dict, first: str) -> str:
    lines = [f"| {first} | Rows | Affected | Share |", "|---|---:|---:|---:|"]
    for name, item in rows.items():
        lines.append(f"| {name} | {item['rows']:,} | {item['affected']:,} | {item['share']:.4%} |")
    return "\n".join(lines)


def render(report: dict) -> str:
    frozen = report["frozen_population"]
    rec = report["reconciliation"]
    snap = report["snapshot_impact"]
    impact = report["feature_impact"]
    ratio = rec["corrected_to_frozen_ratio"]
    feature_lines = ["| Feature | Changed cells | Row share | Median | p95 | Max | Dependency |",
                     "|---|---:|---:|---:|---:|---:|---|"]
    for feature, item in impact["by_feature"].items():
        fmt = lambda value: "—" if value is None else f"{value:.6f}"
        feature_lines.append(
            f"| `{feature}` | {item['count']:,} | {item['share']:.4%} | {fmt(item['median_absolute_change'])} | "
            f"{fmt(item['p95_absolute_change'])} | {fmt(item['max_absolute_change'])} | {item['revenue_dependency'] or 'rank propagation only'} |"
        )
    dependencies = "\n".join(f"- `{name}` — {reason}" for name, reason in report["dependency_trace"].items())
    reasons = "\n".join(f"- `{name}`: {count:,}" for name, count in rec["reason_counts"].items())
    return f"""# EXP-011 Revenue-Mapping Impact Audit

Status: **{report['status']}**  
Classification: **{report['classification']}**

## Scope and firewall

This is a parallel corrected-data integrity audit of the frozen EXP-011 population. It does not edit `sec_v3`, `{frozen['dataset_id']}`, or any EXP-011 output. It loaded no target or return columns, fit zero models, computed no IC/Sharpe/portfolio statistic, and did not access the sealed holdout.

The conservative rule uses consolidated, undimensioned USD facts already admitted by SEC v3 plus `pre.txt` income-statement presentation. A differing candidate is selected only when it is the unique explicitly labelled total/net revenue line or the unique candidate presented on the income statement. Equal candidates preserve the frozen value. Multiple plausible totals, duplicate-tag conflicts, or absent presentation evidence are `REVENUE_AMBIGUOUS`; the shadow view leaves revenue missing.

## Measured filing scope

- Frozen rows: {frozen['rows']:,}; CIKs: {frozen['ciks']:,}; dates: {frozen['date_min']} through {frozen['date_max']}.
- Multi-candidate annual filings: {rec['multi_candidate_filings']:,} ({rec['multi_candidate_contexts']:,} filing-period contexts, including comparative periods).
- Unambiguously corrected disagreements: {rec['corrected_disagreement_filings']:,} filings ({rec['corrected_disagreement_contexts']:,} contexts).
- Ambiguous filings: {rec['ambiguous_filings']:,} ({rec['ambiguous_contexts']:,} contexts).
- Affected CIKs (corrected or ambiguous): {rec['affected_ciks']:,}.
- Corrected/frozen revenue ratio: median {ratio['median'] if ratio['median'] is not None else '—'}, p05 {ratio['p05'] if ratio['p05'] is not None else '—'}, p95 {ratio['p95'] if ratio['p95'] is not None else '—'}, min {ratio['min'] if ratio['min'] is not None else '—'}, max {ratio['max'] if ratio['max'] is not None else '—'}.

Reason codes:

{reasons}

## Attached-snapshot impact

{snap['affected_name_dates']:,} of {frozen['rows']:,} EXP-011 name-dates ({snap['share']:.4%}) receive a different revenue-dependent snapshot in the shadow view. This count excludes cross-sectional rank propagation to otherwise unchanged names.

### By validation period

{_table(snap['by_fold'], 'Period')}

### By year

{_table(snap['by_year'], 'Year')}

### By filer regime

{_table(snap['by_regime'], 'Regime')}

## Actual revenue dependency trace

The list below is derived from `src/quant/features/pit_fundamentals.py` and `src/quant/pit/rich_panel.py`, not from the prompt:

{dependencies}

## Shadow feature-cell impact

- Common rows: {impact['common_rows']:,}.
- Frozen features examined: {impact['features_examined']}.
- Changed feature cells: {impact['changed_cells']:,}.
- Name-dates with any changed rank, including same-date propagation: {impact['affected_name_dates_including_rank_propagation']:,}.
- Features with at least one changed cell: {impact['affected_features']}.
- Frozen pipeline reproduction changed cells before correction: {report['integrity']['frozen_reproduction_changed_cells']}.

All feature changes below are changes in the stored cross-sectional rank scale. “Same-date ranks changed” equals the changed-cell count for that ranked feature and is recorded in the machine manifest.

{chr(10).join(feature_lines)}

Changed cells by validation period: `{json.dumps(impact['changed_cells_by_fold'], sort_keys=True)}`  
Changed cells by year: `{json.dumps(impact['changed_cells_by_year'], sort_keys=True)}`

## Scientific interpretation

EXP-011 remains the immutable result of its frozen v3 pipeline. The audit does not label it automatically invalid or harmless. The measured scope contains unresolved filing-level ambiguity, so the descriptive classification is **{report['classification']}**. A formal corrected-data replication decision is required before the frozen result can support final-candidate selection. No post-hoc materiality percentage was invented.

Machine-readable evidence: `data/manifests/exp011_revenue_mapping_impact.json`.
"""


def main() -> None:
    report = run(ROOT)
    atomic_json(MANIFEST, report)
    DOCUMENT.write_text(render(report))
    print(json.dumps({
        "classification": report["classification"],
        "corrected_disagreement_filings": report["reconciliation"]["corrected_disagreement_filings"],
        "ambiguous_filings": report["reconciliation"]["ambiguous_filings"],
        "affected_name_dates": report["snapshot_impact"]["affected_name_dates"],
        "changed_cells": report["feature_impact"]["changed_cells"],
    }, indent=2))


if __name__ == "__main__":
    main()
