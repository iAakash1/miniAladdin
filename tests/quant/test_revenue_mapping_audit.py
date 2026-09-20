import zipfile

import pandas as pd

from src.quant.pit import revenue_mapping_audit as A


def _facts() -> pd.DataFrame:
    rows = []
    cases = [
        (1, "a", 100.0, 250.0),   # unique explicit total -> corrected
        (2, "b", 100.0, 200.0),   # both plausible -> ambiguous
        (3, "c", 100.0, 100.0),   # equal -> frozen value supported
    ]
    for cik, accession, contract, broad in cases:
        for priority, (tag, value) in enumerate([
            ("RevenueFromContractWithCustomerExcludingAssessedTax", contract),
            ("Revenues", broad),
        ]):
            rows.append({"cik": cik, "accession": accession, "period_end": pd.Timestamp("2023-12-31").date(),
                         "qtrs": 4, "canonical_fact": "revenue", "form": "10-K", "tag": tag,
                         "tag_priority": priority, "value": value, "source_archive": "2024q1.zip"})
    return pd.DataFrame(rows)


def _archive(root):
    target = root / "data/raw/sec"
    target.mkdir(parents=True)
    pre = pd.DataFrame([
        {"adsh": "a", "report": 1, "line": 1, "stmt": "IS", "inpth": 0, "rfile": "H",
         "tag": "RevenueFromContractWithCustomerExcludingAssessedTax", "version": "us-gaap/2023", "plabel": "Revenue", "negating": 0},
        {"adsh": "a", "report": 1, "line": 2, "stmt": "IS", "inpth": 0, "rfile": "H",
         "tag": "Revenues", "version": "us-gaap/2023", "plabel": "Total revenues", "negating": 0},
        {"adsh": "b", "report": 1, "line": 1, "stmt": "IS", "inpth": 0, "rfile": "H",
         "tag": "RevenueFromContractWithCustomerExcludingAssessedTax", "version": "us-gaap/2023", "plabel": "Revenue", "negating": 0},
        {"adsh": "b", "report": 1, "line": 2, "stmt": "IS", "inpth": 0, "rfile": "H",
         "tag": "Revenues", "version": "us-gaap/2023", "plabel": "Revenues", "negating": 0},
    ])
    path = target / "2024q1.zip"
    pre_path = root / "pre.txt"
    pre.to_csv(pre_path, sep="\t", index=False)
    with zipfile.ZipFile(path, "w") as archive:
        archive.write(pre_path, "pre.txt")


def test_conservative_reconciliation_selects_only_unique_total_and_marks_ambiguity(tmp_path):
    _archive(tmp_path)
    result, selected = A.reconcile_filings(tmp_path, _facts())
    states = result.set_index("accession")["status"].to_dict()
    assert states == {"a": "CORRECTED_CANDIDATE", "b": "REVENUE_AMBIGUOUS", "c": "CURRENT_SUPPORTED"}
    assert result.set_index("accession").loc["a", "corrected_value"] == 250.0
    assert tuple(result.set_index("accession").loc["a", "presentation"]["Revenues"]["labels"]) == ("Total revenues",)
    assert len(selected) == 1


def test_shadow_view_never_invents_an_ambiguous_value(tmp_path):
    _archive(tmp_path)
    facts = _facts()
    result, selected = A.reconcile_filings(tmp_path, facts)
    shadow = A.corrected_fact_view(facts, result, selected)
    assert not ((shadow["accession"] == "b") & (shadow["canonical_fact"] == "revenue")).any()
    chosen = shadow[(shadow["accession"] == "a") & (shadow["tag"] == "Revenues")]
    assert chosen.iloc[0]["tag_priority"] == -1


def test_dependency_trace_covers_direct_and_indirect_revenue_consumers():
    expected = {"gross_margin_xs", "asset_turnover_xs", "revenue_growth_xs", "gross_margin_stability_xs",
                "sales_yield_xs", "sales_to_ev_xs", "gross_profitability_xs", "gross_profit_to_ev_xs"}
    assert expected <= set(A.REVENUE_DEPENDENCIES)


def test_distribution_is_positional_and_reports_zero_not_nan():
    mask = pd.Series([True, False, False])
    groups = pd.Series(["a", "a", "b"])
    assert A._distribution(mask, groups) == {
        "a": {"rows": 2, "affected": 1, "share": 0.5},
        "b": {"rows": 1, "affected": 0, "share": 0.0},
    }
